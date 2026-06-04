// --- START OF FILE go_core/main.go ---
package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net"
	"net/http"
	"os"
	"os/exec"
	"sort"
	"strings"
	"sync"
	"time"

	"golang.org/x/net/proxy"
)

type EngineSettings struct {
	MaxLatency       int      `json:"max_latency"`
	MinSpeed         float64  `json:"min_speed"`
	ConnectivityUrls []string `json:"connectivity_urls"`
	SpeedtestUrl     string   `json:"speedtest_url"`
	ChampionTestUrl  string   `json:"champion_test_url"`
	BatchSize        int      `json:"batch_size"`
}

type InputPayload struct {
	Settings EngineSettings           `json:"settings"`
	Nodes    []map[string]interface{} `json:"nodes"`
}

var (
	globalSettings    EngineSettings
	forbiddenNetworks []*net.IPNet

	normalDownloadBytes   = 512 * 1024
	championDownloadBytes = 10 * 1024 * 1024
	readBufSize           = 32 * 1024

	portCounter = 10000
	portMutex   sync.Mutex

	// L4 failure reason counters (reset per l4 phase)
	l4Stats   L4Stats
	l4StatsMu sync.Mutex

	// L7 failure reason counters (reset per l7 phase)
	l7Stats   L7Stats
	l7StatsMu sync.Mutex
)

// L4Stats tracks L4 failure reasons for telemetry
type L4Stats struct {
	Total             int `json:"total"`
	Survived          int `json:"survived"`
	DNS_Error         int `json:"dns_error"`
	Timeout           int `json:"timeout"`
	ConnectionRefused int `json:"connection_refused"`
	InvalidConfig     int `json:"invalid_config"`
	Other             int `json:"other"`

	// Retry metrics
	RetryAttempts  int `json:"retry_attempts"`
	RetryRecovered int `json:"retry_recovered"` // nodes saved by retry
}

// L7Stats tracks L7 (sing-box) failure reasons for telemetry
type L7Stats struct {
	Total            int `json:"total"`
	Survived         int `json:"survived"`
	HTTPTimeout      int `json:"http_timeout"`
	HTTPTLSError     int `json:"http_tls_error"`
	HTTPBadStatus    int `json:"http_bad_status"`
	HTTPOtherError   int `json:"http_other_error"`
	SpeedTimeout     int `json:"speed_timeout"`
	SpeedTLSError    int `json:"speed_tls_error"`
	SpeedTooSlow     int `json:"speed_too_slow"`
	SpeedOtherError  int `json:"speed_other_error"`
	SingboxCrash     int `json:"singbox_crash"`
	ProtocolMismatch int `json:"protocol_mismatch"`
}

func init() {
	cidrs := []string{
		"1.1.1.0/24", "1.0.0.0/24", "8.8.8.0/24", "8.8.4.0/24",
		"162.159.0.0/16", "104.16.0.0/12", "172.64.0.0/13",
	}
	for _, cidr := range cidrs {
		_, network, err := net.ParseCIDR(cidr)
		if err == nil {
			forbiddenNetworks = append(forbiddenNetworks, network)
		}
	}
}

