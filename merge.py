# --- START OF FILE merge.py ---
import os
import re
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

    # Overall survival rate (US-C07): unique alive / total parsed
    parsed = stats.get("parsed", 0)
    survival_rate = (stats["unique_alive"] / parsed * 100.0) if parsed > 0 else 0.0
    survival_warn = " ⚠️" if survival_rate < 0.5 else ""

    msg = (
        f"🦇 <b>Scarlet Devil | Matrix Report</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 <b>Собрано (Total):</b> <code>{stats['parsed']:,}</code>\n"
        f"🛡️ <b>Убито L4:</b> <code>{stats['l4_dropped']:,}</code>\n"
        f"🔋 <b>Живых (Unique):</b> <code>{stats['unique_alive']:,}</code>\n"
        f"🩺 <b>Survival Rate:</b> <code>{survival_rate:.2f}%</code>{survival_warn}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👻 <b>Nightbird (БС):</b> <code>{stats['bs_count']:,}</code>\n"
        f"☄️ <b>Vampire Dash (ЧС):</b> <code>{stats['unique_alive'] - stats['bs_count']:,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Max Speed:</b> <code>{stats['top_speed']:.1f} Mbps</code>\n"
    )

    # Best / worst drone by survival rate (US-C07)
    drone_surv = stats.get("drone_survival", {})
    if drone_surv:
        best = max(drone_surv.items(), key=lambda kv: kv[1])
        worst = min(drone_surv.items(), key=lambda kv: kv[1])
        msg += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏆 <b>Лучший дрон:</b> <code>#{best[0]} ({best[1]:.2f}%)</code>\n"
            f"🪫 <b>Худший дрон:</b> <code>#{worst[0]} ({worst[1]:.2f}%)</code>\n"
        )

    # Top-3 countries by node count (US-C07)
    countries = stats.get("country_stats", [])[:3]
    if countries:
        msg += f"━━━━━━━━━━━━━━━━━━\n🌍 <b>Топ стран:</b>\n"
        for c in countries:
            msg += f"   └ <code>{c['code']}</code>: {c['count']:,}\n"

    # Top-3 sources by yield (US-C07)
    top_sources = stats.get("top_sources", [])[:3]
    if top_sources:
        msg += f"━━━━━━━━━━━━━━━━━━\n📊 <b>Топ источников (yield):</b>\n"
        for s in top_sources:
            msg += f"   └ <code>{s['yield_pct']}%</code> ({s['alive']} alive)\n"

    # Failure reason breakdown (US-C07) — top 5 reasons
    failure_reasons = stats.get("failure_reasons", {})
    if failure_reasons:
        ranked_fail = sorted(failure_reasons.items(), key=lambda kv: kv[1], reverse=True)[:5]
        msg += f"━━━━━━━━━━━━━━━━━━\n🔻 <b>Причины отказов:</b>\n"
        for reason, cnt in ranked_fail:
            if cnt <= 0:
                continue
            msg += f"   └ <code>{reason}</code>: {cnt:,}\n"

    msg += f"━━━━━━━━━━━━━━━━━━\n⚙️ <b>Matrix Performance:</b>\n"
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
                GHA.row("Telegram", "report delivered ✔", last=True, status="ok")
        except Exception as exc:
            logger.error(f"  Ошибка отправки в Telegram: {exc}")


