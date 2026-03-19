// --- START OF FILE go_core/main.go ---
package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/base64"
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

type ProxyConfig struct {
	Server       string                 `json:"server"`
	Port         int                    `json:"port"`
	Type         string                 `json:"type"`
	UUID         string                 `json:"uuid,omitempty"`
	Password     string                 `json:"password,omitempty"`
	Method       string                 `json:"method,omitempty"`
	Security     string                 `json:"security,omitempty"`
	Path         string                 `json:"path,omitempty"`
	Host         string                 `json:"host,omitempty"`
	SNI          string                 `json:"sni,omitempty"`
	FP           string                 `json:"fp,omitempty"`
	ALPN         string                 `json:"alpn,omitempty"`
	PBK          string                 `json:"pbk,omitempty"`
	SID          string                 `json:"sid,omitempty"`
	Flow         string                 `json:"flow,omitempty"`
	ServiceName  string                 `json:"serviceName,omitempty"`
	Aid          int                    `json:"aid,omitempty"`
	Obfs         string                 `json:"obfs,omitempty"`
	ObfsPassword string                 `json:"obfs-password,omitempty"`
	RawMeta      map[string]interface{} `json:"raw_meta,omitempty"`
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
	Settings EngineSettings `json:"settings"`
	Nodes[]ProxyNode    `json:"nodes"`
}

var (
	globalSettings    EngineSettings
	geoCache          sync.Map
	forbiddenNetworks[]*net.IPNet
	championBytes     = 10 * 1024 * 1024
	normalBytes       = 3 * 1024 * 1024
	chunkSize         = 65536
	batchHardTimeout  = 600 * time.Second
	portCounter       = 10000
	portMutex         sync.Mutex
)

func init() {
	rand.Seed(time.Now().UnixNano())
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

// ============================
// ОСНОВНАЯ ТОЧКА ВХОДА (main)
// ============================
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
	fmt.Printf("✔ [ФИЛЬТРАЦИЯ L4]: Завершено. Отбраковано: %d | Передано в Sing-box: %d\n", len(nodes)-len(l4Nodes), len(l4Nodes))

	if len(l4Nodes) == 0 {
		os.WriteFile(os.Args[2], []byte("[]"), 0644)
		return
	}

	l7Nodes := runL7Phase(l4Nodes)
	fmt.Printf("✔ [ИНСПЕКЦИЯ L7]: Полностью завершена. Выжило узлов: %d\n", len(l7Nodes))

	if len(l7Nodes) > 0 {
		runChampionPhase(l7Nodes)
	}

	outData, _ := json.Marshal(l7Nodes)
	os.WriteFile(os.Args[2], outData, 0644)
}