func getNextBasePort(batchSize int) int {
	portMutex.Lock()
	defer portMutex.Unlock()
	p := portCounter
	portCounter += batchSize + 10
	if portCounter > 60000 {
		portCounter = 10000
	}
	return p
}

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "Usage: angra_core <input.json> <output.json> [stats.json]")
		os.Exit(1)
	}

	data, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "ReadFile: %v\n", err)
		os.Exit(1)
	}

	var payload InputPayload
	if err := json.Unmarshal(data, &payload); err != nil {
		fmt.Fprintf(os.Stderr, "Unmarshal: %v\n", err)
		os.Exit(1)
	}

	globalSettings = payload.Settings
	if globalSettings.BatchSize <= 0 {
		globalSettings.BatchSize = 150
	}

	nodes := payload.Nodes

	l4Nodes := runL4Phase(nodes)
	survivalPct := 0.0
	if len(nodes) > 0 {
		survivalPct = float64(len(l4Nodes)) / float64(len(nodes)) * 100
	}
	fmt.Printf("✔[ФИЛЬТРАЦИЯ L4]: Отбраковано %d, Выжило: %d (%.2f%% survival)\n",
		len(nodes)-len(l4Nodes), len(l4Nodes), survivalPct)

	// If no L4 survivors, write output + stats and exit early
	if len(l4Nodes) == 0 {
		_ = os.WriteFile(os.Args[2], []byte("[]"), 0644)
		writeCombinedStats()
		return
	}

	l7Nodes := runL7Phase(l4Nodes)
	l7Pct := 0.0
	if len(l4Nodes) > 0 {
		l7Pct = float64(len(l7Nodes)) / float64(len(l4Nodes)) * 100
	}
	fmt.Printf("✔ [ИНСПЕКЦИЯ L7]: Завершена. Выжило узлов: %d (%.2f%% of L4 survivors)\n",
		len(l7Nodes), l7Pct)

	if len(l7Nodes) > 0 {
		runChampionPhase(l7Nodes)
	}

	// Write combined L4+L7 stats
	writeCombinedStats()

	outData, _ := json.Marshal(l7Nodes)
	_ = os.WriteFile(os.Args[2], outData, 0644)
}

// writeCombinedStats writes both L4 and L7 stats to the stats file (3rd CLI arg).
func writeCombinedStats() {
	if len(os.Args) < 4 || os.Args[3] == "" {
		return
	}
	l4StatsMu.Lock()
	l4 := l4Stats
	l4StatsMu.Unlock()
	l7StatsMu.Lock()
	l7 := l7Stats
	l7StatsMu.Unlock()

	combined := map[string]interface{}{
		"total":             l4.Total,
		"survived":          l4.Survived,
		"dns_error":         l4.DNS_Error,
		"timeout":           l4.Timeout,
		"connection_refused": l4.ConnectionRefused,
		"invalid_config":    l4.InvalidConfig,
		"other":             l4.Other,
		"retry_attempts":    l4.RetryAttempts,
		"retry_recovered":   l4.RetryRecovered,
		"l7": map[string]interface{}{
			"total":             l7.Total,
			"survived":          l7.Survived,
			"http_timeout":      l7.HTTPTimeout,
			"http_tls_error":    l7.HTTPTLSError,
			"http_bad_status":   l7.HTTPBadStatus,
			"http_other_error":  l7.HTTPOtherError,
			"speed_timeout":     l7.SpeedTimeout,
			"speed_tls_error":   l7.SpeedTLSError,
			"speed_too_slow":    l7.SpeedTooSlow,
			"speed_other_error": l7.SpeedOtherError,
			"singbox_crash":     l7.SingboxCrash,
			"protocol_mismatch": l7.ProtocolMismatch,
		},
	}
	if statsBytes, err := json.Marshal(combined); err == nil {
		_ = os.WriteFile(os.Args[3], statsBytes, 0644)
	}

	// Print L7 failure breakdown
	l7Total := l7.Total
	l7Surv := l7.Survived
	l7Dropped := l7Total - l7Surv
	fmt.Printf("  L7 failure breakdown: total=%d dropped=%d survived=%d | "+
		"http_timeout=%d http_tls=%d http_bad_status=%d http_other=%d | "+
		"speed_timeout=%d speed_tls=%d speed_slow=%d speed_other=%d | "+
		"singbox_crash=%d protocol_mismatch=%d\n",
		l7Total, l7Dropped, l7Surv,
		l7.HTTPTimeout, l7.HTTPTLSError, l7.HTTPBadStatus, l7.HTTPOtherError,
		l7.SpeedTimeout, l7.SpeedTLSError, l7.SpeedTooSlow, l7.SpeedOtherError,
		l7.SingboxCrash, l7.ProtocolMismatch)
}

