# --- START OF FILE core/engine.py ---
import asyncio
import json
import os
import subprocess
import uuid
import re
import ipaddress
import aiohttp
import socket
from loguru import logger
from typing import List, Optional
from core.models import ProxyNode
from core.settings import CONFIG

class BatchEngine:
    _GEO_CACHE: dict = {}

    @staticmethod
    def _is_valid_uuid(val: str) -> bool:
        try:
            uuid.UUID(str(val))
            return True
        except ValueError:
            return False

    @staticmethod
    def _node_to_outbound(node: ProxyNode, tag: str) -> Optional[dict]:
        c = node.config
        base = {"tag": tag, "server": c.server, "server_port": c.port}

        try:
            if node.protocol == "vless":
                if not c.uuid or not BatchEngine._is_valid_uuid(c.uuid): return None
                base.update({"type": "vless", "uuid": c.uuid})
                if c.flow: base["flow"] = c.flow

            elif node.protocol == "vmess":
                if not c.uuid or not BatchEngine._is_valid_uuid(c.uuid): return None
                base.update({
                    "type": "vmess",
                    "uuid": c.uuid,
                    "security": "auto",
                    "alter_id": c.alter_id,
                })

            elif node.protocol == "trojan":
                if not c.password: return None
                base.update({"type": "trojan", "password": c.password})

            elif node.protocol == "ss":
                if not c.method or not c.password: return None
                base.update({
                    "type": "shadowsocks",
                    "method": c.method.lower(),
                    "password": c.password,
                })

            elif node.protocol == "hysteria2":
                if not c.password: return None
                base.update({
                    "type": "hysteria2", 
                    "password": c.password
                })
                if c.obfs and c.obfs_password:
                    base["obfs"] = {"type": c.obfs, "password": c.obfs_password}

            if c.type in ("ws", "websocket"):
                base["transport"] = {"type": "ws", "path": c.path or "/"}
                if c.host: base["transport"]["headers"] = {"Host": c.host}
            elif c.type == "grpc":
                base["transport"] = {"type": "grpc", "service_name": c.service_name or c.path or ""}
            elif c.type in ("httpupgrade", "xhttp"):
                base["transport"] = {"type": "httpupgrade", "path": c.path or "/"}
                if c.host: base["transport"]["host"] = c.host
            elif c.type in ("http", "h2"):
                base["transport"] = {"type": "http", "path": c.path or "/"}
                if c.host: base["transport"]["host"] =[h.strip() for h in c.host.split(",") if h.strip()]
            elif c.type == "quic":
                base["transport"] = {"type": "quic"}

            if c.security in ("tls", "reality", "auto"):
                tls = {"enabled": True}

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
                    if clean_fp in {"chrome", "firefox", "edge", "safari", "360", "qq", "ios", "android", "random", "randomized"}:
                        tls["utls"] = {"enabled": True, "fingerprint": clean_fp}
                elif c.security in ("reality", "tls"):
                    tls["utls"] = {"enabled": True, "fingerprint": "chrome"}

                sni = c.sni
                if not sni and c.security != "reality": sni = c.host
                if sni: tls["server_name"] = sni.strip("[]")

                if c.alpn:
                    tls["alpn"] =[x.strip() for x in c.alpn.split(",") if x.strip()]
                elif c.security in ("reality", "tls"):
                    tls["alpn"] = ["h2", "http/1.1"]

                if c.security == "reality":
                    clean_pbk = c.pbk or ""
                    if len(clean_pbk) < 40 or len(clean_pbk) > 46: return None
                    tls["reality"] = {"enabled": True, "public_key": clean_pbk}
                    if c.sid:
                        tls["reality"]["short_id"] = c.sid
                    else:
                        tls["reality"]["short_id"] = ""

                base["tls"] = tls

            return base

        except Exception:
            return None


