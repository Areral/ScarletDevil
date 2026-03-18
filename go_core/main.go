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
	ConnectivityUrls[]string `json:"connectivity_urls"`
	SpeedtestUrl     string   `json:"speedtest_url"`
	ChampionTestUrl  string   `json:"champion_test_url"`
	BatchSize        int      `json:"batch_size"`
}

type InputPayload struct {
	Settings EngineSettings           `json:"settings"`
	Nodes   []map[string]interface{} `json:"nodes"`
}

var forbiddenNetworks[]*net.IPNet
var globalSettings EngineSettings

func init() {
	cidrs :=[]string{
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

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: ./angra_core <input.json> <output.json>")
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

	fmt.Printf("► [ANGRA-GO]: Payload загружен. Узлов: %d | Таймаут: %d мс\n", len(nodes), globalSettings.MaxLatency)

	l4Nodes := runL4Phase(nodes)
	fmt.Printf("✔ [ANGRA-GO L4]: Отбраковано %d, Выжило: %d\n", len(nodes)-len(l4Nodes), len(l4Nodes))

	if len(l4Nodes) == 0 {
		os.WriteFile(os.Args[2], []byte("[]"), 0644)
		return
	}

	l7Nodes := runL7Phase(l4Nodes)
	fmt.Printf("✔ [ANGRA-GO L7]: HTTP-валидация завершена. Выжило: %d\n", len(l7Nodes))

	if len(l7Nodes) > 0 {
		runChampionPhase(l7Nodes)
	}

	outData, _ := json.Marshal(l7Nodes)
	os.WriteFile(os.Args[2], outData, 0644)
}

func runL4Phase(nodes []map[string]interface{})[]map[string]interface{} {
	var wg sync.WaitGroup
	var mu sync.Mutex
	valid := make([]map[string]interface{}, 0)
	sem := make(chan struct{}, 2000)

	for _, node := range nodes {
		wg.Add(1)
		sem <- struct{}{}
		go func(n map[string]interface{}) {
			defer wg.Done()
			defer func() { <-sem }()
			if checkL4(n) {
				mu.Lock()
				valid = append(valid, n)
				mu.Unlock()
			}
		}(node)
	}
	wg.Wait()
	return valid
}

func checkL4(node map[string]interface{}) bool {
	protocol, _ := node["protocol"].(string)
	if protocol == "hysteria2" || protocol == "quic" { return true }
	
	config, ok := node["config"].(map[string]interface{})
	if !ok { return false }

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
		if err != nil || len(ips) == 0 { return false }
		for _, ip := range ips {
			if ip.To4() != nil {
				targetIP = ip
				break
			}
		}
		if targetIP == nil { targetIP = ips[0] }
	}

	if targetIP.IsLoopback() || targetIP.IsPrivate() || targetIP.IsUnspecified() { return false }

	nodeType, _ := config["type"].(string)
	nt := strings.ToLower(nodeType)
	isCdnAllowed := nt == "ws" || nt == "websocket" || nt == "httpupgrade" || nt == "xhttp" || nt == "grpc"
	if !isCdnAllowed {
		for _, network := range forbiddenNetworks {
			if network.Contains(targetIP) { return false }
		}
	}

	address := fmt.Sprintf("[%s]:%d", targetIP.String(), port)
	if targetIP.To4() != nil {
		address = fmt.Sprintf("%s:%d", targetIP.String(), port)
	}

	conn, err := net.DialTimeout("tcp", address, 2*time.Second)
	if err != nil { return false }
	conn.Close()
	return true
}

func runL7Phase(nodes []map[string]interface{}) []map[string]interface{} {
	batchSize := globalSettings.BatchSize
	if batchSize <= 0 { batchSize = 100 }
	var finalNodes []map[string]interface{}

	for i := 0; i < len(nodes); i += batchSize {
		end := i + batchSize
		if end > len(nodes) { end = len(nodes) }
		batch := nodes[i:end]
		
		fmt.Printf("► [ANGRA-GO L7]: Обработка батча %d/%d (размер: %d)\n", (i/batchSize)+1, (len(nodes)+batchSize-1)/batchSize, len(batch))
		survivors := processSingboxBatch(batch)
		finalNodes = append(finalNodes, survivors...)
	}
	return finalNodes
}