func runL4Phase(nodes []map[string]interface{}) []map[string]interface{} {
	// Reset L4 stats for this phase
	l4StatsMu.Lock()
	l4Stats = L4Stats{Total: len(nodes)}
	l4StatsMu.Unlock()

	validNodes := make([]map[string]interface{}, 0, len(nodes)/2)
	var mu sync.Mutex

	sem := make(chan struct{}, 500)

	chunkSz := 1000
	for i := 0; i < len(nodes); i += chunkSz {
		end := i + chunkSz
		if end > len(nodes) {
			end = len(nodes)
		}
		chunk := nodes[i:end]

		var wg sync.WaitGroup
		for _, node := range chunk {
			wg.Add(1)
			go func(n map[string]interface{}) {
				defer wg.Done()
				sem <- struct{}{}
				defer func() { <-sem }()
				alive, reason := checkL4(n)
				if alive {
					mu.Lock()
					l4StatsMu.Lock()
					l4Stats.Survived++
					l4StatsMu.Unlock()
					validNodes = append(validNodes, n)
					mu.Unlock()
				} else {
					l4StatsMu.Lock()
					switch reason {
					case "dns_error":
						l4Stats.DNS_Error++
					case "timeout":
						l4Stats.Timeout++
					case "connection_refused":
						l4Stats.ConnectionRefused++
					case "invalid_config":
						l4Stats.InvalidConfig++
					default:
						l4Stats.Other++
					}
					l4StatsMu.Unlock()
				}
			}(node)
		}
		wg.Wait()
	}
	return validNodes
}

// checkL4 performs TCP connectivity check with retry.
// Returns (alive bool, failureReason string).
// Timeouts: DNS 4s, TCP dial attempt 1: 8s, retry after 2s wait: 10s.
func checkL4(node map[string]interface{}) (bool, string) {
	protocol, _ := node["protocol"].(string)
	if protocol == "hysteria2" || protocol == "quic" {
		// UDP-based protocols — skip L4 TCP check
		return true, ""
	}

	config, ok := node["config"].(map[string]interface{})
	if !ok {
		return false, "invalid_config"
	}

	hostRaw, _ := config["server"].(string)
	host := strings.Trim(hostRaw, "[]")
	portFloat, _ := config["port"].(float64)
	port := int(portFloat)
	if port <= 0 || port > 65535 {
		return false, "invalid_config"
	}

	// DNS resolution with 4s timeout (increased from 2s)
	var targetIP net.IP
	if parsed := net.ParseIP(host); parsed != nil {
		targetIP = parsed
	} else {
		ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
		defer cancel()
		ips, err := net.DefaultResolver.LookupIP(ctx, "ip", host)
		if err != nil || len(ips) == 0 {
			return false, "dns_error"
		}
		for _, ip := range ips {
			if ip.To4() != nil {
				targetIP = ip
				break
			}
		}
		if targetIP == nil {
			targetIP = ips[0]
		}
	}

	if targetIP.IsLoopback() || targetIP.IsPrivate() || targetIP.IsUnspecified() {
		return false, "invalid_config"
	}

	nodeType, _ := config["type"].(string)
	nt := strings.ToLower(nodeType)
	isCdnAllowed := nt == "ws" || nt == "websocket" || nt == "httpupgrade" ||
		nt == "xhttp" || nt == "grpc"
	if !isCdnAllowed {
		for _, network := range forbiddenNetworks {
			if network.Contains(targetIP) {
				return false, "invalid_config"
			}
		}
	}

	var addr string
	if targetIP.To4() != nil {
		addr = fmt.Sprintf("%s:%d", targetIP.String(), port)
	} else {
		addr = fmt.Sprintf("[%s]:%d", targetIP.String(), port)
	}

	// Attempt 1: TCP dial with 8s timeout (increased from 2.5s)
	// Jitter 0-29ms to spread connection storms
	time.Sleep(time.Duration(rand.Intn(30)) * time.Millisecond)

	conn, err := net.DialTimeout("tcp", addr, 8*time.Second)
	if err == nil {
		conn.Close()
		return true, ""
	}

	// Classify failure and decide whether to retry
	errStr := err.Error()
	isTimeout := strings.Contains(errStr, "timeout") || strings.Contains(errStr, "i/o timeout")

	if !isTimeout {
		// Connection refused, network unreachable — unlikely to change on retry
		if strings.Contains(errStr, "refused") {
			return false, "connection_refused"
		}
		return false, "other"
	}

	// Attempt 2: retry with 10s timeout after 2s exponential backoff
	l4StatsMu.Lock()
	l4Stats.RetryAttempts++
	l4StatsMu.Unlock()

	time.Sleep(2 * time.Second)

	conn2, err2 := net.DialTimeout("tcp", addr, 10*time.Second)
	if err2 == nil {
		conn2.Close()
		l4StatsMu.Lock()
		l4Stats.RetryRecovered++
		l4StatsMu.Unlock()
		return true, ""
	}

	return false, "timeout"
}

