# --- START OF FILE core/engine.py ---
import asyncio
import json
import os
import subprocess
import uuid
from loguru import logger
from typing import List
from core.models import ProxyNode
from core.settings import CONFIG

class Inspector:
    def __init__(self):
        self.l4_dropped = 0

    async def process_all(self, nodes: List[ProxyNode]) -> List[ProxyNode]:
        total_initial = len(nodes)
        logger.info(f"► [ANGRA ORCHESTRATOR]: Передача {total_initial} узлов в Go-Ядро (ANGRA-CORE)...")
        
        os.makedirs("data", exist_ok=True)
        input_file = f"data/go_in_{uuid.uuid4().hex[:8]}.json"
        output_file = f"data/go_out_{uuid.uuid4().hex[:8]}.json"
        
        nodes_data =[n.model_dump(by_alias=True) for n in nodes]
        payload = {
            "settings": {
                "max_latency": CONFIG.checking.get("max_latency", 5000),
                "min_speed": CONFIG.checking.get("min_speed", 1.0),
                "connectivity_urls": CONFIG.checking.get("connectivity_urls",["http://cp.cloudflare.com/generate_204"]),
                "speedtest_url": CONFIG.checking.get("speedtest_url", "https://speed.cloudflare.com"),
                "champion_test_url": CONFIG.checking.get("champion_test_url", "https://speed.cloudflare.com/__down?bytes=50000000"),
                "batch_size": getattr(CONFIG, "BATCH_SIZE", 100)
            },
            "nodes": nodes_data
        }
        
        with open(input_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            
        try:
            ext = ".exe" if os.name == "nt" else ""
            if not os.path.exists(f"go_core/angra_core{ext}"):
                logger.info("⚙ [GOLANG]: Инициализация модулей и компиляция ANGRA-CORE...")
                
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
                return []
                
            with open(output_file, "r", encoding="utf-8") as f:
                valid_nodes_data = json.load(f)
                
            valid_nodes =[ProxyNode(**data) for data in valid_nodes_data]
            
        except Exception as e:
            logger.exception(f"✘ [СБОЙ ИНТЕГРАЦИИ GO]: {e}. Убедитесь, что 'go' установлен и доступен в PATH.")
            return[]
        finally:
            if os.path.exists(input_file): os.remove(input_file)
            if os.path.exists(output_file): os.remove(output_file)

        nodes = valid_nodes
        total = len(nodes)

        self.l4_dropped += (total_initial - total)

        logger.info(f"✔ [ANGRA ORCHESTRATOR]: Инспекция полностью завершена. Итого выжило: {total}")
        return valid_nodes

    async def champion_run(self, nodes: List[ProxyNode]) -> float:
        return max((n.speed for n in nodes), default=0.0)
