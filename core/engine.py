# --- START OF FILE core/engine.py ---
import asyncio
import json
import os
import subprocess
import uuid
import ipaddress
import aiohttp
import socket
from loguru import logger
from typing import List, Optional, Dict
from core.models import ProxyNode
from core.settings import CONFIG
from core.logger import GHA
from core.util import is_valid_uuid


class BatchEngine:
    _GEO_CACHE: Dict[str, str] = {}

    @staticmethod
    def _geo_cache_key(ip: str) -> str:
        """Return /24 network for IPv4, exact IP for IPv6.

        Neighboring IPv4 addresses within a /24 almost always share the same
        country, so we key by subnet to avoid redundant ip-api lookups.
        """
        try:
            addr = ipaddress.ip_address(ip)
            if addr.version == 4:
                net = ipaddress.IPv4Network(f"{addr}/24", strict=False)
                return str(net)
            return ip  # IPv6: exact match
        except ValueError:
            return ip

    @staticmethod
    def _node_to_outbound(node: ProxyNode, tag: str) -> Optional[dict]:
        c = node.config
        base: dict = {"tag": tag, "server": c.server, "server_port": c.port}

        try:
            if node.protocol == "vless":
                if not c.uuid or not is_valid_uuid(c.uuid):
                    return None
                base.update({"type": "vless", "uuid": c.uuid})
                if c.flow:
                    base["flow"] = c.flow

            elif node.protocol == "vmess":
                if not c.uuid or not is_valid_uuid(c.uuid):
                    return None
                base.update({
                    "type": "vmess",
                    "uuid": c.uuid,
                    "security": "auto",
                    "alter_id": c.alter_id,
                })

            elif node.protocol == "trojan":
                if not c.password:
                    return None
                base.update({"type": "trojan", "password": c.password})

            elif node.protocol == "ss":
                if not c.method or not c.password:
                    return None
                base.update({
                    "type": "shadowsocks",
                    "method": c.method.lower(),
                    "password": c.password,
                })

            elif node.protocol == "hysteria2":
                if not c.password:
                    return None
                base.update({"type": "hysteria2", "password": c.password})
                if c.obfs and c.obfs_password:
                    base["obfs"] = {"type": c.obfs, "password": c.obfs_password}
                hy2_tls: dict = {"enabled": True, "insecure": True}
                sni = c.sni or c.host
                if sni:
                    hy2_tls["server_name"] = sni.strip("[]")
                if c.alpn:
                    hy2_tls["alpn"] = [x.strip() for x in c.alpn.split(",") if x.strip()]
                base["tls"] = hy2_tls
                return base

            else:
                return None

            if c.type in ("ws", "websocket"):
                base["transport"] = {"type": "ws", "path": c.path or "/"}
                if c.host:
                    base["transport"]["headers"] = {"Host": c.host}
            elif c.type == "grpc":
                base["transport"] = {
                    "type": "grpc",
                    "service_name": c.service_name or c.path or "",
                }
            elif c.type in ("httpupgrade", "xhttp"):
                base["transport"] = {"type": "httpupgrade", "path": c.path or "/"}
                if c.host:
                    base["transport"]["host"] = c.host
            elif c.type in ("http", "h2"):
                base["transport"] = {"type": "http", "path": c.path or "/"}
                if c.host:
                    base["transport"]["host"] = [
                        h.strip() for h in c.host.split(",") if h.strip()
                    ]
            elif c.type == "quic":
                base["transport"] = {"type": "quic"}

            if c.security in ("tls", "reality", "auto"):
                tls: dict = {"enabled": True}

                if c.security == "tls":
                    tls["insecure"] = True
                elif c.security == "reality":
                    tls["insecure"] = False

                if c.security != "reality":
                    for k, v in c.raw_meta.items():
                        if k.lower() in ("allowinsecure", "insecure"):
                            if str(v).lower() in ("1", "true", "yes"):
                                tls["insecure"] = True

                if c.fp:
                    clean_fp = c.fp.lower()
                    if clean_fp in {
                        "chrome", "firefox", "edge", "safari",
                        "360", "qq", "ios", "android", "random", "randomized",
                    }:
                        tls["utls"] = {"enabled": True, "fingerprint": clean_fp}
                elif c.security in ("reality", "tls"):
                    tls["utls"] = {"enabled": True, "fingerprint": "chrome"}

                sni = c.sni
                if not sni and c.security != "reality":
                    sni = c.host
                if sni:
                    tls["server_name"] = sni.strip("[]")

                if c.alpn:
                    tls["alpn"] = [x.strip() for x in c.alpn.split(",") if x.strip()]
                elif c.security in ("reality", "tls"):
                    tls["alpn"] = ["h2", "http/1.1"]

                if c.security == "reality":
                    clean_pbk = c.pbk or ""
                    if len(clean_pbk) < 40 or len(clean_pbk) > 46:
                        return None
                    tls["reality"] = {"enabled": True, "public_key": clean_pbk}
                    tls["reality"]["short_id"] = c.sid if c.sid else ""

                base["tls"] = tls

            return base

        except Exception:
            return None