func runL7Phase(nodes []map[string]interface{}) []map[string]interface{} {
	// Initialize L7 stats
	l7StatsMu.Lock()
	l7Stats = L7Stats{Total: len(nodes)}
	l7StatsMu.Unlock()

	batchSize := globalSettings.BatchSize
	totalBatches := (len(nodes) + batchSize - 1) / batchSize
	finalNodes := make([]map[string]interface{}, 0, len(nodes)/3)

	for i := 0; i < len(nodes); i += batchSize {
		end := i + batchSize
		if end > len(nodes) {
			end = len(nodes)
		}
		batch := nodes[i:end]
		batchNum := (i / batchSize) + 1

		survivors := processSingboxRecursive(batch, false, 0)
		finalNodes = append(finalNodes, survivors...)

		if batchNum%5 == 0 || batchNum == totalBatches {
			fmt.Printf("► [ИНСПЕКЦИЯ L7]: Батч %d/%d завершен (Выжило: %d)\n",
				batchNum, totalBatches, len(survivors))
		}
	}

	// Finalize L7 survived count
	l7StatsMu.Lock()
	l7Stats.Survived = len(finalNodes)
	l7StatsMu.Unlock()

	return finalNodes
}

func processSingboxRecursive(
	batch []map[string]interface{},
	isChampion bool,
	depth int,
) []map[string]interface{} {
	if len(batch) == 0 {
		return nil
	}
	if depth > 3 {
		// Recursive splitting exhausted — nodes could not be checked
		l7StatsMu.Lock()
		l7Stats.SingboxCrash += len(batch)
		l7StatsMu.Unlock()
		return nil
	}

	survivors, crashed := processSingboxBatch(batch, isChampion)
	if crashed {
		if len(batch) == 1 {
			return nil
		}
		mid := len(batch) / 2
		left := processSingboxRecursive(batch[:mid], isChampion, depth+1)
		right := processSingboxRecursive(batch[mid:], isChampion, depth+1)
		return append(left, right...)
	}
	return survivors
}

