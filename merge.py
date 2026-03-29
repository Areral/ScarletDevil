# --- START OF FILE merge.py ---
import os
import json
import glob
import base64
import datetime
import asyncio
import aiohttp
from loguru import logger

import core.logger
from core.logger import GHA

from core.settings import CONFIG


def _vmess_dedup_key(line: str) -> str:
    if not line.startswith("vmess://"):
        return line.split("#")[0]
    try:
        raw = line[8:]
        padded = raw + "=" * (-len(raw) % 4)
        data = json.loads(base64.b64decode(padded).decode("utf-8"))
        data.pop("ps", None)
        normalized = json.dumps(data, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
        return "vmess::" + base64.b64encode(normalized.encode()).decode()
    except Exception:
        return line.split("#")[0]


async def send_telegram_report(stats: dict) -> None:
    if not CONFIG.TG_BOT_TOKEN or not CONFIG.TG_CHAT_ID:
        logger.warning("  TG_BOT_TOKEN / TG_CHAT_ID не заданы — пропуск отправки.")
        return

    public_url = CONFIG.app.get("public_url", "")
    dead_text = (
        f"\n\n🗑️ <b>Dead Sources:</b> {len(stats['dead_sources'])}"
        if stats["dead_sources"] else ""
    )

    msg = (
        f"🦇 <b>Scarlet Devil | Matrix Report</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 <b>Собрано (Total):</b> <code>{stats['parsed']:,}</code>\n"
        f"🛡️ <b>Убито L4:</b> <code>{stats['l4_dropped']:,}</code>\n"
        f"🔋 <b>Живых (Unique):</b> <code>{stats['unique_alive']:,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👻 <b>Nightbird (БС):</b> <code>{stats['bs_count']:,}</code>\n"
        f"☄️ <b>Vampire Dash (ЧС):</b> <code>{stats['unique_alive'] - stats['bs_count']:,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Max Speed:</b> <code>{stats['top_speed']:.1f} Mbps</code>\n\n"
        f"⚙️ <b>Matrix Performance:</b>\n"
    )
    for shard_idx, dur in sorted(stats["durations"].items()):
        msg += f"   └ Drone {shard_idx}: <code>{dur:.1f}s</code>\n"
    msg += (
        f"{dead_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🩸 <a href='{public_url}'>Mansion Status</a>"
    )

    target_topic = 7
    if CONFIG.TG_TOPIC_ID:
        try:
            target_topic = int(CONFIG.TG_TOPIC_ID)
        except ValueError:
            pass

    payload = {
        "chat_id": CONFIG.TG_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "message_thread_id": target_topic,
    }
    url = f"https://api.telegram.org/bot{CONFIG.TG_BOT_TOKEN}/sendMessage"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                resp.raise_for_status()
                logger.info("  Telegram report доставлен ✔")
        except Exception as exc:
            logger.error(f"  Ошибка отправки в Telegram: {exc}")


def build_html(total_alive: int, top_speed: float) -> None:
    template_path = "config/web/template.html"
    if not os.path.exists(template_path):
        logger.warning(f"  Шаблон не найден: {template_path} — пропуск.")
        return

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            tpl = f.read()

        css = ""
        if os.path.exists("config/web/style.css"):
            with open("config/web/style.css", "r", encoding="utf-8") as f:
                css = f.read()

        js = ""
        if os.path.exists("config/web/main.js"):
            with open("config/web/main.js", "r", encoding="utf-8") as f:
                js = f.read()

        now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
        public_url = CONFIG.app.get("public_url", "")

        html_out = (
            tpl.replace("{{INJECT_CSS}}", css)
               .replace("{{INJECT_JS}}", js)
               .replace("{{UPDATE_TIME}}", now.strftime("%d.%m %H:%M"))
               .replace("{{PROXY_COUNT}}", str(total_alive))
               .replace("{{MAX_SPEED}}", str(int(top_speed)))
               .replace("{{SUB_LINK}}", f"{public_url}/sub")
        )
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_out)

        logger.info(f"  index.html сгенерирован ({total_alive:,} узлов, {int(top_speed)} Mbps)")
    except Exception as exc:
        logger.error(f"  Ошибка генерации HTML: {exc}")


