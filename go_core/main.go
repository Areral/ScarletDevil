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

type ProxyConfig struct {
	Server  string                 `json:"server"`
	Port    int                    `json:"port"`
	Type    string                 `json:"type"`
	Security string                `json:"security,omitempty"`
	RawMeta map[string]interface{} `json:"raw_meta,omitempty"`
}

type ProxyNode struct {
	Protocol  string      `json:"protocol"`
	Config    ProxyConfig `json:"config"`
	RawURI    string      `json:"raw_uri"`
	Latency   int         `json:"latency"`
	Speed     float64     `json:"speed"`
	Country   string      `json:"country"`
	IsBS      bool        `json:"is_bs"`
	StrictID  string      `json:"strict_id"`
	SourceUrl string      `json:"source_url"`
}

type InputPayload struct {
	Settings EngineSettings           `json:"settings"`
	Nodes    []map[string]interface{} `json:"nodes"`
}

var (
	globalSettings    EngineSettings
	forbiddenNetworks []*net.IPNet
	championBytes     = 10 * 1024 * 1024
	normalBytes       = 1 * 1024 * 1024
	chunkSize         = 65536
	portCounter       = 10000
	portMutex         sync.Mutex
)

func init() {
	rand.Seed(time.Now().UnixNano())
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
		os.Exit(1)
	}

	data, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}

	var payload InputPayload
	if err := json.Unmarshal(data, &payload); err != nil {
		panic(err)
	}

	globalSettings = payload.Settings
	nodes := payload.Nodes

	l4Nodes := runL4Phase(nodes)
	fmt.Printf("✔[ФИЛЬТРАЦИЯ L4]: Отбраковано %d, Выжило: %d\n", len(nodes)-len(l4Nodes), len(l4Nodes))

	if len(l4Nodes) == 0 {
		os.WriteFile(os.Args[2], []byte("[]"), 0644)
		return
	}

	l7Nodes := runL7Phase(l4Nodes)
	fmt.Printf("✔ [ИНСПЕКЦИЯ L7]: Завершена. Выжило узлов: %d\n", len(l7Nodes))

	if len(l7Nodes) > 0 {
		runChampionPhase(l7Nodes)
	}

	outData, _ := json.Marshal(l7Nodes)
	os.WriteFile(os.Args[2], outData, 0644)
}

func runL4Phase(nodes []map[string]interface{}) []map[string]interface{} {
	validNodes := make([]map[string]interface{}, 0)
	var mu sync.Mutex

	sem := make(chan struct{}, 75)
	scanChunkSize := 500

	for i := 0; i < len(nodes); i += scanChunkSize {
		end := i + scanChunkSize
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

				if checkL4(n) {
					mu.Lock()
					validNodes = append(validNodes, n)
					mu.Unlock()
				}
			}(node)
		}
		wg.Wait()
	}
	return validNodes
}