def build_html(total_alive: int, top_speed: float, stats: dict) -> None:
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

        country_stats_json = json.dumps(stats.get("country_stats", []), ensure_ascii=False)

        # Consolidated node statistics blob — single source of truth for the
        # client-side charts (data attributes below mirror these values).
        node_stats = {
            "total":     int(total_alive),
            "max_speed": int(top_speed),
            "avg_speed": round(stats.get("avg_speed", 0.0), 1),
            "median_speed": round(stats.get("median_speed", 0.0), 1),
            "speed_p90": round(stats.get("speed_percentile_90", 0.0), 1),
            "bs":        int(stats.get("bs_count", 0)),
            "chs":       int(stats.get("chs_count", 0)),
            "vless":     int(stats.get("vless_count", 0)),
            "vmess":     int(stats.get("vmess_count", 0)),
            "trojan":    int(stats.get("trojan_count", 0)),
            "ss":        int(stats.get("ss_count", 0)),
            "hy2":       int(stats.get("hy2_count", 0)),
            "countries": stats.get("country_stats", []),
        }
        node_stats_json = json.dumps(node_stats, ensure_ascii=False)

        html_out = (
            tpl.replace("{{INJECT_CSS}}", css)
               .replace("{{INJECT_JS}}", js)
               .replace("{{UPDATE_TIME_ISO}}", now.isoformat())
               .replace("{{UPDATE_TIME}}", now.strftime("%d.%m %H:%M"))
               .replace("{{PROXY_COUNT}}", str(total_alive))
               .replace("{{MAX_SPEED}}", str(int(top_speed)))
               .replace("{{AVG_SPEED}}", str(round(stats.get("avg_speed", 0.0), 1)))
               .replace("{{MEDIAN_SPEED}}", str(round(stats.get("median_speed", 0.0), 1)))
               .replace("{{SPEED_P90}}", str(round(stats.get("speed_percentile_90", 0.0), 1)))
               .replace("{{BS_COUNT}}", str(stats.get("bs_count", 0)))
               .replace("{{CHS_COUNT}}", str(stats.get("chs_count", 0)))
               .replace("{{VLESS_COUNT}}", str(stats.get("vless_count", 0)))
               .replace("{{VMESS_COUNT}}", str(stats.get("vmess_count", 0)))
               .replace("{{TROJAN_COUNT}}", str(stats.get("trojan_count", 0)))
               .replace("{{SS_COUNT}}", str(stats.get("ss_count", 0)))
               .replace("{{HY2_COUNT}}", str(stats.get("hy2_count", 0)))
               .replace("{{COUNTRY_STATS_JSON}}", country_stats_json)
               .replace("{{NODE_STATS_JSON}}", node_stats_json)
        )

        # Safety net: a placeholder in the template with no matching .replace()
        # above must never reach the published page (the visible "{{MAX_SPEED}}"
        # bug). Rewrite any survivor to an em-dash and shout about it in the log.
        leftover = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", html_out)))
        if leftover:
            logger.warning(f"  Незаполненные плейсхолдеры (заменены на «—»): {leftover}")
            html_out = re.sub(r"\{\{[A-Z0-9_]+\}\}", "—", html_out)

        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html_out)

        GHA.row("index.html", f"{total_alive:,} nodes · {int(top_speed)} Mbps", last=True, status="ok")
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
        for link in unique_map.values():
            f.write(f"{link}\n")

    GHA.row(f"{output_file}", f"{len(files)} shards → {len(unique_map):,} unique")
    return len(unique_map)


def _extract_country_stats(sub_file: str, top_n: int = 10) -> list:
    """Extract country codes from subscription URL fragments (#NN-name)."""
    import re
    country_re = re.compile(r"#(\w{2})[\s\-_]")

    country_counts: dict = {}
    if not os.path.exists(sub_file):
        return []

    try:
        with open(sub_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = country_re.search(line)
                if m:
                    code = m.group(1).upper()
                    # Filter out non-country-like codes (numeric, common false positives)
                    if code.isalpha() and len(code) == 2:
                        country_counts[code] = country_counts.get(code, 0) + 1
    except Exception:
        pass

    # Sort by count descending, take top N
    sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"code": code, "count": cnt, "flag": ""} for code, cnt in sorted_countries]


POOL_PATH = "data/pool.json"


def load_pool(path: str = POOL_PATH) -> list:
    """Load the rolling pool of historically-working nodes."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            pool = json.load(f)
        return pool if isinstance(pool, list) else []
    except Exception:
        return []


def save_pool(pool: list, path: str = POOL_PATH) -> None:
    """Persist the rolling pool to disk."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)