class Inspector:
    def __init__(self) -> None:
        self.l4_dropped = 0
        self.l4_failure_reasons: Dict[str, int] = {}
        self.l4_retry_attempts = 0
        self.l4_retry_recovered = 0
        self.l7_stats: Dict[str, int] = {}
        self.l7_total = 0
        self.l7_survived = 0

    def _extract_l4_stats(self, stats: dict) -> None:
        """Extract L4 failure reasons from combined stats, excluding meta and L7 keys."""
        l4_meta = {"total", "survived", "retry_attempts", "retry_recovered", "l7"}
        self.l4_failure_reasons = {
            k: v for k, v in stats.items()
            if k not in l4_meta and not isinstance(v, dict)
        }
        self.l4_retry_attempts = stats.get("retry_attempts", 0)
        self.l4_retry_recovered = stats.get("retry_recovered", 0)
        GHA.note(
            f"L4 stats        {self.l4_failure_reasons} | "
            f"retries={self.l4_retry_attempts} recovered={self.l4_retry_recovered}"
        )

    def _extract_l7_stats(self, stats: dict) -> None:
        """Extract L7 failure reasons from combined stats and log breakdown."""
        l7 = stats.get("l7", {})
        if not l7 or not isinstance(l7, dict):
            return
        self.l7_stats = l7
        self.l7_total = l7.get("total", 0)
        self.l7_survived = l7.get("survived", 0)
        l7_dropped = self.l7_total - self.l7_survived
        l7_pct = (self.l7_survived / self.l7_total * 100) if self.l7_total > 0 else 0.0
        GHA.note(
            f"L7 stats        total={self.l7_total} dropped={l7_dropped} "
            f"survived={self.l7_survived} ({l7_pct:.1f}%) | "
            f"http_timeout={l7.get('http_timeout', 0)} "
            f"http_tls_error={l7.get('http_tls_error', 0)} "
            f"http_bad_status={l7.get('http_bad_status', 0)} "
            f"http_other={l7.get('http_other_error', 0)} | "
            f"speed_timeout={l7.get('speed_timeout', 0)} "
            f"speed_tls={l7.get('speed_tls_error', 0)} "
            f"speed_slow={l7.get('speed_too_slow', 0)} "
            f"speed_other={l7.get('speed_other_error', 0)} | "
            f"singbox_crash={l7.get('singbox_crash', 0)} "
            f"protocol_mismatch={l7.get('protocol_mismatch', 0)}"
        )

    async def _resolve_geo(self, nodes: List[ProxyNode]) -> None:
        GHA.row("GeoIP", "resolving DNS…")
        if not nodes:
            return

        async def resolve_ip(host: str) -> Optional[str]:
            try:
                ipaddress.ip_address(host)
                return host
            except ValueError:
                try:
                    return await asyncio.to_thread(socket.gethostbyname, host)
                except Exception:
                    return None

        # Deduplicate hosts — many nodes share the same server hostname.
        host_to_nodes: Dict[str, List[ProxyNode]] = {}
        for node in nodes:
            host = node.config.server.strip("[]")
            host_to_nodes.setdefault(host, []).append(node)

        unique_hosts = list(host_to_nodes.keys())
        resolved_ips = await asyncio.gather(
            *[resolve_ip(h) for h in unique_hosts]
        )
        host_to_ip: Dict[str, Optional[str]] = dict(
            zip(unique_hosts, resolved_ips)
        )

        # Map resolved IPs back to nodes.
        node_ip_pairs: List[tuple] = []
        for node in nodes:
            host = node.config.server.strip("[]")
            ip = host_to_ip.get(host)
            if not ip:
                node.country = "UN"
                continue
            node_ip_pairs.append((node, ip))

        # Count cache hits before fetching.
        cache_hits = 0
        already_cached: set = set()
        for _, ip in node_ip_pairs:
            ck = BatchEngine._geo_cache_key(ip)
            if ck in BatchEngine._GEO_CACHE or ck in already_cached:
                cache_hits += 1
            else:
                already_cached.add(ck)

        # Build deduplicated fetch list keyed by /24 (IPv4) or exact IP (IPv6).
        ips_to_fetch: List[str] = []
        seen: set = set()
        for _, ip in node_ip_pairs:
            ck = BatchEngine._geo_cache_key(ip)
            if ck not in BatchEngine._GEO_CACHE and ck not in seen:
                ips_to_fetch.append(ip)
                seen.add(ck)

        GHA.row(
            "GeoIP",
            f"{len(nodes)} nodes · {len(unique_hosts)} hosts · "
            f"{cache_hits} cached · fetching {len(ips_to_fetch)}",
        )

        GEO_BATCH = 100
        GEO_SLEEP = 4.5

        if ips_to_fetch:
            async with aiohttp.ClientSession() as session:
                for i in range(0, len(ips_to_fetch), GEO_BATCH):
                    batch = ips_to_fetch[i : i + GEO_BATCH]
                    body = [
                        {"query": ip, "fields": "query,status,countryCode"}
                        for ip in batch
                    ]
                    try:
                        async with session.post(
                            "http://ip-api.com/batch",
                            json=body,
                            timeout=aiohttp.ClientTimeout(total=15),
                        ) as resp:
                            if resp.status == 200:
                                for item in await resp.json(content_type=None):
                                    ip_key = item.get("query", "")
                                    if not ip_key:
                                        continue
                                    ok = item.get("status", "fail") == "success"
                                    raw_cc = item.get("countryCode") if ok else None
                                    cc = (raw_cc or "UN").strip().upper()
                                    cc = cc if len(cc) == 2 else "UN"
                                    # Store under /24 key for IPv4 so neighbours reuse.
                                    BatchEngine._GEO_CACHE[
                                        BatchEngine._geo_cache_key(ip_key)
                                    ] = cc
                            elif resp.status == 429:
                                logger.warning("  GeoIP: rate limit — remaining nodes → UN")
                                break
                    except Exception as exc:
                        logger.debug(f"  GeoIP batch error: {exc}")

                    if i + GEO_BATCH < len(ips_to_fetch):
                        await asyncio.sleep(GEO_SLEEP)

        # Assign countries from cache (keyed by /24 or exact IP).
        for node, ip in node_ip_pairs:
            node.country = BatchEngine._GEO_CACHE.get(
                BatchEngine._geo_cache_key(ip), "UN"
            )

        assigned = sum(1 for n in nodes if n.country != "UN")
        GHA.row("GeoIP", f"flags assigned {assigned}/{len(nodes)}", last=True, status="ok")

    async def process_all(self, nodes: List[ProxyNode]) -> List[ProxyNode]:
        GHA.row("prepare", f"{len(nodes):,} nodes → ANGRA-CORE")

        os.makedirs("data", exist_ok=True)
        uid = uuid.uuid4().hex[:8]
        input_file = f"data/go_in_{uid}.json"
        output_file = f"data/go_out_{uid}.json"
        stats_file = f"data/go_stats_{uid}.json"

        payload_nodes: List[dict] = []
        for n in nodes:
            outbound = BatchEngine._node_to_outbound(n, "placeholder")
            if outbound:
                dump = n.model_dump(by_alias=True)
                dump["ready_outbound"] = outbound
                payload_nodes.append(dump)
            else:
                self.l4_dropped += 1

        GHA.row(
            "translate",
            f"{len(payload_nodes):,} outbounds  (rejected {self.l4_dropped:,})",
        )

        payload = {
            "settings": {
                "max_latency": CONFIG.checking.get("max_latency", 5000),
                "min_speed":   CONFIG.checking.get("min_speed", 1.0),
                "speed_as_filter": CONFIG.checking.get("speed_as_filter", False),
                "speed_concurrency": CONFIG.checking.get("speed_concurrency", 12),
                "l7_concurrency": CONFIG.checking.get("l7_concurrency", 4),
                "connectivity_urls": CONFIG.checking.get(
                    "connectivity_urls", ["http://cp.cloudflare.com/generate_204"]
                ),
                "speedtest_url": CONFIG.checking.get(
                    "speedtest_url", "https://speed.cloudflare.com"
                ),
                "champion_test_url": CONFIG.checking.get(
                    "champion_test_url",
                    "https://speed.cloudflare.com/__down?bytes=10485760",
                ),
                "batch_size": getattr(CONFIG, "BATCH_SIZE", 150),
                "champion_top_n": getattr(CONFIG, "CHAMPION_TOP_N", 20),
            },
            "nodes": payload_nodes,
        }

        with open(input_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        try:
            ext = ".exe" if os.name == "nt" else ""
            binary = f"go_core/angra_core{ext}"

            if not os.path.exists(binary):
                GHA.row("compile", "building ANGRA-CORE (first run)…")
                subprocess.run(
                    ["go", "mod", "init", "angra_core"],
                    cwd="go_core", check=False, capture_output=True,
                )
                subprocess.run(["go", "get", "golang.org/x/net/proxy"], cwd="go_core", check=True)
                subprocess.run(["go", "mod", "tidy"], cwd="go_core", check=True)
                subprocess.run(
                    ["go", "build", "-ldflags", "-s -w", "-o", f"angra_core{ext}", "main.go"],
                    cwd="go_core", check=True,
                )
                GHA.row("compile", "done ✔", status="ok")

            proc = await asyncio.create_subprocess_exec(
                f"./angra_core{ext}", f"../{input_file}", f"../{output_file}", f"../{stats_file}",
                cwd="go_core",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stderr_chunks: List[bytes] = []

            async def _stream_stdout(stream: asyncio.StreamReader) -> None:
                while True:
                    raw = await stream.readline()
                    if not raw:
                        break
                    line = raw.decode(errors="replace").rstrip()
                    if line:
                        print(f"  {line}", flush=True)

            async def _collect_stderr(stream: asyncio.StreamReader) -> None:
                while True:
                    raw = await stream.readline()
                    if not raw:
                        break
                    stderr_chunks.append(raw)

            await asyncio.gather(
                _stream_stdout(proc.stdout),
                _collect_stderr(proc.stderr),
            )
            await proc.wait()

            if proc.returncode != 0:
                stderr_text = b"".join(stderr_chunks).decode(errors="replace")
                logger.error(f"  ANGRA-CORE exited {proc.returncode}: {stderr_text[:500]}")
                # Try to read L4/L7 stats even on failure
                if os.path.exists(stats_file):
                    try:
                        with open(stats_file, "r", encoding="utf-8") as sf:
                            stats = json.load(sf)
                        self._extract_l4_stats(stats)
                        self._extract_l7_stats(stats)
                    except Exception:
                        pass
                return []

            # Read L4/L7 failure stats
            if os.path.exists(stats_file):
                try:
                    with open(stats_file, "r", encoding="utf-8") as sf:
                        stats = json.load(sf)
                    self._extract_l4_stats(stats)
                    self._extract_l7_stats(stats)
                except Exception:
                    pass

            with open(output_file, "r", encoding="utf-8") as f:
                valid_nodes_data: list = json.load(f)
            if not valid_nodes_data:
                valid_nodes_data = []

            valid_nodes: List[ProxyNode] = []
            for data in valid_nodes_data:
                data.pop("ready_outbound", None)
                try:
                    valid_nodes.append(ProxyNode(**data))
                except Exception as exc:
                    logger.debug(f"  ProxyNode reconstruct error: {exc}")

        except Exception as exc:
            logger.exception(f"  Go integration failure: {exc}")
            return []
        finally:
            for path in (input_file, output_file, stats_file):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass

        total = len(valid_nodes)
        self.l4_dropped += max(0, len(payload_nodes) - total)

        if valid_nodes:
            await self._resolve_geo(valid_nodes)

        return valid_nodes