func checkL4(node map[string]interface{}) bool {
	protocol, _ := node["protocol"].(string)
	if protocol == "hysteria2" || protocol == "quic" {
		return true
	}

	config, ok := node["config"].(map[string]interface{})
	if !ok {
		return false
	}

	hostRaw, _ := config["server"].(string)
	host := strings.Trim(hostRaw, "[]")
	portFloat, _ := config["port"].(float64)
	port := int(portFloat)

	var targetIP net.IP
	parsedIP := net.ParseIP(host)

	if parsedIP != nil {
		targetIP = parsedIP
	} else {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		ips, err := net.DefaultResolver.LookupIP(ctx, "ip", host)
		if err != nil || len(ips) == 0 {
			return false
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
		return false
	}

	nodeType, _ := config["type"].(string)
	nt := strings.ToLower(nodeType)
	isCdnAllowed := nt == "ws" || nt == "websocket" || nt == "httpupgrade" || nt == "xhttp" || nt == "grpc"
	if !isCdnAllowed {
		for _, network := range forbiddenNetworks {
			if network.Contains(targetIP) {
				return false
			}
		}
	}

	address := fmt.Sprintf("[%s]:%d", targetIP.String(), port)
	if targetIP.To4() != nil {
		address = fmt.Sprintf("%s:%d", targetIP.String(), port)
	}

	time.Sleep(time.Duration(rand.Float64()*200) * time.Millisecond)

	conn, err := net.DialTimeout("tcp", address, 3500*time.Millisecond)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

func runL7Phase(nodes []map[string]interface{}) []map[string]interface{} {
	batchSize := globalSettings.BatchSize
	if batchSize <= 0 {
		batchSize = 100
	}
	totalBatches := (len(nodes) + batchSize - 1) / batchSize
	finalNodes := make([]map[string]interface{}, 0)

	for i := 0; i < len(nodes); i += batchSize {
		end := i + batchSize
		if end > len(nodes) {
			end = len(nodes)
		}
		batch := nodes[i:end]
		batchNum := (i / batchSize) + 1

		survivors := processSingboxRecursive(batch, false, 0)
		if len(survivors) > 0 {
			finalNodes = append(finalNodes, survivors...)
		}

		if batchNum%5 == 0 || batchNum == totalBatches {
			fmt.Printf("► [ИНСПЕКЦИЯ L7]: Батч %d/%d завершен (Выжило: %d)\n", batchNum, totalBatches, len(survivors))
		}
	}
	return finalNodes
}

func processSingboxRecursive(batch []map[string]interface{}, isChampion bool, depth int) []map[string]interface{} {
	if len(batch) == 0 {
		return []map[string]interface{}{}
	}
	if depth > 3 {
		return []map[string]interface{}{}
	}

	survivors, crashed := processSingboxBatch(batch, isChampion)
	if crashed {
		if len(batch) == 1 {
			return []map[string]interface{}{}
		}

		mid := len(batch) / 2
		left := processSingboxRecursive(batch[:mid], isChampion, depth+1)
		right := processSingboxRecursive(batch[mid:], isChampion, depth+1)
		return append(left, right...)
	}

	return survivors
}

func processSingboxBatch(batch []map[string]interface{}, isChampion bool) ([]map[string]interface{}, bool) {
	basePort := getNextBasePort(len(batch))
	inbounds := make([]map[string]interface{}, 0)
	outbounds := make([]map[string]interface{}, 0)
	rules := []map[string]interface{}{
		{"protocol": "dns", "outbound": "direct"},
		{"ip_cidr": []string{"127.0.0.0/8", "10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12", "::1/128", "fc00::/7", "fe80::/10"}, "outbound": "block"},
	}

	validMap := make(map[int]map[string]interface{})

	for i, node := range batch {
		readyOutbound, ok := node["ready_outbound"].(map[string]interface{})
		if !ok {
			continue
		}

		tag := fmt.Sprintf("proxy-%d", i)
		readyOutbound["tag"] = tag

		localPort := basePort + i
		inbounds = append(inbounds, map[string]interface{}{
			"type": "socks", "tag": fmt.Sprintf("in-%d", i),
			"listen": "127.0.0.1", "listen_port": localPort,
		})
		outbounds = append(outbounds, readyOutbound)
		rules = append(rules, map[string]interface{}{
			"inbound": []string{fmt.Sprintf("in-%d", i)}, "outbound": tag,
		})
		validMap[localPort] = node
	}

	if len(validMap) == 0 {
		return []map[string]interface{}{}, false
	}

	outbounds = append(outbounds, map[string]interface{}{"type": "direct", "tag": "direct"})
	outbounds = append(outbounds, map[string]interface{}{"type": "block", "tag": "block"})

	configMap := map[string]interface{}{
		"log": map[string]interface{}{"level": "fatal", "output": "discard"},
		"dns": map[string]interface{}{
			"servers": []map[string]interface{}{
				{"tag": "remote-doh", "address": "https://1.1.1.1/dns-query", "detour": "direct"},
				{"tag": "fallback-doh", "address": "https://dns.quad9.net/dns-query", "detour": "direct"},
			},
			"independent_cache": true,
		},
		"inbounds":  inbounds,
		"outbounds": outbounds,
		"route": map[string]interface{}{
			"rules": rules, "final": "block", "auto_detect_interface": true,
		},
	}

	configBytes, _ := json.Marshal(configMap)
	configPath := fmt.Sprintf("run_%d.json", basePort)
	os.WriteFile(configPath, configBytes, 0644)
	defer os.Remove(configPath)

	cmd := exec.Command("sing-box", "run", "-c", configPath)
	if err := cmd.Start(); err != nil {
		return nil, true
	}
	defer func() {
		cmd.Process.Kill()
		cmd.Wait()
	}()

	portReady := false
	for start := time.Now(); time.Since(start) < 5*time.Second; {
		conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", basePort), 300*time.Millisecond)
		if err == nil {
			conn.Close()
			portReady = true
			break
		}
		time.Sleep(100 * time.Millisecond)
	}

	if !portReady {
		return nil, true
	}
	time.Sleep(500 * time.Millisecond)

	var wgPing sync.WaitGroup
	var mu sync.Mutex
	pingPassed := make(map[int]map[string]interface{})
	semPing := make(chan struct{}, 100)

	for port, node := range validMap {
		wgPing.Add(1)
		semPing <- struct{}{}

		go func(p int, n map[string]interface{}) {
			defer wgPing.Done()
			defer func() { <-semPing }()

			if lat, ok := testHTTPPing(p); ok {
				n["latency"] = lat
				mu.Lock()
				pingPassed[p] = n
				mu.Unlock()
			}
		}(port, node)
	}
	wgPing.Wait()

	if len(pingPassed) == 0 {
		return nil, false
	}

	var wgSpeed sync.WaitGroup
	alive := make([]map[string]interface{}, 0)
	semSpeed := make(chan struct{}, 10)

	for port, node := range pingPassed {
		wgSpeed.Add(1)
		semSpeed <- struct{}{}

		go func(p int, n map[string]interface{}) {
			defer wgSpeed.Done()
			defer func() { <-semSpeed }()

			verifySSL := resolvePayloadSSL(n)
			if speed, ok := testHTTPSpeed(p, verifySSL, isChampion); ok {
				n["speed"] = speed
				mu.Lock()
				alive = append(alive, n)
				mu.Unlock()
			}
		}(port, node)
	}
	wgSpeed.Wait()

	return alive, false
}

func getSocksClient(port int, timeout time.Duration, verifySSL bool) *http.Client {
	dialer, err := proxy.SOCKS5("tcp", fmt.Sprintf("127.0.0.1:%d", port), nil, proxy.Direct)
	if err != nil {
		dialer = proxy.Direct
	}
	transport := &http.Transport{
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			return dialer.Dial(network, addr)
		},
		TLSClientConfig:   &tls.Config{InsecureSkipVerify: !verifySSL},
		DisableKeepAlives: true,
	}
	return &http.Client{Transport: transport, Timeout: timeout}
}

func testHTTPPing(port int) (int, bool) {
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

	client := getSocksClient(port, time.Duration(maxLatency+1500)*time.Millisecond, false)

	for _, targetUrl := range urls {
		t0 := time.Now()

		req, err := http.NewRequest("GET", targetUrl, nil)
		if err != nil {
			continue
		}
		req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

		resp, err := client.Do(req)
		if err != nil {
			continue
		}

		io.Copy(io.Discard, io.LimitReader(resp.Body, 512))
		resp.Body.Close()

		if resp.StatusCode != 204 {
			continue
		}

		lat := int(time.Since(t0).Milliseconds())
		if lat > maxLatency {
			return 0, false
		}
		return lat, true
	}
	return 0, false
}

func testHTTPSpeed(port int, verifySSL bool, isChampion bool) (float64, bool) {
	minSpeed := globalSettings.MinSpeed
	if minSpeed <= 0 {
		minSpeed = 1.0
	}

	if isChampion {
		timeout := 25 * time.Second
		url := globalSettings.ChampionTestUrl
		if url == "" {
			url = "https://speed.cloudflare.com/__down?bytes=10485760"
		}

		client := getSocksClient(port, timeout, verifySSL)
		req, err := http.NewRequest("GET", url, nil)
		if err != nil {
			return 0, false
		}
		req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

		tStart := time.Now()
		resp, err := client.Do(req)
		if err != nil {
			return 0, false
		}
		defer resp.Body.Close()

		if resp.StatusCode == 429 || resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return 0, false
		}

		buf := make([]byte, chunkSize)
		total := 0
		for {
			n, errRead := resp.Body.Read(buf)
			total += n

			dur := time.Since(tStart).Seconds()
			if dur > 3.5 && total < 65536 {
				return 0, false
			}
			if total >= championBytes || errRead != nil {
				break
			}
		}

		if total < 256*1024 {
			return 0, false
		}

		dur := time.Since(tStart).Seconds()
		if dur < 0.1 {
			dur = 0.1
		}
		speed := (float64(total) * 8.0) / (dur * 1000000.0)
		if speed > 3000.0 {
			speed = 3000.0
		}
		if speed < minSpeed {
			return 0, false
		}
		return speed, true

	} else {
		timeout := 15 * time.Second
		dlUrl := globalSettings.SpeedtestUrl
		if dlUrl == "" || dlUrl == "https://speed.cloudflare.com" {
			dlUrl = "https://speed.cloudflare.com/__down?bytes=1048576"
		}

		client := getSocksClient(port, timeout, verifySSL)
		req, err := http.NewRequest("GET", dlUrl, nil)
		if err != nil {
			return 0, false
		}
		req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

		tStart := time.Now()
		resp, err := client.Do(req)
		if err != nil {
			return 0, false
		}
		defer resp.Body.Close()

		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return 0, false
		}

		buf := make([]byte, chunkSize)
		total := 0
		for {
			n, errRead := resp.Body.Read(buf)
			total += n
			if total >= normalBytes || errRead != nil {
				break
			}
		}

		if total < 256*1024 {
			return 0, false
		}

		dur := time.Since(tStart).Seconds()
		if dur < 0.05 {
			dur = 0.05
		}
		speed := (float64(total) * 8.0) / (dur * 1000000.0)
		if speed > 3000.0 {
			speed = 3000.0
		}
		if speed < minSpeed {
			return 0, false
		}
		return speed, true
	}
}

func resolvePayloadSSL(node map[string]interface{}) bool {
	sec := ""
	config, ok := node["config"].(map[string]interface{})
	if ok {
		if s, ok := config["security"].(string); ok {
			sec = s
		}
	}
	if sec == "reality" {
		return true
	}

	if ok {
		if rawMeta, ok := config["raw_meta"].(map[string]interface{}); ok {
			for k, v := range rawMeta {
				kl := strings.ToLower(k)
				if kl == "allowinsecure" || kl == "insecure" {
					if fmt.Sprintf("%v", v) == "1" || fmt.Sprintf("%v", v) == "true" || fmt.Sprintf("%v", v) == "yes" {
						return false
					}
				}
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
	if len(nodes) < 5 {
		limit = len(nodes)
	}

	fmt.Printf("►[ANGRA-GO CHAMPION]: Старт спидтеста для Топ-%d\n", limit)

	for i := 0; i < limit; i++ {
		res, crashed := processSingboxBatch([]map[string]interface{}{nodes[i]}, true)
		if !crashed && len(res) > 0 {
			nodes[i]["speed"] = res[0]["speed"]
		}
	}
}