func processSingboxBatch(
	batch []map[string]interface{},
	isChampion bool,
) ([]map[string]interface{}, bool) {

	basePort := getNextBasePort(len(batch))
	inbounds := make([]map[string]interface{}, 0, len(batch))
	outbounds := make([]map[string]interface{}, 0, len(batch)+2)
	rules := []map[string]interface{}{
		{"protocol": "dns", "outbound": "direct"},
		{
			"ip_cidr":  []string{"127.0.0.0/8", "10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12", "::1/128", "fc00::/7", "fe80::/10"},
			"outbound": "block",
		},
	}

	portToNode := make(map[int]map[string]interface{}, len(batch))

	firstValidPort := -1

	for i, node := range batch {
		readyOutbound, ok := node["ready_outbound"].(map[string]interface{})
		if !ok {
			continue
		}
		tag := fmt.Sprintf("proxy-%d", i)
		readyOutbound["tag"] = tag

		localPort := basePort + i

		inbounds = append(inbounds, map[string]interface{}{
			"type":        "socks",
			"tag":         fmt.Sprintf("in-%d", i),
			"listen":      "127.0.0.1",
			"listen_port": localPort,
		})
		outbounds = append(outbounds, readyOutbound)
		rules = append(rules, map[string]interface{}{
			"inbound":  []string{fmt.Sprintf("in-%d", i)},
			"outbound": tag,
		})
		portToNode[localPort] = node

		if firstValidPort == -1 {
			firstValidPort = localPort
		}
	}

	if firstValidPort == -1 || len(portToNode) == 0 {
		// All nodes in this batch have no valid outbound config
		l7StatsMu.Lock()
		l7Stats.ProtocolMismatch += len(batch)
		l7StatsMu.Unlock()
		return nil, false
	}

	outbounds = append(outbounds,
		map[string]interface{}{"type": "direct", "tag": "direct"},
		map[string]interface{}{"type": "block", "tag": "block"},
	)

	configMap := map[string]interface{}{
		"log": map[string]interface{}{
			"disabled": true,
		},
		"dns": map[string]interface{}{
			"servers": []map[string]interface{}{
				{
					"tag":     "remote-doh",
					"address": "https://1.1.1.1/dns-query",
					"detour":  "direct",
				},
				{
					"tag":     "fallback-doh",
					"address": "https://dns.quad9.net/dns-query",
					"detour":  "direct",
				},
			},
			"strategy":          "prefer_ipv4",
			"independent_cache": true,
		},
		"inbounds":  inbounds,
		"outbounds": outbounds,
		"route": map[string]interface{}{
			"rules": rules,
			"final": "block",
		},
	}

	configBytes, _ := json.Marshal(configMap)
	configPath := fmt.Sprintf("run_%d.json", basePort)
	_ = os.WriteFile(configPath, configBytes, 0644)
	defer os.Remove(configPath)

	cmd := exec.Command("sing-box", "run", "-c", configPath)
	if err := cmd.Start(); err != nil {
		return nil, true
	}
	defer func() {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
	}()

	portReady := false
	deadline := time.Now().Add(8 * time.Second) // increased from 5s
	for time.Now().Before(deadline) {
		conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", firstValidPort), 300*time.Millisecond)
		if err == nil {
			conn.Close()
			portReady = true
			break
		}
		time.Sleep(100 * time.Millisecond)
	}

	if !portReady {
		// Sing-box failed to start — track all nodes in batch
		l7StatsMu.Lock()
		l7Stats.SingboxCrash += len(batch)
		l7StatsMu.Unlock()
		return nil, true
	}
	time.Sleep(200 * time.Millisecond)

	var wgPing sync.WaitGroup
	var mu sync.Mutex
	pingPassed := make(map[int]map[string]interface{}, len(portToNode))
	semPing := make(chan struct{}, 200)

	for port, node := range portToNode {
		wgPing.Add(1)
		semPing <- struct{}{}
		go func(p int, n map[string]interface{}) {
			defer wgPing.Done()
			defer func() { <-semPing }()
			if lat, ok, reason := testHTTPPing(p); ok {
				n["latency"] = lat
				mu.Lock()
				pingPassed[p] = n
				mu.Unlock()
			} else {
				// Track L7 HTTP ping failure reason
				l7StatsMu.Lock()
				switch reason {
				case "timeout":
					l7Stats.HTTPTimeout++
				case "tls_error":
					l7Stats.HTTPTLSError++
				case "bad_status":
					l7Stats.HTTPBadStatus++
				default:
					l7Stats.HTTPOtherError++
				}
				l7StatsMu.Unlock()
			}
		}(port, node)
	}
	wgPing.Wait()

	if len(pingPassed) == 0 {
		return nil, false
	}

	var wgSpeed sync.WaitGroup
	alive := make([]map[string]interface{}, 0, len(pingPassed))
	semSpeed := make(chan struct{}, 40)

	for port, node := range pingPassed {
		wgSpeed.Add(1)
		semSpeed <- struct{}{}
		go func(p int, n map[string]interface{}) {
			defer wgSpeed.Done()
			defer func() { <-semSpeed }()
			verifySSL := resolvePayloadSSL(n)
			if speed, ok, reason := testHTTPSpeed(p, verifySSL, isChampion); ok {
				n["speed"] = speed
				mu.Lock()
				alive = append(alive, n)
				mu.Unlock()
			} else {
				// Track L7 speed test failure reason
				l7StatsMu.Lock()
				switch reason {
				case "timeout":
					l7Stats.SpeedTimeout++
				case "tls_error":
					l7Stats.SpeedTLSError++
				case "too_slow":
					l7Stats.SpeedTooSlow++
				default:
					l7Stats.SpeedOtherError++
				}
				l7StatsMu.Unlock()
			}
		}(port, node)
	}
	wgSpeed.Wait()

	return alive, false
}

