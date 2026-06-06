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
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"golang.org/x/net/proxy"
)

type EngineSettings struct {
	MaxLatency       int      `json:"max_latency"`
	MinSpeed         float64  `json:"min_speed"`
	SpeedAsFilter    bool     `json:"speed_as_filter"`
	SpeedConcurrency int      `json:"speed_concurrency"`
	L7Concurrency    int      `json:"l7_concurrency"`
	ConnectivityUrls []string `json:"connectivity_urls"`
	SpeedtestUrl     string   `json:"speedtest_url"`
	ChampionTestUrl  string   `json:"champion_test_url"`
	BatchSize        int      `json:"batch_size"`
	ChampionTopN     int      `json:"champion_top_n"`
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

	// globalSpeedSem bounds the TOTAL number of concurrent speed-test
	// downloads across ALL parallel L7 batches. It is a single shared cap so
	// that raising L7 batch parallelism never multiplies bandwidth contention
	// on the runner's single uplink (see AUDIT §2.4). Sized by speed_concurrency
	// and initialised once in main().
	globalSpeedSem chan struct{}

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

	// Global download-concurrency cap shared by every parallel L7 batch.
	speedCap := globalSettings.SpeedConcurrency
	if speedCap <= 0 {
		speedCap = 12
	}
	globalSpeedSem = make(chan struct{}, speedCap)

	nodes := payload.Nodes

	l4Nodes := runL4Phase(nodes)
	survivalPct := 0.0
	if len(nodes) > 0 {
		survivalPct = float64(len(l4Nodes)) / float64(len(nodes)) * 100
	}
	fmt.Printf("├─ %-16skilled %d · alive %d · %.1f%% survival\n",
		"L4 filter", len(nodes)-len(l4Nodes), len(l4Nodes), survivalPct)

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
	fmt.Printf("├─ %-16ssurvivors %d · %.1f%% of L4\n",
		"L7 inspect", len(l7Nodes), l7Pct)

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
		"total":              l4.Total,
		"survived":           l4.Survived,
		"dns_error":          l4.DNS_Error,
		"timeout":            l4.Timeout,
		"connection_refused": l4.ConnectionRefused,
		"invalid_config":     l4.InvalidConfig,
		"other":              l4.Other,
		"retry_attempts":     l4.RetryAttempts,
		"retry_recovered":    l4.RetryRecovered,
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
	fmt.Printf("│  %-16stotal=%d dropped=%d survived=%d | "+
		"http_timeout=%d http_tls=%d http_bad_status=%d http_other=%d | "+
		"speed_timeout=%d speed_tls=%d speed_slow=%d speed_other=%d | "+
		"singbox_crash=%d protocol_mismatch=%d\n",
		"L7 breakdown",
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

	addr := net.JoinHostPort(targetIP.String(), strconv.Itoa(port))

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

// l7Brief returns a compact snapshot of the running L7 failure counters so a
// run that is cancelled mid-phase still shows WHY nodes are being dropped
// (crash vs ping-timeout vs protocol-mismatch) on every logged batch line.
func l7Brief() string {
	l7StatsMu.Lock()
	s := l7Stats
	l7StatsMu.Unlock()
	return fmt.Sprintf(
		"crash=%d proto_mismatch=%d ping_timeout=%d ping_tls=%d ping_bad=%d ping_other=%d",
		s.SingboxCrash, s.ProtocolMismatch,
		s.HTTPTimeout, s.HTTPTLSError, s.HTTPBadStatus, s.HTTPOtherError)
}

func runL7Phase(nodes []map[string]interface{}) []map[string]interface{} {
	// Initialize L7 stats
	l7StatsMu.Lock()
	l7Stats = L7Stats{Total: len(nodes)}
	l7StatsMu.Unlock()

	batchSize := globalSettings.BatchSize
	totalBatches := (len(nodes) + batchSize - 1) / batchSize

	// Number of sing-box batches inspected concurrently. Each instance still
	// handles batchSize nodes; only the WALL-CLOCK of the (mostly ping-timeout
	// bound) phase shrinks. Bandwidth stays bounded by globalSpeedSem, so this
	// speeds the phase up without choking the uplink.
	l7Conc := globalSettings.L7Concurrency
	if l7Conc <= 0 {
		l7Conc = 6
	}
	if l7Conc > totalBatches {
		l7Conc = totalBatches
	}

	fmt.Printf("│  L7 start · %d batches × %d nodes · %d parallel sing-box · %d global download slots\n",
		totalBatches, batchSize, l7Conc, cap(globalSpeedSem))

	var (
		finalNodes = make([]map[string]interface{}, 0, len(nodes)/3)
		mu         sync.Mutex
		wg         sync.WaitGroup
		fatalFlag  int32
		completed  int32
	)
	sem := make(chan struct{}, l7Conc)

	for i := 0; i < len(nodes); i += batchSize {
		if atomic.LoadInt32(&fatalFlag) == 1 {
			break
		}
		end := i + batchSize
		if end > len(nodes) {
			end = len(nodes)
		}
		batch := nodes[i:end]
		batchNum := (i / batchSize) + 1

		wg.Add(1)
		sem <- struct{}{}
		go func(b []map[string]interface{}, bn int) {
			defer wg.Done()
			defer func() { <-sem }()
			if atomic.LoadInt32(&fatalFlag) == 1 {
				// A sibling batch already hit a fatal (binary-missing) abort.
				// Count this batch's nodes so they are not silently dropped from
				// the L7 ledger (Total stays == Survived + Σfailures).
				l7StatsMu.Lock()
				l7Stats.SingboxCrash += len(b)
				l7StatsMu.Unlock()
				return
			}

			survivors, fatal := processSingboxRecursive(b, false, 0)
			if fatal {
				// sing-box is unrunnable (binary missing) — splitting cannot
				// help. Abort the phase instead of grinding every batch.
				if atomic.CompareAndSwapInt32(&fatalFlag, 0, 1) {
					fmt.Printf("│  L7 ABORT · sing-box could not be started (binary missing / unrunnable). Skipping remaining batches.\n")
				}
				return
			}

			mu.Lock()
			finalNodes = append(finalNodes, survivors...)
			mu.Unlock()

			done := int(atomic.AddInt32(&completed, 1))
			if done%20 == 0 || done == totalBatches {
				fmt.Printf("│  L7 %d/%d · batch#%d alive %d · [%s]\n",
					done, totalBatches, bn, len(survivors), l7Brief())
			}
		}(batch, batchNum)
	}
	wg.Wait()

	// Finalize L7 survived count
	l7StatsMu.Lock()
	l7Stats.Survived = len(finalNodes)
	l7StatsMu.Unlock()

	return finalNodes
}

// processSingboxRecursive inspects a batch, splitting in half on a (retryable)
// sing-box crash to isolate a poison node. The second return value is a FATAL
// flag: when true, sing-box itself is unrunnable (binary missing) and the
// caller must abort the whole phase rather than keep splitting.
//
// All crash telemetry is owned here (counted exactly once at the leaves) so it
// is not inflated by counting at every level of the split.
func processSingboxRecursive(
	batch []map[string]interface{},
	isChampion bool,
	depth int,
) ([]map[string]interface{}, bool) {
	if len(batch) == 0 {
		return nil, false
	}
	if depth > 3 {
		// Recursive splitting exhausted — nodes could not be checked
		l7StatsMu.Lock()
		l7Stats.SingboxCrash += len(batch)
		l7StatsMu.Unlock()
		return nil, false
	}

	survivors, crashed, fatal := processSingboxBatch(batch, isChampion)
	if fatal {
		// Environmental: sing-box cannot run at all. Count the batch and signal
		// abort up the stack — no point splitting.
		l7StatsMu.Lock()
		l7Stats.SingboxCrash += len(batch)
		l7StatsMu.Unlock()
		return nil, true
	}
	if crashed {
		if len(batch) == 1 {
			// Single poison node that crashes sing-box — drop it, but record it
			// so the loss is visible in telemetry (was silent before).
			l7StatsMu.Lock()
			l7Stats.SingboxCrash++
			l7StatsMu.Unlock()
			return nil, false
		}
		mid := len(batch) / 2
		left, lf := processSingboxRecursive(batch[:mid], isChampion, depth+1)
		if lf {
			return left, true
		}
		right, rf := processSingboxRecursive(batch[mid:], isChampion, depth+1)
		return append(left, right...), rf
	}
	return survivors, false
}

// processSingboxBatch runs one sing-box over the batch and returns
// (survivors, crashed, fatal). crashed=true means sing-box never became ready
// (retryable by splitting); fatal=true means the binary could not be started at
// all (environmental — caller should abort the phase).
func processSingboxBatch(
	batch []map[string]interface{},
	isChampion bool,
) ([]map[string]interface{}, bool, bool) {

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
	skipped := 0

	for i, node := range batch {
		readyOutbound, ok := node["ready_outbound"].(map[string]interface{})
		if !ok {
			// Node carries no usable outbound. Count it so the L7 ledger stays
			// balanced (Total == Survived + Σfailures); previously a mixed batch
			// silently lost these nodes from every counter.
			skipped++
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

	if skipped > 0 {
		l7StatsMu.Lock()
		l7Stats.ProtocolMismatch += skipped
		l7StatsMu.Unlock()
	}

	if firstValidPort == -1 || len(portToNode) == 0 {
		// Every node in this (sub-)batch lacked a valid outbound — already
		// counted above via `skipped`.
		return nil, false, false
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
		// Binary missing / unrunnable — fatal & environmental, not a per-node
		// fault. Signalled up so the phase aborts instead of splitting for hours.
		return nil, true, true
	}
	// Reap the process in a goroutine so the readiness loop can break the instant
	// sing-box dies (e.g. a poison outbound) instead of burning the full deadline.
	exited := make(chan struct{})
	go func() {
		_ = cmd.Wait()
		close(exited)
	}()
	defer func() {
		_ = cmd.Process.Kill()
		<-exited
	}()

	portReady := false
	deadline := time.Now().Add(8 * time.Second)
portWait:
	for time.Now().Before(deadline) {
		select {
		case <-exited:
			// sing-box died before binding — stop waiting immediately.
			break portWait
		default:
		}
		conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", firstValidPort), 300*time.Millisecond)
		if err == nil {
			conn.Close()
			portReady = true
			break
		}
		select {
		case <-exited:
			break portWait
		case <-time.After(100 * time.Millisecond):
		}
	}

	if !portReady {
		// Never became ready (crash or poison node) — retryable via split.
		// Crash telemetry is owned by processSingboxRecursive (counted at the
		// leaves) to avoid inflating it at every split level.
		return nil, true, false
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
		return nil, false, false
	}

	var wgSpeed sync.WaitGroup
	alive := make([]map[string]interface{}, 0, len(pingPassed))

	// Downloads are throttled by the package-global globalSpeedSem (sized by
	// speed_concurrency) rather than a per-batch semaphore, so running several
	// L7 batches in parallel never multiplies bandwidth contention on the
	// runner's single uplink (see AUDIT §2.4).
	minSpeed := globalSettings.MinSpeed
	if minSpeed <= 0 {
		minSpeed = 1.0
	}

	for port, node := range pingPassed {
		wgSpeed.Add(1)
		globalSpeedSem <- struct{}{}
		go func(p int, n map[string]interface{}) {
			defer wgSpeed.Done()
			defer func() { <-globalSpeedSem }()
			verifySSL := resolvePayloadSSL(n)
			speed, ok, reason := testHTTPSpeed(p, verifySSL, isChampion)
			// Speed is always recorded for sorting/labels; a failed
			// measurement records 0 without dropping the node (US-001).
			if ok {
				n["speed"] = speed
			} else {
				if _, exists := n["speed"]; !exists {
					n["speed"] = 0.0
				}
				// Track L7 speed test failure reason (telemetry only; US-C02).
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
			// Survival is gated on the L7 connectivity ping (already
			// passed). min_speed only drops a node when speed_as_filter
			// is explicitly enabled; otherwise it is a ranking signal.
			if globalSettings.SpeedAsFilter && (!ok || speed < minSpeed) {
				return
			}
			mu.Lock()
			alive = append(alive, n)
			mu.Unlock()
		}(port, node)
	}
	wgSpeed.Wait()

	return alive, false, false
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

	// HTTP timeout = maxLatency + 2s setup buffer. A larger buffer is pointless:
	// any node slower than maxLatency is rejected by the `lat > maxLatency` check
	// below anyway, so a bigger timeout only makes dead nodes hang longer. Two
	// URLs are tried sequentially, so a dead node costs at most ~2×this.
	client := getSocksClient(
		port,
		time.Duration(maxLatency+2000)*time.Millisecond,
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

// testHTTPSpeed measures throughput through the local SOCKS proxy. Returns
// (speed_mbps, ok, failure_reason). It does NOT apply the min_speed threshold —
// that decision lives in the caller and is only enforced when speed_as_filter
// is enabled (US-001). failure_reason ∈ {"", "timeout", "tls_error",
// "too_slow" (measurement invalid), "http_error"}.
func testHTTPSpeed(port int, verifySSL bool, isChampion bool) (float64, bool, string) {
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

	// Reset the clock AFTER the response headers arrive so throughput is measured
	// over body transfer only. Including the SOCKS dial + remote TCP + TLS
	// handshake + TTFB (which all scale with the node's latency, already captured
	// by testHTTPPing) systematically deflated the figure — worst for fast,
	// high-latency nodes — and under speed_as_filter dropped genuinely good nodes.
	tStart = time.Now()

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

	// Minimum bytes needed to trust the measurement. The champion round downloads
	// 10 MB to refine the top-N; if it delivers under 1 MB the sample is too
	// truncated (typically a mid-transfer stall) to be representative, so report
	// "too_slow" and let the caller keep the earlier L7 figure instead of
	// overwriting a fast node with a near-zero stalled-download value. 1 MB only
	// rejects nodes under ~0.3 Mbps, whose retained L7 number is fine anyway.
	minValid := 256 * 1024
	if isChampion {
		minValid = 1024 * 1024
	}
	if total < minValid {
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

	limit := globalSettings.ChampionTopN
	if limit <= 0 {
		limit = 20
	}
	if len(nodes) < limit {
		limit = len(nodes)
	}
	fmt.Printf("├─ %-16s10MB speed test · top-%d\n", "champion", limit)

	for i := 0; i < limit; i++ {
		res, crashed, _ := processSingboxBatch(
			[]map[string]interface{}{nodes[i]}, true,
		)
		if !crashed && len(res) > 0 {
			if s, ok := res[0]["speed"].(float64); ok {
				nodes[i]["speed"] = s
			}
		}
	}
}
