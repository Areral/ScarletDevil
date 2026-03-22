# --- START OF FILE core/logger.py ---
import sys
import os
from loguru import logger

os.makedirs("data", exist_ok=True)
logger.remove()

logger.add(
    sys.stdout,
    format="<dim>{time:HH:mm:ss}</dim>  <level>{level: <7}</level>  {message}",
    level="INFO",
    colorize=True,
    enqueue=False,
)

logger.add(
    "data/debug.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} — {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="3 days",
    enqueue=True,
)


class GHA:

    _W = 64

    @staticmethod
    def group(title: str) -> None:
        print(f"::group::{title}", flush=True)

    @staticmethod
    def endgroup() -> None:
        print("::endgroup::", flush=True)

    @staticmethod
    def notice(msg: str) -> None:
        print(f"::notice::{msg}", flush=True)

    @staticmethod
    def warning(msg: str) -> None:
        print(f"::warning::{msg}", flush=True)

    @staticmethod
    def error(msg: str) -> None:
        print(f"::error::{msg}", flush=True)

    @staticmethod
    def _pad(text: str, width: int) -> str:
        if len(text) > width:
            text = text[:width - 1] + "…"
        return text + " " * (width - len(text))

    @classmethod
    def _box_top(cls) -> None:
        print(f"  ╔{'═' * cls._W}╗", flush=True)

    @classmethod
    def _box_bot(cls) -> None:
        print(f"  ╚{'═' * cls._W}╝", flush=True)

    @classmethod
    def _box_div(cls) -> None:
        print(f"  ╠{'═' * cls._W}╣", flush=True)

    @classmethod
    def _box_title(cls, text: str) -> None:
        inner = cls._pad(text, cls._W - 2)
        print(f"  ║  {inner}  ║", flush=True)

    @classmethod
    def _box_row(cls, label: str, value: str) -> None:
        content = f"  {label:<24}{value}"
        padded = cls._pad(content, cls._W - 2)
        print(f"  ║  {padded}  ║", flush=True)

    @classmethod
    def _box_blank(cls) -> None:
        print(f"  ║{' ' * cls._W}  ║", flush=True)

    @classmethod
    def drone_header(cls, drone_idx: int, drone_total: int) -> None:
        print(flush=True)
        cls._box_top()
        cls._box_title(f"🦇  SCARLET DEVIL NETWORK — DRONE {drone_idx} / {drone_total}")
        cls._box_bot()
        print(flush=True)

    @classmethod
    def nexus_header(cls) -> None:
        print(flush=True)
        cls._box_top()
        cls._box_title("🩸  SCARLET NEXUS — FINAL MERGE & PUBLISH")
        cls._box_bot()
        print(flush=True)

    @classmethod
    def drone_summary(
        cls,
        drone_idx: int,
        parsed: int,
        l4_dropped: int,
        l7_alive: int,
        unique: int,
        bs_count: int,
        top_speed: float,
        duration: float,
        dead_sources: int,
    ) -> None:
        print(flush=True)
        cls._box_top()
        cls._box_title(f"DRONE {drone_idx} — MISSION COMPLETE")
        cls._box_div()
        cls._box_row("Parsed (shard)",        f"{parsed:>8,}  nodes")
        cls._box_row("L4 killed",             f"{l4_dropped:>8,}  nodes")
        cls._box_row("L7 alive",              f"{l7_alive:>8,}  nodes")
        cls._box_row("Unique (post-dedup)",   f"{unique:>8,}  nodes")
        cls._box_div()
        cls._box_row("  └─ БС (whitelist)",   f"{bs_count:>8,}  nodes")
        cls._box_row("  └─ ЧС (blacklist)",   f"{unique - bs_count:>8,}  nodes")
        cls._box_div()
        cls._box_row("⚡ Top speed",           f"{top_speed:>8.1f}  Mbps")
        cls._box_row("🗑  Dead sources",        f"{dead_sources:>8,}")
        cls._box_row("⏱  Duration",            f"{duration:>8.1f}  sec")
        cls._box_bot()
        print(flush=True)

    @classmethod
    def nexus_summary(
        cls,
        parsed: int,
        l4_dropped: int,
        unique_alive: int,
        bs_count: int,
        top_speed: float,
        dead_sources: int,
        durations: dict,
    ) -> None:
        print(flush=True)
        cls._box_top()
        cls._box_title("NEXUS — PUBLISH COMPLETE")
        cls._box_div()
        cls._box_row("Total parsed",          f"{parsed:>8,}  nodes")
        cls._box_row("L4 killed (all drones)",f"{l4_dropped:>8,}  nodes")
        cls._box_row("Unique alive",          f"{unique_alive:>8,}  nodes")
        cls._box_div()
        cls._box_row("  └─ БС (whitelist)",   f"{bs_count:>8,}  nodes")
        cls._box_row("  └─ ЧС (blacklist)",   f"{unique_alive - bs_count:>8,}  nodes")
        cls._box_div()
        cls._box_row("⚡ Top speed",           f"{top_speed:>8.1f}  Mbps")
        cls._box_row("🗑  Dead sources",        f"{dead_sources:>8,}")
        if durations:
            cls._box_div()
            for shard_idx, dur in sorted(durations.items()):
                cls._box_row(f"  Drone {shard_idx} duration", f"{dur:>8.1f}  sec")
        cls._box_bot()
        print(flush=True)