func getSocksClient(port int, timeout time.Duration, verifySSL bool) *http.Client {
	dialer, err := proxy.SOCKS5(
		"tcp",
		fmt.Sprintf("127.0.0.1:%d", port),
		nil,
		proxy.Direct,
	)
	if err != nil {
		dialer = proxy.Direct
	}
	transport := &http.Transport{
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			return dialer.Dial(network, addr)
		},
		TLSClientConfig:    &tls.Config{InsecureSkipVerify: !verifySSL},
		DisableKeepAlives:  true,
		DisableCompression: true,
		MaxIdleConns:       1,
		IdleConnTimeout:    5 * time.Second,
	}
	return &http.Client{Transport: transport, Timeout: timeout}
}

// testHTTPPing probes connectivity through the SOCKS proxy.
// Returns (latency_ms, ok, failure_reason).
// failure_reason is one of: "" (success), "timeout", "tls_error", "http_error".
func testHTTPPing(port int) (int, bool, string) {
	maxLatency := globalSettings.MaxLatency
	if maxLatency <= 0 {
		maxLatency = 5000
	}

	urls := globalSettings.ConnectivityUrls
	if len(urls) == 0 {
		urls = []string{
			"http://cp.cloudflare.com/generate_204",
			"http://www.gstatic.com/generate_204",
		}
	}

	// Prefer generate_204 endpoints — they return clean 204 responses
	var filtered []string
	for _, u := range urls {
		if strings.Contains(strings.ToLower(u), "generate_204") {
			filtered = append(filtered, u)
		}
	}
	if len(filtered) > 0 {
		urls = filtered
	}

	rand.Shuffle(len(urls), func(i, j int) { urls[i], urls[j] = urls[j], urls[i] })
	if len(urls) > 2 {
		urls = urls[:2]
	}

	// HTTP timeout: maxLatency + 10s buffer = 15s total (increased from 6.5s)
	client := getSocksClient(
		port,
		time.Duration(maxLatency+10000)*time.Millisecond,
		false,
	)

	// Track reason for the LAST error across all URL attempts
	var lastReason string

	for _, targetURL := range urls {
		t0 := time.Now()

		req, err := http.NewRequest("GET", targetURL, nil)
		if err != nil {
			lastReason = "http_error"
			continue
		}
		req.Header.Set("User-Agent",
			"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

		resp, err := client.Do(req)
		if err != nil {
			errStr := strings.ToLower(err.Error())
			if strings.Contains(errStr, "timeout") || strings.Contains(errStr, "deadline") {
				lastReason = "timeout"
			} else if strings.Contains(errStr, "tls") || strings.Contains(errStr, "x509") ||
				strings.Contains(errStr, "handshake") {
				lastReason = "tls_error"
			} else {
				lastReason = "http_error"
			}
			continue
		}

		_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 512))
		resp.Body.Close()

		if resp.StatusCode != 204 {
			lastReason = "bad_status"
			continue
		}

		lat := int(time.Since(t0).Milliseconds())
		if lat > maxLatency {
			return 0, false, "timeout"
		}
		return lat, true, ""
	}

	if lastReason == "" {
		lastReason = "http_error"
	}
	return 0, false, lastReason
}

