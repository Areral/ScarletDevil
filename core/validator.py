# --- START OF FILE core/validator.py ---
import aiohttp
import ipaddress
import asyncio
import os
import time
from loguru import logger
from core.settings import CONFIG
from core.models import ProxyNode

# Кэш последней успешно загруженной версии whitelist'ов (§5.1.3).
# Если источники недоступны/пусты — используем последнюю рабочую копию,
# чтобы класс БС (Nightbird) не схлопнулся в ноль.
_CACHE_DIR = os.path.join("data", "whitelist_cache")
_DOMAINS_CACHE = os.path.join(_CACHE_DIR, "domains.txt")
_CIDR_CACHE = os.path.join(_CACHE_DIR, "cidr.txt")


class RKNValidator:
    domains_wl = set()
    ips_wl = set()
    networks_wl = []
    _is_loaded = False

    @classmethod
    async def _fetch_list(cls, session: aiohttp.ClientSession, url: str) -> str:
        if not url:
            return ""
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.text()
        except Exception:
            pass
        return ""

    @staticmethod
    def _parse_lines(text: str) -> set:
        return {
            line.strip().lower()
            for line in text.splitlines()
            if line.strip() and not line.startswith('#')
        }

    @staticmethod
    def _save_cache(path: str, lines: set):
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(lines)))
        except Exception as e:
            logger.warning(f"► [WHITELIST КЭШ]: не удалось записать {path}: {e}")

    @staticmethod
    def _load_cache(path: str) -> set:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return {
                        line.strip().lower()
                        for line in f
                        if line.strip() and not line.startswith('#')
                    }
        except Exception as e:
            logger.warning(f"► [WHITELIST КЭШ]: не удалось прочитать {path}: {e}")
        return set()

    @staticmethod
    def _cache_age_str(path: str) -> str:
        try:
            if os.path.exists(path):
                age_h = (time.time() - os.path.getmtime(path)) / 3600.0
                return f"{age_h:.1f}ч"
        except Exception:
            pass
        return "n/a"

    @classmethod
    def _resolve_with_cache(cls, fetched: set, cache_path: str, label: str) -> set:
        """Сохраняет свежие данные в кэш либо откатывается на кэш при пустом ответе."""
        if fetched:
            cls._save_cache(cache_path, fetched)
            logger.info(f"► [WHITELIST {label}]: загружено {len(fetched)} строк из источников (кэш обновлён).")
            return fetched

        cached = cls._load_cache(cache_path)
        if cached:
            logger.warning(
                f"► [WHITELIST {label}]: источники пусты/недоступны — "
                f"откат на КЭШ ({len(cached)} строк, возраст {cls._cache_age_str(cache_path)})."
            )
        else:
            logger.warning(f"► [WHITELIST {label}]: источники пусты И кэш отсутствует.")
        return cached

    @classmethod
    async def load_lists(cls):
        cls.domains_wl.clear()
        cls.ips_wl.clear()
        cls.networks_wl.clear()
        cls._is_loaded = False

        dom_urls = CONFIG.whitelist.get("domains_urls", [])
        if not dom_urls and CONFIG.whitelist.get("domains_url"):
            dom_urls = [CONFIG.whitelist.get("domains_url")]

        ip_urls = CONFIG.whitelist.get("ips_urls", [])
        if not ip_urls and CONFIG.whitelist.get("ips_url"):
            ip_urls = [CONFIG.whitelist.get("ips_url")]

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = []
            for url in dom_urls:
                tasks.append(cls._fetch_list(session, url))
            for url in ip_urls:
                tasks.append(cls._fetch_list(session, url))

            results = await asyncio.gather(*tasks)

        dom_results = results[:len(dom_urls)]
        ip_results = results[len(dom_urls):]

        ok_dom = sum(1 for t in dom_results if t)
        ok_ip = sum(1 for t in ip_results if t)
        logger.info(
            f"► [БАЗЫ РКН]: источники ответили — домены {ok_dom}/{len(dom_urls)}, "
            f"подсети {ok_ip}/{len(ip_urls)}."
        )

        dom_lines = set()
        for text in dom_results:
            if text:
                dom_lines.update(cls._parse_lines(text))
        dom_lines = cls._resolve_with_cache(dom_lines, _DOMAINS_CACHE, "домены")
        cls.domains_wl = dom_lines

        ip_lines = set()
        for text in ip_results:
            if text:
                ip_lines.update(cls._parse_lines(text))
        ip_lines = cls._resolve_with_cache(ip_lines, _CIDR_CACHE, "подсети")

        unique_nets = set()
        for item in ip_lines:
            if '/' in item:
                try:
                    net = ipaddress.ip_network(item, strict=False)
                    if net.prefixlen > 0:
                        unique_nets.add(net)
                except ValueError:
                    pass
            else:
                cls.ips_wl.add(item)

        cls.networks_wl = list(unique_nets)

        if cls.domains_wl or cls.ips_wl or cls.networks_wl:
            cls._is_loaded = True
            logger.info(f"► [БАЗЫ РКН]: Успешно загружены. Доменов: {len(cls.domains_wl)} | Подсетей: {len(cls.ips_wl) + len(cls.networks_wl)}")
        else:
            logger.warning("► [БАЗЫ РКН]: ВНИМАНИЕ! Базы пусты (источники И кэш). Все узлы будут классифицированы как ЧС.")

    @classmethod
    def check_bs(cls, node: ProxyNode) -> bool:
        if node.config.security != "reality":
            return False

        if not cls._is_loaded:
            return False

        raw_target = node.config.sni or node.config.host or node.config.server
        if not raw_target:
            return False

        target = raw_target.split(",")[0].strip().lower().strip("[]")

        if not target:
            return False

        if target in cls.domains_wl or target in cls.ips_wl:
            return True

        try:
            ip_obj = ipaddress.ip_address(target)
            for net in cls.networks_wl:
                if ip_obj in net:
                    return True
            return False
        except ValueError:
            parts = target.split('.')
            for i in range(1, len(parts) - 1):
                base_domain = '.'.join(parts[i:])
                if base_domain in cls.domains_wl:
                    return True
            return False