func processSingboxBatch(batch []map[string]interface{}) []map[string]interface{} {
	basePort := 10000
	inbounds := make([]map[string]interface{}, 0)
	outbounds := make([]map[string]interface{}, 0)
	rules := []map[string]interface{}{
		{"protocol": "dns", "outbound": "direct"},
		{"ip_cidr":[]string{"127.0.0.0/8", "10.0.0.0/8", "192.168.0.0/16"}, "outbound": "block"},
	}

	validMap := make(map[int]map[string]interface{})

	for i, node := range batch {
		readyOutbound, ok := node["ready_outbound"].(map[string]interface{})
		if !ok { continue }

		tag := fmt.Sprintf("proxy-%d", i)
		readyOutbound["tag"] = tag
		
		localPort := basePort + i
		inbounds = append(inbounds, map[string]interface{}{
			"type": "socks", "tag": fmt.Sprintf("in-%d", i),
			"listen": "127.0.0.1", "listen_port": localPort,
		})
		outbounds = append(outbounds, readyOutbound)
		rules = append(rules, map[string]interface{}{
			"inbound":[]string{fmt.Sprintf("in-%d", i)}, "outbound": tag,
		})
		validMap[localPort] = node
	}

	outbounds = append(outbounds, map[string]interface{}{"type": "direct", "tag": "direct"})
	outbounds = append(outbounds, map[string]interface{}{"type": "block", "tag": "block"})

	configBytes, _ := json.Marshal(map[string]interface{}{
		"log": map[string]interface{}{"level": "fatal", "output": "discard"},
		"inbounds": inbounds, "outbounds": outbounds,
		"route": map[string]interface{}{"rules": rules, "final": "block", "auto_detect_interface": true},
	})
	
	configPath := "go_temp.json"
	os.WriteFile(configPath, configBytes, 0644)
	defer os.Remove(configPath)

	cmd := exec.Command("sing-box", "run", "-c", configPath)
	if err := cmd.Start(); err != nil { return nil }
	defer func() { cmd.Process.Kill(); cmd.Wait() }()
	time.Sleep(1 * time.Second)

	var wgPing sync.WaitGroup
	var mu sync.Mutex
	pingPassed := make(map[int]map[string]interface{})
	semPing := make(chan struct{}, 25)

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

	if len(pingPassed) == 0 { return nil }

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
			if speed, ok := testHTTPSpeed(p, verifySSL); ok {
				n["speed"] = speed
				mu.Lock()
				alive = append(alive, n)
				mu.Unlock()
			}
		}(port, node)
	}
	wgSpeed.Wait()

	return alive
}

func getSocksClient(port int, timeout time.Duration, verifySSL bool) *http.Client {
	dialer, _ := proxy.SOCKS5("tcp", fmt.Sprintf("127.0.0.1:%d", port), nil, proxy.Direct)
	transport := &http.Transport{
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			return dialer.Dial(network, addr)
		},
		TLSClientConfig: &tls.Config{InsecureSkipVerify: !verifySSL},
		DisableKeepAlives: true,
	}
	return &http.Client{Transport: transport, Timeout: timeout}
}

func testHTTPPing(port int) (int, bool) {
	client := getSocksClient(port, 5*time.Second, false)
	urls := globalSettings.ConnectivityUrls
	if len(urls) == 0 { urls =[]string{"http://cp.cloudflare.com/generate_204"} }
	
	targetUrl := urls[rand.Intn(len(urls))]
	req, _ := http.NewRequest("GET", targetUrl, nil)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

	t0 := time.Now()
	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != 204 { return 0, false }
	defer resp.Body.Close()
	
	body, _ := io.ReadAll(resp.Body)
	if len(body) > 0 { return 0, false }

	lat := int(time.Since(t0).Milliseconds())
	if lat > globalSettings.MaxLatency { return 0, false }
	return lat, true
}