// testHTTPSpeed measures download speed through the SOCKS proxy.
// Returns (speed_mbps, ok, failure_reason).
// failure_reason is one of: "" (success), "timeout", "tls_error", "too_slow", "http_error".
func testHTTPSpeed(port int, verifySSL bool, isChampion bool) (float64, bool, string) {
	minSpeed := globalSettings.MinSpeed
	if minSpeed <= 0 {
		minSpeed = 1.0
	}

	var (
		timeout    time.Duration
		targetURL  string
		targetSize int
	)

	if isChampion {
		timeout = 25 * time.Second
		targetSize = championDownloadBytes
		targetURL = globalSettings.ChampionTestUrl
		if targetURL == "" {
			targetURL = "https://speed.cloudflare.com/__down?bytes=10485760"
		}
	} else {
		timeout = 15 * time.Second // increased from 8s
		targetSize = normalDownloadBytes
		targetURL = globalSettings.SpeedtestUrl
		if targetURL == "" || targetURL == "https://speed.cloudflare.com" {
			targetURL = "https://speed.cloudflare.com/__down?bytes=524288"
		}
	}

	client := getSocksClient(port, timeout, verifySSL)
	req, err := http.NewRequest("GET", targetURL, nil)
	if err != nil {
		return 0, false, "http_error"
	}
	req.Header.Set("User-Agent",
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

	tStart := time.Now()
	resp, err := client.Do(req)
	if err != nil {
		errStr := strings.ToLower(err.Error())
		if strings.Contains(errStr, "timeout") || strings.Contains(errStr, "deadline") {
			return 0, false, "timeout"
		} else if strings.Contains(errStr, "tls") || strings.Contains(errStr, "x509") ||
			strings.Contains(errStr, "handshake") {
			return 0, false, "tls_error"
		}
		return 0, false, "http_error"
	}
	defer resp.Body.Close()

	if resp.StatusCode == 429 || resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return 0, false, "http_error"
	}

	buf := make([]byte, readBufSize)
	total := 0

	for {
		n, readErr := resp.Body.Read(buf)
		total += n

		elapsed := time.Since(tStart).Seconds()
		if elapsed > 3.5 && total < 65536 {
			return 0, false, "too_slow"
		}

		if total >= targetSize || readErr != nil {
			break
		}
	}

	if total < 256*1024 {
		return 0, false, "too_slow"
	}

	elapsed := time.Since(tStart).Seconds()
	if elapsed < 0.05 {
		elapsed = 0.05
	}

	speed := (float64(total) * 8.0) / (elapsed * 1_000_000.0)
	if speed > 3000.0 {
		speed = 3000.0
	}
	if speed < minSpeed {
		return 0, false, "too_slow"
	}
	return speed, true, ""
}

func resolvePayloadSSL(node map[string]interface{}) bool {
	config, ok := node["config"].(map[string]interface{})
	if !ok {
		return true
	}
	sec, _ := config["security"].(string)
	if sec == "reality" {
		return true
	}
	rawMeta, ok := config["raw_meta"].(map[string]interface{})
	if !ok {
		return true
	}
	for k, v := range rawMeta {
		kl := strings.ToLower(k)
		if kl == "allowinsecure" || kl == "insecure" {
			vs := fmt.Sprintf("%v", v)
			if vs == "1" || vs == "true" || vs == "yes" {
				return false
			}
		}
	}
	return true
}

func runChampionPhase(nodes []map[string]interface{}) {
	sort.Slice(nodes, func(i, j int) bool {
		sI, _ := nodes[i]["speed"].(float64)
		sJ, _ := nodes[j]["speed"].(float64)
		return sI > sJ
	})

	limit := 5
	if len(nodes) < limit {
		limit = len(nodes)
	}
	fmt.Printf("►[ANGRA-GO CHAMPION]: Старт 10MB спидтеста для Топ-%d\n", limit)

	for i := 0; i < limit; i++ {
		res, crashed := processSingboxBatch(
			[]map[string]interface{}{nodes[i]}, true,
		)
		if !crashed && len(res) > 0 {
			if s, ok := res[0]["speed"].(float64); ok {
				nodes[i]["speed"] = s
			}
		}
	}
}