class Inspector:
    def __init__(self):
        self.l4_dropped = 0

    async def _resolve_geo(self, nodes: List[ProxyNode]):
        logger.info("► [GEOIP]: Присвоение флагов стран выжившим узлам...")
        
        async def fetch_geo(ip: str, session: aiohttp.ClientSession) -> str:
            if ip in BatchEngine._GEO_CACHE:
                return BatchEngine._GEO_CACHE[ip]
                
            geo_services =[
                f"http://ip-api.com/json/{ip}",
                f"https://freeipapi.com/api/json/{ip}"
            ]
            
            for url in geo_services:
                try:
                    async with session.get(url, timeout=3.0) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            country = data.get("countryCode", data.get("countryCode", "UN"))
                            if len(country) == 2:
                                BatchEngine._GEO_CACHE[ip] = country.upper()
                                return country.upper()
                except Exception:
                    pass
            return "UN"

        async with aiohttp.ClientSession() as session:
            for node in nodes:
                try:
                    host = node.config.server.strip("[]")
                    try:
                        ipaddress.ip_address(host)
                        ip = host
                    except ValueError:
                        ip = socket.gethostbyname(host)
                        
                    node.country = await fetch_geo(ip, session)
                    await asyncio.sleep(0.05)
                except Exception:
                    node.country = "UN"

    async def process_all(self, nodes: List[ProxyNode]) -> List[ProxyNode]:
        total_initial = len(nodes)
        logger.info(f"► [ANGRA ORCHESTRATOR]: Передача {total_initial} узлов в Go-Ядро (ANGRA-CORE)...")
        
        os.makedirs("data", exist_ok=True)
        input_file = f"data/go_in_{uuid.uuid4().hex[:8]}.json"
        output_file = f"data/go_out_{uuid.uuid4().hex[:8]}.json"
        
        payload_nodes =[]
        for n in nodes:
            outbound = BatchEngine._node_to_outbound(n, "placeholder")
            if outbound:
                dump = n.model_dump(by_alias=True)
                dump["ready_outbound"] = outbound
                payload_nodes.append(dump)
            else:
                self.l4_dropped += 1

        payload = {
            "settings": {
                "max_latency": CONFIG.checking.get("max_latency", 5000),
                "min_speed": CONFIG.checking.get("min_speed", 1.0),
                "connectivity_urls": CONFIG.checking.get("connectivity_urls",["http://cp.cloudflare.com/generate_204"]),
                "speedtest_url": CONFIG.checking.get("speedtest_url", "https://speed.cloudflare.com"),
                "champion_test_url": CONFIG.checking.get("champion_test_url", "https://speed.cloudflare.com/__down?bytes=50000000"),
                "batch_size": getattr(CONFIG, "BATCH_SIZE", 100)
            },
            "nodes": payload_nodes
        }
        
        with open(input_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            
        try:
            ext = ".exe" if os.name == "nt" else ""
            if not os.path.exists(f"go_core/angra_core{ext}"):
                logger.info("⚙ [GOLANG]: Компиляция ANGRA-CORE...")
                subprocess.run(["go", "mod", "init", "angra_core"], cwd="go_core", check=False)
                subprocess.run(["go", "get", "golang.org/x/net/proxy"], cwd="go_core", check=True)
                subprocess.run(["go", "mod", "tidy"], cwd="go_core", check=True)
                subprocess.run(["go", "build", "-o", f"angra_core{ext}", "main.go"], cwd="go_core", check=True)
            
            logger.info("⚡ [GOLANG]: Запуск сетевого пайплайна (L4 -> L7 -> Champion)...")
            
            proc = await asyncio.create_subprocess_exec(
                f"./angra_core{ext}", f"../{input_file}", f"../{output_file}",
                cwd="go_core",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if stdout:
                for line in stdout.decode().splitlines():
                    if line.strip(): logger.info(line.strip())
                    
            if proc.returncode != 0:
                logger.error(f"✘ [GOLANG CRASH]: {stderr.decode()}")
                return[]
                
            with open(output_file, "r", encoding="utf-8") as f:
                valid_nodes_data = json.load(f)
                if not valid_nodes_data:
                    valid_nodes_data = []
                
            valid_nodes =[]
            for data in valid_nodes_data:
                data.pop("ready_outbound", None)
                valid_nodes.append(ProxyNode(**data))
            
        except Exception as e:
            logger.exception(f"✘[СБОЙ ИНТЕГРАЦИИ GO]: {e}")
            return[]
        finally:
            if os.path.exists(input_file): os.remove(input_file)
            if os.path.exists(output_file): os.remove(output_file)

        nodes = valid_nodes
        total = len(nodes)
        self.l4_dropped += (len(payload_nodes) - total)

        if nodes:
            await self._resolve_geo(nodes)

        logger.info(f"✔ [ANGRA ORCHESTRATOR]: Инспекция полностью завершена. Итого выжило: {total}")
        return valid_nodes

    async def champion_run(self, nodes: List[ProxyNode]) -> float:
        return max((n.speed for n in nodes), default=0.0)
