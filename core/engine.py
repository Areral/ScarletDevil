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
from core.util import is_valid_uuid


class BatchEngine:
    _GEO_CACHE: Dict[str, str] = {}

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

    async def _resolve_geo(self, nodes: List[ProxyNode]) -> None:
        logger.info("  GeoIP: разрешение DNS...")
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

        hosts = [n.config.server.strip("[]") for n in nodes]
        resolved: List[Optional[str]] = await asyncio.gather(
            *[resolve_ip(h) for h in hosts]
        )

        node_ip_pairs: List[tuple] = []
        ips_to_fetch: List[str] = []
        seen: set = set()

        for node, ip in zip(nodes, resolved):
            if not ip:
                node.country = "UN"
                continue
            node_ip_pairs.append((node, ip))
            if ip not in BatchEngine._GEO_CACHE and ip not in seen:
                ips_to_fetch.append(ip)
                seen.add(ip)

        logger.info(
            f"  GeoIP: DNS resolved {len(node_ip_pairs)} nodes, "
            f"fetching {len(ips_to_fetch)} unique IPs..."
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
                                    BatchEngine._GEO_CACHE[ip_key] = (
                                        cc if len(cc) == 2 else "UN"
                                    )
                            elif resp.status == 429:
                                logger.warning("  GeoIP: rate limit — remaining nodes → UN")
                                break
                    except Exception as exc:
                        logger.debug(f"  GeoIP batch error: {exc}")

                    if i + GEO_BATCH < len(ips_to_fetch):
                        await asyncio.sleep(GEO_SLEEP)

        for node, ip in node_ip_pairs:
            node.country = BatchEngine._GEO_CACHE.get(ip, "UN")

        assigned = sum(1 for n in nodes if n.country != "UN")
        logger.info(f"  GeoIP: flags assigned {assigned}/{len(nodes)}")

    async def process_all(self, nodes: List[ProxyNode]) -> List[ProxyNode]:
        logger.info(f"  Подготовка {len(nodes):,} узлов для передачи в ANGRA-CORE...")

        os.makedirs("data", exist_ok=True)
        uid = uuid.uuid4().hex[:8]
        input_file = f"data/go_in_{uid}.json"
        output_file = f"data/go_out_{uid}.json"

        payload_nodes: List[dict] = []
        for n in nodes:
            outbound = BatchEngine._node_to_outbound(n, "placeholder")
            if outbound:
                dump = n.model_dump(by_alias=True)
                dump["ready_outbound"] = outbound
                payload_nodes.append(dump)
            else:
                self.l4_dropped += 1

        logger.info(
            f"  Транслировано outbounds: {len(payload_nodes):,}  "
            f"(отклонено при трансляции: {self.l4_dropped:,})"
        )

        payload = {
            "settings": {
                "max_latency": CONFIG.checking.get("max_latency", 5000),
                "min_speed":   CONFIG.checking.get("min_speed", 1.0),
                "speed_as_filter": CONFIG.checking.get("speed_as_filter", False),
                "speed_concurrency": CONFIG.checking.get("speed_concurrency", 12),
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
            },
            "nodes": payload_nodes,
        }

        with open(input_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        try:
            ext = ".exe" if os.name == "nt" else ""
            binary = f"go_core/angra_core{ext}"

            if not os.path.exists(binary):
                logger.info("  Компиляция ANGRA-CORE (первый запуск)...")
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
                logger.info("  Компиляция завершена.")

            proc = await asyncio.create_subprocess_exec(
                f"./angra_core{ext}", f"../{input_file}", f"../{output_file}",
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
                return []

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
            for path in (input_file, output_file):
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
