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


# ─────────────────────────────────────────────────────────────────────────────
#  Scarlet palette — raw ANSI. GitHub Actions renders these; NO_COLOR disables.
# ─────────────────────────────────────────────────────────────────────────────
class C:
    _ON = (
        sys.stdout.isatty() or os.environ.get("GITHUB_ACTIONS") == "true"
    ) and os.environ.get("NO_COLOR") is None

    RESET = "\033[0m" if _ON else ""
    BOLD = "\033[1m" if _ON else ""
    DIM = "\033[2m" if _ON else ""

    SCARLET = "\033[38;5;197m" if _ON else ""   # hero red — headers
    ROSE = "\033[38;5;211m" if _ON else ""      # soft pink — section titles
    OK = "\033[38;5;78m" if _ON else ""         # green — success
    WARN = "\033[38;5;221m" if _ON else ""      # amber — warnings
    BAD = "\033[38;5;203m" if _ON else ""       # red — failures
    CYAN = "\033[38;5;80m" if _ON else ""       # numbers / accents
    GREY = "\033[38;5;245m" if _ON else ""      # labels / tree glyphs

    @classmethod
    def wrap(cls, color: str, text: str) -> str:
        return f"{color}{text}{cls.RESET}" if color else text


class GHA:
    # Tree glyphs
    _TEE = "├─"
    _END = "└─"
    _PIPE = "│"

    # True only inside GitHub Actions, where ::group::/::endgroup:: are real
    # workflow commands. Elsewhere we print a plain styled header instead of the
    # literal "::group::…" text so local runs stay readable.
    _GHA = os.environ.get("GITHUB_ACTIONS") == "true"

    # ── GitHub Actions log folding ──────────────────────────────────────────
    @classmethod
    def group(cls, title: str) -> None:
        if cls._GHA:
            print(f"::group::{title}", flush=True)
        else:
            print(flush=True)
            print(cls._c(C.SCARLET + C.BOLD, title), flush=True)

    @classmethod
    def endgroup(cls) -> None:
        if cls._GHA:
            print("::endgroup::", flush=True)

    @classmethod
    def phase(cls, marker: str, title: str, desc: str = "") -> None:
        """Open one collapsible phase header (a GitHub Actions fold in CI)."""
        cls.group(f"{marker} {title}" + (f" — {desc}" if desc else ""))

    @staticmethod
    def notice(msg: str) -> None:
        print(f"::notice::{msg}", flush=True)

    @staticmethod
    def warning(msg: str) -> None:
        print(f"::warning::{msg}", flush=True)

    @staticmethod
    def error(msg: str) -> None:
        print(f"::error::{msg}", flush=True)

    # ── Banners ─────────────────────────────────────────────────────────────
    @classmethod
    def _banner(cls, glyph: str, title: str, color: str) -> None:
        line = "═" * 58
        print(flush=True)
        print(cls._c(color, f"  ╓{line}"), flush=True)
        print(
            cls._c(color, "  ║  ")
            + cls._c(color + C.BOLD, f"{glyph}  {title}"),
            flush=True,
        )
        print(cls._c(color, f"  ╙{line}"), flush=True)
        print(flush=True)

    @staticmethod
    def _c(color: str, text: str) -> str:
        return C.wrap(color, text)

    @classmethod
    def drone_header(cls, drone_idx: int, drone_total: int) -> None:
        cls._banner("🦇", f"SCARLET DEVIL · DRONE {drone_idx}/{drone_total}", C.SCARLET)

    @classmethod
    def nexus_header(cls) -> None:
        cls._banner("🩸", "SCARLET NEXUS · FINAL MERGE & PUBLISH", C.SCARLET)

    # ── Tree rows ───────────────────────────────────────────────────────────
    @classmethod
    def row(
        cls,
        label: str,
        value: str = "",
        last: bool = False,
        status: str = "",
    ) -> None:
        """A tree branch row. status ∈ {'ok','warn','bad',''} colors the value."""
        glyph = cls._END if last else cls._TEE
        tree = cls._c(C.GREY, glyph)
        lab = cls._c(C.GREY, f"{label:<16}")
        vcolor = {
            "ok": C.OK,
            "warn": C.WARN,
            "bad": C.BAD,
        }.get(status, C.CYAN)
        val = cls._c(vcolor, value) if value else ""
        print(f"  {tree} {lab}{val}", flush=True)

    @classmethod
    def note(cls, text: str, last: bool = False) -> None:
        """A free-text tree branch (no value column)."""
        glyph = cls._END if last else cls._TEE
        print(f"  {cls._c(C.GREY, glyph)} {cls._c(C.GREY, text)}", flush=True)

    @classmethod
    def blank(cls) -> None:
        print(flush=True)

    # ── Summaries ───────────────────────────────────────────────────────────
    @classmethod
    def _summary(cls, title: str, rows: list, color: str) -> None:
        print(flush=True)
        print(cls._c(color + C.BOLD, f"  ◤ {title}"), flush=True)
        n = len(rows)
        for i, (label, value, status) in enumerate(rows):
            if label == "---":
                print(f"  {cls._c(C.GREY, cls._PIPE)}", flush=True)
                continue
            last = i == n - 1
            cls.row(label, value, last=last, status=status)
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
        survival = (l7_alive / parsed * 100) if parsed else 0.0
        rows = [
            ("parsed", f"{parsed:>8,} nodes", ""),
            ("L4 killed", f"{l4_dropped:>8,} nodes", "warn"),
            ("L7 alive", f"{l7_alive:>8,} nodes", "ok"),
            ("unique", f"{unique:>8,} nodes  ({survival:.1f}% survival)", "ok"),
            ("---", "", ""),
            ("whitelist БС", f"{bs_count:>8,} nodes", ""),
            ("blacklist ЧС", f"{unique - bs_count:>8,} nodes", ""),
            ("---", "", ""),
            ("⚡ top speed", f"{top_speed:>8.1f} Mbps", "ok"),
            ("🗑 dead src", f"{dead_sources:>8,}", "warn" if dead_sources else ""),
            ("⏱ duration", f"{duration:>8.1f} sec", ""),
        ]
        cls._summary(f"DRONE {drone_idx} · MISSION COMPLETE", rows, C.SCARLET)

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
        survival = (unique_alive / parsed * 100) if parsed else 0.0
        rows = [
            ("total parsed", f"{parsed:>8,} nodes", ""),
            ("L4 killed", f"{l4_dropped:>8,} nodes", "warn"),
            ("unique alive", f"{unique_alive:>8,} nodes  ({survival:.2f}% survival)", "ok"),
            ("---", "", ""),
            ("whitelist БС", f"{bs_count:>8,} nodes", ""),
            ("blacklist ЧС", f"{unique_alive - bs_count:>8,} nodes", ""),
            ("---", "", ""),
            ("⚡ top speed", f"{top_speed:>8.1f} Mbps", "ok"),
            ("🗑 dead src", f"{dead_sources:>8,}", "warn" if dead_sources else ""),
        ]
        if durations:
            rows.append(("---", "", ""))
            for shard_idx, dur in sorted(durations.items()):
                rows.append((f"drone {shard_idx}", f"{dur:>8.1f} sec", ""))
        cls._summary("NEXUS · PUBLISH COMPLETE", rows, C.SCARLET)
