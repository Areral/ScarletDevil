# --- START OF FILE parse_only.py ---
"""Parse-once entrypoint (AUDIT §2.1).

Runs whitelist loading + source fetch/parse a SINGLE time and writes the
collected nodes to data/nodes.json (a list of ProxyNode.model_dump(by_alias=True)
dicts). The crawler drones then read that file via NODES_FILE instead of each
re-fetching and re-parsing every source. This removes the 4× redundant parsing
that contiguous-shard slicing in main.py caused.
"""
import asyncio
import json
import os
import sys
from loguru import logger

import core.logger  # noqa: F401  (configures loguru sink)
from core.logger import GHA
from core.parser import LinkParser
from core.validator import RKNValidator

NODES_FILE_DEFAULT = "data/nodes.json"


async def main() -> None:
    out_path = os.environ.get("NODES_FILE", NODES_FILE_DEFAULT)

    try:
        GHA.group("① BASES — Loading RKN / TSPU Whitelists")
        await RKNValidator.load_lists()
        GHA.endgroup()

        GHA.group("② PARSE — Fetching & Decoding Subscription Sources")
        parser = LinkParser()
        all_nodes = await parser.fetch_and_parse()
        GHA.endgroup()

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([n.model_dump(by_alias=True) for n in all_nodes], f)

        logger.info(f"  parse_only: wrote {len(all_nodes):,} nodes → {out_path}")

        if not all_nodes:
            GHA.warning("parse_only: zero nodes parsed.")

    except Exception as exc:
        GHA.error(f"parse_only critical failure: {exc}")
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
