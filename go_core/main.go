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

// = МОСТ КОНФИГУРАЦИИ ИЗ PYTHON =
type EngineSettings struct {
	MaxLatency       int      `json:"max_latency"`
	MinSpeed         float64  `json:"min_speed"`
	ConnectivityUrls[]string `json:"connectivity_urls"`
	SpeedtestUrl     string   `json:"speedtest_url"`
	ChampionTestUrl  string   `json:"champion_test_url"`
	BatchSize        int      `json:"batch_size"`
}

type InputPayload struct {
	Settings EngineSettings `json:"settings"`
	Nodes[]ProxyNode    `json:"nodes"`
}

// = СИНХРОНИЗАЦИЯ С PYDANTIC МОДЕЛЯМИ =
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

var forbiddenNetworks []*net.IPNet
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

func runL4Phase(nodes []ProxyNode)[]ProxyNode {
	var wg sync.WaitGroup
	var mu sync.Mutex
	valid := make([]ProxyNode, 0)
	sem := make(chan struct{}, 2000)

	for _, node := range nodes {
		wg.Add(1)
		sem <- struct{}{}
		go func(n ProxyNode) {
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

func checkL4(node ProxyNode) bool {
	if node.Protocol == "hysteria2" || node.Protocol == "quic" { return true }
	
	host := strings.Trim(node.Config.Server, "[]")
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

	nt := strings.ToLower(node.Config.Type)
	isCdnAllowed := nt == "ws" || nt == "websocket" || nt == "httpupgrade" || nt == "xhttp" || nt == "grpc"
	if !isCdnAllowed {
		for _, network := range forbiddenNetworks {
			if network.Contains(targetIP) { return false }
		}
	}

	address := fmt.Sprintf("[%s]:%d", targetIP.String(), node.Config.Port)
	if targetIP.To4() != nil {
		address = fmt.Sprintf("%s:%d", targetIP.String(), node.Config.Port)
	}

	conn, err := net.DialTimeout("tcp", address, 2*time.Second)
	if err != nil { return false }
	conn.Close()
	return true
}

func runL7Phase(nodes []ProxyNode)[]ProxyNode {
	batchSize := globalSettings.BatchSize
	if batchSize <= 0 { batchSize = 100 }
	var finalNodes[]ProxyNode

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

func processSingboxBatch(batch []ProxyNode)[]ProxyNode {
	basePort := 10000
	inbounds := make([]map[string]interface{}, 0)
	outbounds := make([]map[string]interface{}, 0)
	rules := []map[string]interface{}{
		{"protocol": "dns", "outbound": "direct"},
		{"ip_cidr":[]string{"127.0.0.0/8", "10.0.0.0/8", "192.168.0.0/16"}, "outbound": "block"},
	}

	validMap := make(map[int]ProxyNode)

	for i, node := range batch {
		tag := fmt.Sprintf("proxy-%d", i)
		ob := buildOutbound(node, tag)
		if ob == nil { continue }
		
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
	pingPassed := make(map[int]ProxyNode)
	semPing := make(chan struct{}, 25)

	for port, node := range validMap {
		wgPing.Add(1)
		semPing <- struct{}{}
		go func(p int, n ProxyNode) {
			defer wgPing.Done()
			defer func() { <-semPing }()
			if lat, ok := testHTTPPing(p); ok {
				n.Latency = lat
				mu.Lock()
				pingPassed[p] = n
				mu.Unlock()
			}
		}(port, node)
	}
	wgPing.Wait()

	if len(pingPassed) == 0 { return nil }

	var wgSpeed sync.WaitGroup
	alive := make([]ProxyNode, 0)
	semSpeed := make(chan struct{}, 10)

	for port, node := range pingPassed {
		wgSpeed.Add(1)
		semSpeed <- struct{}{}
		go func(p int, n ProxyNode) {
			defer wgSpeed.Done()
			defer func() { <-semSpeed }()
			verifySSL := resolvePayloadSSL(n)
			if speed, ok := testHTTPSpeed(p, verifySSL); ok {
				n.Speed = speed
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
		tr := map[string]interface{}{"type": "ws", "path": c.Path}
		if c.Host != "" { tr["headers"] = map[string]interface{}{"Host": c.Host} }
		base["transport"] = tr
	} else if nt == "grpc" {
		sn := c.ServiceName
		if sn == "" { sn = c.Path }
		base["transport"] = map[string]interface{}{"type": "grpc", "service_name": sn}
	} else if nt == "httpupgrade" || nt == "xhttp" {
		tr := map[string]interface{}{"type": "httpupgrade", "path": c.Path}
		if c.Host != "" { tr["host"] = c.Host }
		base["transport"] = tr
	}

	sec := strings.ToLower(c.Security)
	if sec == "tls" || sec == "reality" {
		tlsConf := map[string]interface{}{"enabled": true, "insecure": sec == "tls"}
		if c.SNI != "" { tlsConf["server_name"] = c.SNI } else if c.Host != "" { tlsConf["server_name"] = c.Host }
		
		if c.FP != "" { tlsConf["utls"] = map[string]interface{}{"enabled": true, "fingerprint": c.FP}
		} else { tlsConf["utls"] = map[string]interface{}{"enabled": true, "fingerprint": "chrome"} }

		if c.ALPN != "" { tlsConf["alpn"] = strings.Split(c.ALPN, ",")
		} else { tlsConf["alpn"] =[]string{"h2", "http/1.1"} }

		if sec == "reality" {
			tlsConf["reality"] = map[string]interface{}{"enabled": true, "public_key": c.PBK, "short_id": c.SID}
		}
		base["tls"] = tlsConf
	}

	return base
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

func resolvePayloadSSL(n ProxyNode) bool {
	if n.Config.Security == "reality" { return true }
	for k, v := range n.Config.RawMeta {
		kl := strings.ToLower(k)
		if kl == "allowinsecure" || kl == "insecure" {
			if fmt.Sprintf("%v", v) == "1" || fmt.Sprintf("%v", v) == "true" { return false }
		}
	}
	return true
}

func runChampionPhase(nodes[]ProxyNode) {
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].Speed > nodes[j].Speed })
	limit := 5
	if len(nodes) < 5 { limit = len(nodes) }
	
	fmt.Printf("►[ANGRA-GO CHAMPION]: Старт 50MB спидтеста для Топ-%d\n", limit)

	for i := 0; i < limit; i++ {
		speed := performHeavySpeedtest(nodes[i])
		if speed > 0 { nodes[i].Speed = speed }
	}
}

func performHeavySpeedtest(node ProxyNode) float64 {
	configPath := "go_temp_champ.json"
	ob := buildOutbound(node, "proxy-0")
	if ob == nil { return 0 }

	configBytes, _ := json.Marshal(map[string]interface{}{
		"log": map[string]interface{}{"level": "fatal", "output": "discard"},
		"inbounds": []map[string]interface{}{{"type": "socks", "tag": "in-0", "listen": "127.0.0.1", "listen_port": 15000}},
		"outbounds": []map[string]interface{}{ob, {"type": "direct", "tag": "direct"}},
		"route": map[string]interface{}{"rules": []map[string]interface{}{{"inbound":[]string{"in-0"}, "outbound": "proxy-0"}}},
	})
	os.WriteFile(configPath, configBytes, 0644)
	defer os.Remove(configPath)

	cmd := exec.Command("sing-box", "run", "-c", configPath)
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
