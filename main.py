# --- START OF FILE main.py ---
import asyncio
import time
import sys
import os
from loguru import logger

import core.logger
from core.logger import GHA

from core.settings import CONFIG
from core.parser import LinkParser, SourceHealth
from core.engine import Inspector
from core.exporter import Exporter
from core.validator import RKNValidator


async def main() -> None:
    start_time = time.perf_counter()

    shard_index = int(os.environ.get("SHARD_INDEX", "0"))
    shard_count = int(os.environ.get("SHARD_COUNT", "1"))

    GHA.drone_header(shard_index + 1, shard_count)

    try:
        GHA.group(f"① BASES — Loading RKN / TSPU Whitelists")
        await RKNValidator.load_lists()
        GHA.endgroup()

        GHA.group("② PARSE — Fetching & Decoding Subscription Sources")
        source_health = SourceHealth(shard_index=shard_index if shard_count > 1 else -1)
        parser = LinkParser()
        all_nodes = await parser.fetch_and_parse(source_health=source_health)

        if not all_nodes:
            GHA.error("No valid nodes after parsing — aborting drone.")
            logger.error("Нет валидных узлов после парсинга. Завершение.")
            GHA.endgroup()
            return

        if shard_count > 1:
            # Round-robin distribution: each drone gets every Nth node.
            # This ensures nodes from all sources are spread evenly across drones,
            # preventing high-yield source clusters from landing entirely on one shard.
            nodes = all_nodes[shard_index::shard_count]
            logger.info(
                f"  Shard {shard_index + 1}/{shard_count} — "
                f"round-robin slice — "
                f"({len(nodes):,} / {len(all_nodes):,} nodes)"
            )
        else:
            nodes = all_nodes

        logger.info(f"  Total collected  {len(all_nodes):>8,}  nodes")
        logger.info(f"  Shard workload   {len(nodes):>8,}  nodes")
        GHA.endgroup()

        GHA.group("③ ENGINE — L4 TCP · L7 sing-box · Champion Speed Test")
        inspector = Inspector()
        alive_nodes = await inspector.process_all(nodes)
        l4_dropped = inspector.l4_dropped
        GHA.endgroup()

        GHA.group("④ AGGREGATE — Metrics & Deduplication")

        logger.info(f"  L7 alive (raw)   {len(alive_nodes):>8,}  nodes")

        for node in alive_nodes:
            if node.source_url in parser.metrics:
                m = parser.metrics[node.source_url]
                m["alive"] = m.get("alive", 0) + 1

        # Record source health & compute per-source yields
        source_yields: dict = {}
        for url, m in parser.metrics.items():
            parsed = m.get("parsed", 0)
            alive = m.get("alive", 0)
            source_health.record(url, parsed, alive)
            if parsed > 0:
                source_yields[url] = {
                    "parsed": parsed,
                    "alive": alive,
                    "yield_pct": round(alive / parsed * 100, 1),
                }
        source_health.save()

        dead_sources = [
            url for url, m in parser.metrics.items()
            if m.get("parsed", 0) > 0 and m.get("alive", 0) == 0
        ]

        unique_alive: dict = {}
        for n in alive_nodes:
            unique_alive[n.strict_id] = n
        alive_nodes = list(unique_alive.values())

        bs_count = sum(1 for n in alive_nodes if n.is_bs)
        top_speed = max((n.speed for n in alive_nodes), default=0.0)

        # Compute speed distribution stats (US-C04)
        speeds = sorted([n.speed for n in alive_nodes if n.speed > 0])
        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
        if speeds:
            mid = len(speeds) // 2
            median_speed = speeds[mid] if len(speeds) % 2 == 1 else (speeds[mid - 1] + speeds[mid]) / 2
            p90_idx = int(len(speeds) * 0.9)
            speed_p90 = speeds[min(p90_idx, len(speeds) - 1)]
        else:
            median_speed = 0.0
            speed_p90 = 0.0

        # Compute country distribution from GeoIP data (US-C04)
        country_counts: dict = {}
        for n in alive_nodes:
            cc = (n.country or "UN").strip().upper()
            if len(cc) == 2 and cc.isalpha():
                country_counts[cc] = country_counts.get(cc, 0) + 1
        sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        country_stats = [{"code": cc, "count": cnt, "flag": ""} for cc, cnt in sorted_countries]

        logger.info(f"  Unique alive     {len(alive_nodes):>8,}  nodes")
        logger.info(f"  БС (whitelist)   {bs_count:>8,}  nodes")
        logger.info(f"  ЧС (blacklist)   {len(alive_nodes) - bs_count:>8,}  nodes")
        logger.info(f"  Dead sources     {len(dead_sources):>8,}")
        logger.info(f"  ⚡ Top speed      {top_speed:>8.1f}  Mbps")
        logger.info(f"  📊 Avg/Med/P90    {avg_speed:>6.1f} / {median_speed:>6.1f} / {speed_p90:>6.1f}  Mbps")
        top_countries_str = ', '.join(f"{c['code']}:{c['count']}" for c in country_stats[:5])
        logger.info(f"  🌍 Top countries  {len(country_stats)}  ({top_countries_str})")
        GHA.endgroup()

        GHA.group("⑤ EXPORT — Writing Subscription Files")
        duration = time.perf_counter() - start_time
        Exporter.save_files(
            alive_nodes,
            shard_index=shard_index if shard_count > 1 else -1,
            parsed_count=len(nodes),
            dead_sources=dead_sources,
            duration=duration,
            l4_dropped=l4_dropped,
            l4_failure_reasons=getattr(inspector, "l4_failure_reasons", {}),
            l4_retry_attempts=getattr(inspector, "l4_retry_attempts", 0),
            l4_retry_recovered=getattr(inspector, "l4_retry_recovered", 0),
            l7_stats=getattr(inspector, "l7_stats", {}),
            source_yields=source_yields,
            avg_speed=avg_speed,
            median_speed=median_speed,
            speed_percentile_90=speed_p90,
            country_stats=country_stats,
        )
        GHA.endgroup()

        duration = time.perf_counter() - start_time
        GHA.drone_summary(
            drone_idx=shard_index + 1,
            parsed=len(nodes),
            l4_dropped=l4_dropped,
            l7_alive=len(alive_nodes),
            unique=len(alive_nodes),
            bs_count=bs_count,
            top_speed=top_speed,
            duration=duration,
            dead_sources=len(dead_sources),
        )

        if len(alive_nodes) == 0:
            GHA.warning(f"Drone {shard_index + 1}: zero alive nodes in output.")

    except Exception as exc:
        GHA.error(f"Drone {shard_index + 1} critical failure: {exc}")
        logger.exception(f"✘ КРИТИЧЕСКИЙ СБОЙ: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    if sys.platform != "win32":
        try:
            import uvloop
            uvloop.install()
        except ImportError:
            pass

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