def update_pool(alive_uris: set, path: str = POOL_PATH) -> dict:
    """Update the rolling pool based on this run's surviving nodes.

    - Pool nodes that survived: fail_count reset to 0, last_seen updated.
    - Pool nodes that didn't survive: fail_count incremented.
    - New survivors: added to pool with fail_count=0.
    - Nodes with fail_count >= 3: evicted.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    existing = load_pool(path)

    pool_by_uri = {entry["uri"]: entry for entry in existing}

    updated = []
    evicted = 0
    added = 0

    for uri, entry in pool_by_uri.items():
        if uri in alive_uris:
            entry["fail_count"] = 0
            entry["last_seen"] = now
            updated.append(entry)
            alive_uris.discard(uri)
        else:
            entry["fail_count"] = entry.get("fail_count", 0) + 1
            if entry["fail_count"] < 3:
                updated.append(entry)
            else:
                evicted += 1

    for uri in alive_uris:
        updated.append({"uri": uri, "last_seen": now, "fail_count": 0})
        added += 1

    save_pool(updated, path)

    logger.info(
        f"  Pool updated: {len(updated)} entries "
        f"(evicted={evicted}, new={added})"
    )
    return {"size": len(updated), "evicted": evicted, "added": added}


def main() -> None:
    GHA.nexus_header()

    stats: dict = {
        "parsed":       0,
        "l4_dropped":   0,
        "top_speed":    0.0,
        "avg_speed":    0.0,
        "median_speed": 0.0,
        "speed_percentile_90": 0.0,
        "dead_sources": set(),
        "durations":    {},
        "unique_alive": 0,
        "bs_count":     0,
        "country_stats": [],
        "drone_survival": {},
        "failure_reasons": {},
        "top_sources":  [],
    }

    GHA.phase("①", "COLLECT", "Reading drone telemetry")
    stat_files = glob.glob("shards_temp/shard-data-*/stats_*.json")
    GHA.row("stat files", f"{len(stat_files)} found")

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

            # Per-drone survival rate (US-C07): alive / parsed
            if parsed > 0:
                stats["drone_survival"][shard_idx] = alive / parsed * 100.0

            # Aggregate failure reasons (US-C07): L4 reasons + L7 stats breakdown
            for reason, cnt in (data.get("l4_failure_reasons") or {}).items():
                if reason == "total":
                    continue
                stats["failure_reasons"][reason] = stats["failure_reasons"].get(reason, 0) + cnt
            for reason, cnt in (data.get("l7_stats") or {}).items():
                if reason in ("total", "survived"):
                    continue
                if not isinstance(cnt, int):
                    continue
                stats["failure_reasons"][reason] = stats["failure_reasons"].get(reason, 0) + cnt

            # Aggregate speed stats (US-C04) — weighted by drone alive count
            drone_alive = alive
            drone_avg = data.get("avg_speed", 0.0)
            drone_med = data.get("median_speed", 0.0)
            drone_p90 = data.get("speed_percentile_90", 0.0)
            if drone_alive > 0:
                # Weighted running average for avg_speed
                old_total = stats.get("_alive_for_avg", 0)
                old_avg = stats["avg_speed"]
                new_total = old_total + drone_alive
                stats["avg_speed"] = (old_avg * old_total + drone_avg * drone_alive) / new_total if new_total > 0 else 0.0
                stats["_alive_for_avg"] = new_total
                # For median/p90: track the best across drones (best-effort aggregation)
                if drone_med > stats["median_speed"]:
                    stats["median_speed"] = drone_med
                if drone_p90 > stats["speed_percentile_90"]:
                    stats["speed_percentile_90"] = drone_p90

            # Aggregate country stats from drone GeoIP data (US-C04)
            drone_countries = data.get("country_stats", [])
            if drone_countries:
                merged_countries = {c["code"]: c["count"] for c in stats["country_stats"]}
                for c in drone_countries:
                    code = c["code"]
                    merged_countries[code] = merged_countries.get(code, 0) + c["count"]
                sorted_merged = sorted(merged_countries.items(), key=lambda x: x[1], reverse=True)[:10]
                stats["country_stats"] = [{"code": cc, "count": cnt, "flag": ""} for cc, cnt in sorted_merged]

            logger.info(
                f"  Drone {shard_idx:<4}  parsed={parsed:>6,}  "
                f"alive={alive:>5,}  speed={spd:>6.1f} Mbps  t={dur:.0f}s"
            )
        except Exception as exc:
            logger.warning(f"  Ошибка чтения {f_path}: {exc}")

    # Aggregate source yields across all drones for monitoring
    all_yields: dict = {}
    for f_path in stat_files:
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for url, yd in data.get("source_yields", {}).items():
                existing = all_yields.get(url, {"parsed": 0, "alive": 0})
                existing["parsed"] += yd.get("parsed", 0)
                existing["alive"] += yd.get("alive", 0)
                all_yields[url] = existing
        except Exception:
            pass

    if all_yields:
        ranked = sorted(
            all_yields.items(),
            key=lambda kv: kv[1]["alive"] / max(kv[1]["parsed"], 1),
            reverse=True,
        )
        top_n = min(5, len(ranked))
        GHA.row(f"top-{top_n} yield", "by source", status="ok")
        for url, yd in ranked[:top_n]:
            yp = yd["alive"] / max(yd["parsed"], 1) * 100
            stats["top_sources"].append({"url": url, "alive": yd["alive"], "yield_pct": round(yp, 1)})
            GHA.note(f"  {yp:5.1f}%  alive={yd['alive']:>4}  parsed={yd['parsed']:>5}  {url[:80]}")
        if len(ranked) > top_n:
            bottom_n = min(3, len(ranked) - top_n)
            GHA.row(f"bottom-{bottom_n} yield", "by source", status="warn")
            for url, yd in ranked[-bottom_n:]:
                yp = yd["alive"] / max(yd["parsed"], 1) * 100
                GHA.note(f"  {yp:5.1f}%  alive={yd['alive']:>4}  parsed={yd['parsed']:>5}  {url[:80]}")

    GHA.endgroup()

    GHA.phase("②", "MERGE", "Deduplicating subscription files")
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
    stats["chs_count"] = merge_subscription_files(
        "shards_temp/shard-data-*/sub_chs_*.txt",
        "sub_chs.txt",
        "Scarlet Devil | Vampire Dash (ЧС)",
    )
    stats["vless_count"] = merge_subscription_files(
        "shards_temp/shard-data-*/sub_vless_*.txt",
        "sub_vless.txt",
        "Scarlet Devil | VLESS",
    )
    stats["vmess_count"] = merge_subscription_files(
        "shards_temp/shard-data-*/sub_vmess_*.txt",
        "sub_vmess.txt",
        "Scarlet Devil | VMess",
    )
    stats["trojan_count"] = merge_subscription_files(
        "shards_temp/shard-data-*/sub_trojan_*.txt",
        "sub_trojan.txt",
        "Scarlet Devil | Trojan",
    )
    stats["ss_count"] = merge_subscription_files(
        "shards_temp/shard-data-*/sub_ss_*.txt",
        "sub_ss.txt",
        "Scarlet Devil | Shadowsocks",
    )
    stats["hy2_count"] = merge_subscription_files(
        "shards_temp/shard-data-*/sub_hy2_*.txt",
        "sub_hy2.txt",
        "Scarlet Devil | Hysteria2",
    )
    merge_subscription_files(
        "shards_temp/shard-data-*/sub_ru_*.txt",
        "sub_ru.txt",
        "Scarlet Devil | Remilia (RU-verified)",
    )

    # Build country distribution: prefer drone GeoIP data, fall back to URL parsing
    if not stats["country_stats"]:
        stats["country_stats"] = _extract_country_stats("sub_all.txt")
    else:
        GHA.row("🌍 GeoIP", f"{len(stats['country_stats'])} countries", status="ok")
    GHA.endgroup()

    GHA.phase("③", "POOL", "Updating rolling pool of historically-working nodes")
    alive_uris: set = set()
    for sub_file in ["sub_all.txt", "sub_bs.txt", "sub_chs.txt"]:
        if os.path.exists(sub_file):
            with open(sub_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        alive_uris.add(line)
    update_pool(alive_uris)
    GHA.endgroup()

    GHA.phase("④", "BUILD", "Compiling dashboard (index.html)")
    build_html(stats["unique_alive"], stats["top_speed"], stats)
    GHA.endgroup()

    GHA.phase("⑤", "NOTIFY", "Sending Telegram report")
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