def merge_subscription_files(pattern: str, output_file: str, title: str) -> int:
    files = glob.glob(pattern)
    unique_map: dict = {}

    for f_path in files:
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    dedup_key = _vmess_dedup_key(line)
                    if dedup_key not in unique_map:
                        unique_map[dedup_key] = line
        except Exception:
            pass

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"#profile-title: {title}\n")
        f.write("#profile-update-interval: 6\n")
        for link in sorted(unique_map.values()):
            f.write(f"{link}\n")

    logger.info(f"  {output_file:<20} ← {len(files):>2} shards  →  {len(unique_map):>6,} unique nodes")
    return len(unique_map)


def main() -> None:
    GHA.nexus_header()

    stats: dict = {
        "parsed":       0,
        "l4_dropped":   0,
        "top_speed":    0.0,
        "dead_sources": set(),
        "durations":    {},
        "unique_alive": 0,
        "bs_count":     0,
    }

    GHA.group("① COLLECT — Reading Drone Telemetry")
    stat_files = glob.glob("shards_temp/shard-data-*/stats_*.json")
    logger.info(f"  Найдено файлов статистики: {len(stat_files)}")

    if not stat_files:
        GHA.warning("No stat files found — merge will produce empty subscriptions.")

    for f_path in stat_files:
        try:
            shard_idx = f_path.split("stats_")[-1].replace(".json", "")
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            alive   = data.get("alive", 0)
            parsed  = data.get("parsed", 0)
            l4drop  = data.get("l4_dropped", 0)
            spd     = data.get("top_speed", 0.0)
            dur     = data.get("duration", 0.0)

            stats["parsed"]     += parsed
            stats["l4_dropped"] += l4drop
            if spd > stats["top_speed"]:
                stats["top_speed"] = spd
            stats["durations"][shard_idx] = dur
            for src in data.get("dead_sources", []):
                stats["dead_sources"].add(src)

            logger.info(
                f"  Drone {shard_idx:<4}  parsed={parsed:>6,}  "
                f"alive={alive:>5,}  speed={spd:>6.1f} Mbps  t={dur:.0f}s"
            )
        except Exception as exc:
            logger.warning(f"  Ошибка чтения {f_path}: {exc}")
    GHA.endgroup()

    GHA.group("② MERGE — Deduplicating Subscription Files")
    stats["unique_alive"] = merge_subscription_files(
        "shards_temp/shard-data-*/sub_all_*.txt",
        "sub_all.txt",
        "Scarlet Devil | Gungnir (MIX)",
    )
    stats["bs_count"] = merge_subscription_files(
        "shards_temp/shard-data-*/sub_bs_*.txt",
        "sub_bs.txt",
        "Scarlet Devil | Nightbird (БС)",
    )
    merge_subscription_files(
        "shards_temp/shard-data-*/sub_chs_*.txt",
        "sub_chs.txt",
        "Scarlet Devil | Vampire Dash (ЧС)",
    )
    GHA.endgroup()

    GHA.group("③ BUILD — Compiling Dashboard (index.html)")
    build_html(stats["unique_alive"], stats["top_speed"])
    GHA.endgroup()

    GHA.group("④ NOTIFY — Sending Telegram Report")
    asyncio.run(send_telegram_report(stats))
    GHA.endgroup()

    GHA.nexus_summary(
        parsed=stats["parsed"],
        l4_dropped=stats["l4_dropped"],
        unique_alive=stats["unique_alive"],
        bs_count=stats["bs_count"],
        top_speed=stats["top_speed"],
        dead_sources=len(stats["dead_sources"]),
        durations=stats["durations"],
    )

    if stats["unique_alive"] == 0:
        GHA.error("Nexus produced zero alive nodes — check drone logs.")


if __name__ == "__main__":
    main()
