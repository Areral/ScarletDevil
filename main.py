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
from core.parser import LinkParser
from core.engine import Inspector
from core.exporter import Exporter
from core.validator import RKNValidator
from core.models import ProxyNode


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
        nodes_file = os.environ.get("NODES_FILE", "")
        if nodes_file:
            with open(nodes_file, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
            all_nodes = [ProxyNode.model_validate(d) for d in raw_list]
            logger.info(f"Loaded {len(all_nodes)} nodes from {nodes_file}")
            source_metrics: dict = {}
        else:
            parser = LinkParser()
            all_nodes = await parser.fetch_and_parse()
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
            nodes = all_nodes[shard_index::shard_count]
            logger.info(
                f"  Shard {shard_index + 1}/{shard_count} — "
                f"({len(nodes):,} / {len(all_nodes):,} nodes, round-robin)"
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
            if node.source_url in source_metrics:
                m = source_metrics[node.source_url]
                m["alive"] = m.get("alive", 0) + 1

        dead_sources = [
            url for url, m in source_metrics.items()
            if m.get("parsed", 0) > 0 and m.get("alive", 0) == 0
        ]

        unique_alive: dict = {}
        for n in alive_nodes:
            unique_alive[n.strict_id] = n
        alive_nodes = list(unique_alive.values())

        bs_count = sum(1 for n in alive_nodes if n.is_bs)
        top_speed = max((n.speed for n in alive_nodes), default=0.0)

        logger.info(f"  Unique alive     {len(alive_nodes):>8,}  nodes")
        logger.info(f"  БС (whitelist)   {bs_count:>8,}  nodes")
        logger.info(f"  ЧС (blacklist)   {len(alive_nodes) - bs_count:>8,}  nodes")
        logger.info(f"  Dead sources     {len(dead_sources):>8,}")
        logger.info(f"  ⚡ Top speed      {top_speed:>8.1f}  Mbps")
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