func testHTTPSpeed(port int, verifySSL bool) (float64, bool) {
	client := getSocksClient(port, 5*time.Second, verifySSL)
	url := globalSettings.SpeedtestUrl
	if url == "" { url = "https://speed.cloudflare.com" }

	req, _ := http.NewRequest("HEAD", url, nil)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

	t0 := time.Now()
	resp, err := client.Do(req)
	if err != nil || (resp.StatusCode < 200 || resp.StatusCode >= 500) { return 0, false }
	defer resp.Body.Close()

	dur := time.Since(t0).Seconds()
	if dur < 0.05 { dur = 0.05 }
	
	speed := 15.0 / dur
	if speed < globalSettings.MinSpeed { return 0, false }
	if speed > 3000.0 { speed = 3000.0 }
	return speed, true
}

func resolvePayloadSSL(node map[string]interface{}) bool {
	sec := ""
	config, ok := node["config"].(map[string]interface{})
	if ok {
		if s, ok := config["security"].(string); ok { sec = s }
	}
	
	if sec == "reality" { return true }
	
	if ok {
		if rawMeta, ok := config["raw_meta"].(map[string]interface{}); ok {
			for k, v := range rawMeta {
				kl := strings.ToLower(k)
				if kl == "allowinsecure" || kl == "insecure" {
					if fmt.Sprintf("%v", v) == "1" || fmt.Sprintf("%v", v) == "true" { return false }
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
	if len(nodes) < 5 { limit = len(nodes) }
	
	fmt.Printf("►[ANGRA-GO CHAMPION]: Старт 50MB спидтеста для Топ-%d\n", limit)

	for i := 0; i < limit; i++ {
		speed := performHeavySpeedtest(nodes[i])
		if speed > 0 { nodes[i]["speed"] = speed }
	}
}

func performHeavySpeedtest(node map[string]interface{}) float64 {
	readyOutbound, ok := node["ready_outbound"].(map[string]interface{})
	if !ok { return 0 }
	readyOutbound["tag"] = "proxy-0"

	configBytes, _ := json.Marshal(map[string]interface{}{
		"log": map[string]interface{}{"level": "fatal", "output": "discard"},
		"inbounds": []map[string]interface{}{{"type": "socks", "tag": "in-0", "listen": "127.0.0.1", "listen_port": 15000}},
		"outbounds": []map[string]interface{}{readyOutbound, {"type": "direct", "tag": "direct"}},
		"route": map[string]interface{}{"rules": []map[string]interface{}{{"inbound":[]string{"in-0"}, "outbound": "proxy-0"}}},
	})
	os.WriteFile("go_temp_champ.json", configBytes, 0644)
	defer os.Remove("go_temp_champ.json")

	cmd := exec.Command("sing-box", "run", "-c", "go_temp_champ.json")
	if err := cmd.Start(); err != nil { return 0 }
	defer func() { cmd.Process.Kill(); cmd.Wait() }()
	time.Sleep(1 * time.Second)

	client := getSocksClient(15000, 30*time.Second, resolvePayloadSSL(node))
	url := globalSettings.ChampionTestUrl
	if url == "" { url = "https://speed.cloudflare.com/__down?bytes=50000000" }

	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

	t0 := time.Now()
	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != 200 { return 0 }
	defer resp.Body.Close()

	buf := make([]byte, 65536)
	total := 0
	for {
		n, err := resp.Body.Read(buf)
		total += n
		if err != nil { break }
		if total >= 50*1024*1024 { break }
	}

	dur := time.Since(t0).Seconds()
	if dur < 0.1 { dur = 0.1 }
	return float64(total*8) / (dur * 1000000.0)
}