// =========================================
// L4 ФИЛЬТРАЦИЯ (Семафор 75, Джиттер 0.2с)
// =========================================
func runL4Phase(nodes []ProxyNode)[]ProxyNode {
	validNodes := make([]ProxyNode, 0)
	var mu sync.Mutex

	sem := make(chan struct{}, 75)
	chunkSize := 500

	for i := 0; i < len(nodes); i += chunkSize {
		end := i + chunkSize
		if end > len(nodes) {
			end = len(nodes)
		}
		chunk := nodes[i:end]

		var wg sync.WaitGroup
		for _, node := range chunk {
			wg.Add(1)
			go func(n ProxyNode) {
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

func checkL4(node ProxyNode) bool {
	if node.Protocol == "hysteria2" || node.Protocol == "quic" {
		return true
	}
	host := strings.Trim(node.Config.Server, "[]")
	port := node.Config.Port

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

	nt := strings.ToLower(node.Config.Type)
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

// =========================
// L7 ФИЛЬТРАЦИЯ (Sing-box)
// =========================
func runL7Phase(nodes []ProxyNode)[]ProxyNode {
	batchSize := globalSettings.BatchSize
	if batchSize <= 0 {
		batchSize = 100
	}
	totalBatches := (len(nodes) + batchSize - 1) / batchSize
	var finalNodes[]ProxyNode

	for i := 0; i < len(nodes); i += batchSize {
		end := i + batchSize
		if end > len(nodes) {
			end = len(nodes)
		}
		batch := nodes[i:end]
		batchNum := (i / batchSize) + 1

		survivors := processSingboxBatch(batch, false)
		finalNodes = append(finalNodes, survivors...)

		if batchNum%5 == 0 || batchNum == totalBatches {
			fmt.Printf("►[ИНСПЕКЦИЯ L7]: Батч %d/%d завершен (Выжило: %d)\n", batchNum, totalBatches, len(survivors))
		}
	}
	return finalNodes
}

func isConfigValid(configBytes[]byte) bool {
	configPath := fmt.Sprintf("check_%d.json", rand.Intn(100000))
	os.WriteFile(configPath, configBytes, 0644)
	defer os.Remove(configPath)

	cmd := exec.Command("sing-box", "check", "-c", configPath)
	err := cmd.Run()
	return err == nil
}

func processSingboxBatch(batch[]ProxyNode, isChampion bool) []ProxyNode {
	basePort := getNextBasePort(len(batch))
	inbounds := make([]map[string]interface{}, 0)
	outbounds := make([]map[string]interface{}, 0)
	rules := []map[string]interface{}{
		{"protocol": "dns", "outbound": "direct"},
		{"ip_cidr":[]string{"127.0.0.0/8", "10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12", "::1/128", "fc00::/7", "fe80::/10"}, "outbound": "block"},
	}

	validMap := make(map[int]ProxyNode)

	for i, node := range batch {
		tag := fmt.Sprintf("proxy-%d", i)
		ob := buildOutbound(node, tag)
		if ob == nil {
			continue
		}

		localPort := basePort + i
		inbounds = append(inbounds, map[string]interface{}{
			"type": "socks", "tag": fmt.Sprintf("in-%d", i),
			"listen": "127.0.0.1", "listen_port": localPort,
		})
		outbounds = append(outbounds, ob)
		rules = append(rules, map[string]interface{}{
			"inbound":[]string{fmt.Sprintf("in-%d", i)}, "outbound": tag,
		})
		validMap[localPort] = node
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

	if !isConfigValid(configBytes) {
		return nil
	}

	configPath := fmt.Sprintf("run_%d.json", basePort)
	os.WriteFile(configPath, configBytes, 0644)
	defer os.Remove(configPath)

	cmd := exec.Command("sing-box", "run", "-c", configPath)
	if err := cmd.Start(); err != nil {
		return nil
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
		return nil
	}
	time.Sleep(1 * time.Second)

	var wgPing sync.WaitGroup
	var mu sync.Mutex
	pingPassed := make(map[int]ProxyNode)
	semPing := make(chan struct{}, 100)

	delay := 0.0
	for port, node := range validMap {
		wgPing.Add(1)
		semPing <- struct{}{}
		
		go func(p int, n ProxyNode, d float64) {
			defer wgPing.Done()
			defer func() { <-semPing }()
			
			if lat, ok := testHTTPPing(p, d); ok {
				n.Latency = lat
				mu.Lock()
				pingPassed[p] = n
				mu.Unlock()
			}
		}(port, node, delay)
		delay += 0.01
	}
	wgPing.Wait()

	if len(pingPassed) == 0 {
		return nil
	}

	var wgSpeed sync.WaitGroup
	alive := make([]ProxyNode, 0)
	semSpeed := make(chan struct{}, 6)

	for port, node := range pingPassed {
		wgSpeed.Add(1)
		semSpeed <- struct{}{}
		
		go func(p int, n ProxyNode) {
			defer wgSpeed.Done()
			defer func() { <-semSpeed }()
			
			if speed, country, ok := testHTTPSpeed(p, n.StrictID, isChampion); ok {
				n.Speed = speed
				n.Country = country
				mu.Lock()
				alive = append(alive, n)
				mu.Unlock()
			}
		}(port, node)
	}
	wgSpeed.Wait()

	return alive
}

func buildOutbound(n ProxyNode, tag string) map[string]interface{} {
	c := n.Config
	base := map[string]interface{}{"tag": tag, "server": c.Server, "server_port": c.Port}

	switch n.Protocol {
	case "vless":
		if c.UUID == "" { return nil }
		base["type"] = "vless"
		base["uuid"] = c.UUID
		if c.Flow != "" { base["flow"] = c.Flow }
	case "vmess":
		if c.UUID == "" { return nil }
		base["type"] = "vmess"
		base["uuid"] = c.UUID
		base["security"] = "auto"
		base["alter_id"] = c.Aid
	case "trojan":
		base["type"] = "trojan"
		base["password"] = c.Password
	case "ss":
		base["type"] = "shadowsocks"
		base["method"] = strings.ToLower(c.Method)
		base["password"] = c.Password
	case "hysteria2":
		base["type"] = "hysteria2"
		base["password"] = c.Password
		if c.Obfs != "" {
			base["obfs"] = map[string]interface{}{"type": c.Obfs, "password": c.ObfsPassword}
		}
	default:
		return nil
	}

	nt := strings.ToLower(c.Type)
	if nt == "ws" || nt == "websocket" {
		path := c.Path
		if path == "" { path = "/" }
		tr := map[string]interface{}{"type": "ws", "path": path}
		if c.Host != "" { tr["headers"] = map[string]interface{}{"Host": c.Host} }
		base["transport"] = tr
	} else if nt == "grpc" {
		sn := c.ServiceName
		if sn == "" { sn = c.Path }
		base["transport"] = map[string]interface{}{"type": "grpc", "service_name": sn}
	} else if nt == "httpupgrade" || nt == "xhttp" {
		path := c.Path
		if path == "" { path = "/" }
		tr := map[string]interface{}{"type": "httpupgrade", "path": path}
		if c.Host != "" { tr["host"] = c.Host }
		base["transport"] = tr
	} else if nt == "http" || nt == "h2" {
		path := c.Path
		if path == "" { path = "/" }
		tr := map[string]interface{}{"type": "http", "path": path}
		if c.Host != "" {
			hosts :=[]string{}
			for _, h := range strings.Split(c.Host, ",") {
				if strings.TrimSpace(h) != "" { hosts = append(hosts, strings.TrimSpace(h)) }
			}
			if len(hosts) > 0 { tr["host"] = hosts }
		}
		base["transport"] = tr
	} else if nt == "quic" {
		base["transport"] = map[string]interface{}{"type": "quic"}
	}

	sec := strings.ToLower(c.Security)
	if sec == "tls" || sec == "reality" || sec == "auto" {
		tlsConf := map[string]interface{}{"enabled": true}

		if sec == "tls" {
			tlsConf["insecure"] = true
		} else if sec == "reality" {
			tlsConf["insecure"] = false
		}

		if sec != "reality" {
			for k, v := range c.RawMeta {
				kl := strings.ToLower(k)
				if kl == "allowinsecure" || kl == "insecure" {
					if fmt.Sprintf("%v", v) == "1" || fmt.Sprintf("%v", v) == "true" || fmt.Sprintf("%v", v) == "yes" {
						tlsConf["insecure"] = true
					}
				}
			}
		}

		fp := strings.ToLower(c.FP)
		if fp == "chrome" || fp == "firefox" || fp == "edge" || fp == "safari" || fp == "360" || fp == "qq" || fp == "ios" || fp == "android" || fp == "random" || fp == "randomized" {
			tlsConf["utls"] = map[string]interface{}{"enabled": true, "fingerprint": fp}
		} else if sec == "reality" || sec == "tls" {
			tlsConf["utls"] = map[string]interface{}{"enabled": true, "fingerprint": "chrome"}
		}

		sni := c.SNI
		if sni == "" && sec != "reality" { sni = c.Host }
		if sni == "" && sec != "reality" { sni = c.Server }
		if sni != "" {
			tlsConf["server_name"] = strings.Trim(sni, "[]")
		}

		if c.ALPN != "" {
			var alpns[]string
			for _, a := range strings.Split(c.ALPN, ",") {
				if strings.TrimSpace(a) != "" { alpns = append(alpns, strings.TrimSpace(a)) }
			}
			if len(alpns) > 0 { tlsConf["alpn"] = alpns }
		} else if sec == "reality" || sec == "tls" {
			tlsConf["alpn"] =[]string{"h2", "http/1.1"}
		}

		if sec == "reality" {
			if len(c.PBK) < 40 || len(c.PBK) > 46 { return nil }
			tlsConf["reality"] = map[string]interface{}{"enabled": true, "public_key": c.PBK, "short_id": c.SID}
		}

		base["tls"] = tlsConf
	}

	return base
}

func getSocksClient(port int, timeout time.Duration) *http.Client {
	dialer, _ := proxy.SOCKS5("tcp", fmt.Sprintf("127.0.0.1:%d", port), nil, proxy.Direct)
	transport := &http.Transport{
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			return dialer.Dial(network, addr)
		},
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		DisableKeepAlives: true,
	}
	return &http.Client{Transport: transport, Timeout: timeout}
}

func testHTTPPing(port int, delaySec float64) (int, bool) {
	if delaySec > 0 {
		time.Sleep(time.Duration(delaySec * float64(time.Second)))
	}

	maxLatency := globalSettings.MaxLatency
	if maxLatency <= 0 { maxLatency = 5000 }

	urls := globalSettings.ConnectivityUrls
	if len(urls) == 0 {
		urls =[]string{"http://www.gstatic.com/generate_204"}
	}
	
	rand.Shuffle(len(urls), func(i, j int) { urls[i], urls[j] = urls[j], urls[i] })
	testUrls := urls
	if len(testUrls) > 2 { testUrls = testUrls[:2] }

	client := getSocksClient(port, 5*time.Second)
	
	t0 := time.Now()
	for _, targetUrl := range testUrls {
		req, _ := http.NewRequest("GET", targetUrl, nil)
		req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

		resp, err := client.Do(req)
		if err != nil { continue }
		
		defer resp.Body.Close()
		if resp.StatusCode != 204 { break }
		
		body, _ := io.ReadAll(resp.Body)
		if len(body) > 0 { break }

		lat := int(time.Since(t0).Milliseconds())
		if lat > maxLatency { return 0, false }
		return lat, true
	}
	return 0, false
}

func testHTTPSpeed(port int, strictID string, isChampion bool) (float64, string, bool) {
	timeout := 12 * time.Second
	targetBytes := normalBytes
	url := globalSettings.SpeedtestUrl
	if url == "" { url = "https://speed.cloudflare.com/__down?bytes=5000000" }

	if isChampion {
		timeout = 18 * time.Second
		targetBytes = championBytes
		if globalSettings.ChampionTestUrl != "" { url = globalSettings.ChampionTestUrl }
	}

	client := getSocksClient(port, timeout)
	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

	tStart := time.Now()
	resp, err := client.Do(req)
	
	total := 0
	if err == nil {
		defer resp.Body.Close()
		if resp.StatusCode == 429 {
			total = targetBytes
			tStart = time.Now().Add(-2 * time.Second)
		} else if resp.StatusCode == 200 {
			buf := make([]byte, chunkSize)
			for {
				n, errRead := resp.Body.Read(buf)
				total += n
				
				dur := time.Since(tStart).Seconds()
				if dur > 3.5 && total < 65536 {
					return 0, "UN", false
				}
				if total >= targetBytes || errRead != nil {
					break
				}
			}
		} else {
			return 0, "UN", false
		}
	}

	if total < 256*1024 {
		return 0, "UN", false
	}

	dur := time.Since(tStart).Seconds()
	if dur < 0.1 { dur = 0.1 }
	speed := (float64(total) * 8.0) / (dur * 1000000.0)
	if speed > 3000.0 { speed = 3000.0 }
	
	minSpeed := globalSettings.MinSpeed
	if minSpeed <= 0 { minSpeed = 1.0 }
	if speed < minSpeed {
		return 0, "UN", false
	}

	country := "UN"
	if val, ok := geoCache.Load(strictID); ok {
		country = val.(string)
	} else {
		time.Sleep(time.Duration(rand.Float64()*300+100) * time.Millisecond)
		geoUrls :=[]string{
			"http://cp.cloudflare.com/cdn-cgi/trace",
			"https://cloudflare.com/cdn-cgi/trace",
			"http://ip-api.com/json",
		}
		rand.Shuffle(len(geoUrls), func(i, j int) { geoUrls[i], geoUrls[j] = geoUrls[j], geoUrls[i] })
		
		geoClient := &http.Client{Timeout: 4 * time.Second}
		for _, gUrl := range geoUrls {
			r, err := geoClient.Get(gUrl)
			if err == nil && r.StatusCode == 200 {
				body, _ := io.ReadAll(r.Body)
				r.Body.Close()
				content := string(body)
				
				if strings.Contains(gUrl, "trace") {
					lines := strings.Split(content, "\n")
					for _, line := range lines {
						if strings.HasPrefix(line, "loc=") {
							country = strings.ToUpper(strings.TrimPrefix(line, "loc="))
							break
						}
					}
				} else {
					var data map[string]interface{}
					json.Unmarshal(body, &data)
					if cc, ok := data["countryCode"].(string); ok && len(cc) == 2 {
						country = strings.ToUpper(cc)
					}
				}
				if country != "UN" && country != "XX" && country != "" {
					geoCache.Store(strictID, country)
					break
				}
			}
		}
	}

	if country == "" || country == "XX" { country = "UN" }
	return speed, country, true
}

func runChampionPhase(nodes[]ProxyNode) {
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].Speed > nodes[j].Speed })
	limit := 5
	if len(nodes) < 5 { limit = len(nodes) }
	
	for i := 0; i < limit; i++ {
		res := processSingboxBatch([]ProxyNode{nodes[i]}, true)
		if len(res) > 0 {
			nodes[i].Speed = res[0].Speed
		}
	}
}