# --- START OF FILE main.py ---
import asyncio
import time
import sys
import os
import json
from loguru import logger

import core.logger
from core.logger import GHA

from core.settings import CONFIG
from core.parser import LinkParser, SourceHealth
from core.engine import Inspector
from core.exporter import Exporter
from core.validator import RKNValidator
from core.models import ProxyNode


def apply_ru_verdict(nodes: list) -> int:
    """Flag nodes as ru_verified from an external RU probe worker's verdict.

    The verdict is env-gated via RU_VERDICT_FILE: a JSON file holding the list of
    node strict_ids that an RU-side worker confirmed reachable from inside Russia.
    Accepts a bare JSON list of ids, or an object with a "verified"/"ids" key.
    When the env var is unset or the file is missing, nothing is flagged and
    sub_ru.txt is simply empty (no failure).
    """
    verdict_file = os.environ.get("RU_VERDICT_FILE", "")
    if not verdict_file:
        return 0
    if not os.path.exists(verdict_file):
        logger.warning(
            f"  RU verdict: {verdict_file} not found — sub_ru will be empty"
        )
        return 0
    try:
        with open(verdict_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("verified", data.get("ids", []))
        verified = {str(x) for x in data}
    except Exception as exc:
        logger.warning(f"  RU verdict: failed to load {verdict_file}: {exc}")
        return 0

    flagged = 0
    for n in nodes:
        if n.strict_id in verified:
            n.ru_verified = True
            flagged += 1
    logger.info(
        f"  RU verdict: flagged {flagged}/{len(nodes)} nodes as ru_verified "
        f"({len(verified)} ids in verdict)"
    )
    return flagged


async def main() -> None:
    start_time = time.perf_counter()

    shard_index = int(os.environ.get("SHARD_INDEX", "0"))
    shard_count = int(os.environ.get("SHARD_COUNT", "1"))

    GHA.drone_header(shard_index + 1, shard_count)

    try:
        GHA.phase("①", "BASES", "Loading RKN / TSPU whitelists")
        await RKNValidator.load_lists()
        GHA.endgroup()

        GHA.group("② PARSE — Fetching & Decoding Subscription Sources")
        source_health = SourceHealth(shard_index=shard_index if shard_count > 1 else -1)
        nodes_file = os.environ.get("NODES_FILE", "")
        if nodes_file:
            # Parse-once mode (US-004): nodes pre-parsed by an upstream job.
            with open(nodes_file, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
            all_nodes = [ProxyNode.model_validate(d) for d in raw_list]
            logger.info(f"Loaded {len(all_nodes)} nodes from {nodes_file}")
            parser = None
            source_metrics: dict = {}
        else:
            parser = LinkParser()
            all_nodes = await parser.fetch_and_parse(source_health=source_health)
            source_metrics = parser.metrics

        # --- Rolling pool: add historically-working nodes to the check set ---
        pool_path = "data/pool.json"
        pool_added = 0
        fresh_ids = {n.strict_id for n in all_nodes}
        if os.path.exists(pool_path):
            try:
                with open(pool_path, "r", encoding="utf-8") as f:
                    pool_entries = json.load(f)
                for entry in pool_entries:
                    uri = entry.get("uri", "")
                    if not uri:
                        continue
                    node = LinkParser.parse_link(uri)
                    if node and node.strict_id not in fresh_ids:
                        node.is_bs = RKNValidator.check_bs(node)
                        all_nodes.append(node)
                        fresh_ids.add(node.strict_id)
                        pool_added += 1
                if pool_added:
                    logger.info(
                        f"  Pool: added {pool_added} historically-working nodes to check set"
                    )
            except Exception as exc:
                logger.warning(f"  Pool: failed to load {pool_path}: {exc}")

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
        else:
            nodes = all_nodes

        GHA.section("②", "PARSE", "Fetching & decoding sources")
        GHA.row("collected", f"{len(all_nodes):>8,} nodes")
        if shard_count > 1:
            GHA.row(
                f"shard {shard_index + 1}/{shard_count}",
                f"{len(nodes):>8,} nodes  (round-robin slice)",
                last=True,
            )
        else:
            GHA.row("workload", f"{len(nodes):>8,} nodes", last=True)
        GHA.endgroup()

        GHA.phase("③", "ENGINE", "L4 TCP · L7 sing-box · champion speed test")
        inspector = Inspector()
        alive_nodes = await inspector.process_all(nodes)
        l4_dropped = inspector.l4_dropped
        GHA.endgroup()

        GHA.phase("④", "AGGREGATE", "Metrics & deduplication")

        for node in alive_nodes:
            if node.source_url in source_metrics:
                m = source_metrics[node.source_url]
                m["alive"] = m.get("alive", 0) + 1

        # Record source health & compute per-source yields
        source_yields: dict = {}
        for url, m in source_metrics.items():
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
            url for url, m in source_metrics.items()
            if m.get("parsed", 0) > 0 and m.get("alive", 0) == 0
        ]

        raw_alive = len(alive_nodes)
        unique_alive: dict = {}
        for n in alive_nodes:
            unique_alive[n.strict_id] = n
        alive_nodes = list(unique_alive.values())

        apply_ru_verdict(alive_nodes)

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

        GHA.row("L7 alive", f"{raw_alive:>8,} nodes", status="ok")
        GHA.row("unique", f"{len(alive_nodes):>8,} nodes")
        GHA.row("whitelist БС", f"{bs_count:>8,} nodes")
        GHA.row("blacklist ЧС", f"{len(alive_nodes) - bs_count:>8,} nodes")
        GHA.row("dead sources", f"{len(dead_sources):>8,}", status="warn" if dead_sources else "")
        GHA.row("⚡ top speed", f"{top_speed:>8.1f} Mbps", status="ok")
        GHA.row("📊 avg/med/p90", f"{avg_speed:.1f} / {median_speed:.1f} / {speed_p90:.1f} Mbps")
        top_countries_str = ', '.join(f"{c['code']}:{c['count']}" for c in country_stats[:5])
        GHA.row("🌍 countries", f"{len(country_stats)}  ({top_countries_str})", last=True)
        GHA.endgroup()

        GHA.phase("⑤", "EXPORT", "Writing subscription files")
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
