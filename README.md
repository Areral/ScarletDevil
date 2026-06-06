<div align="center">

<img src="assets/banner.svg" alt="Scarlet Devil Network" width="100%">

<br>

[![Python](https://img.shields.io/badge/Python-3.11+-38bdf8?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Go](https://img.shields.io/badge/ANGRA--CORE-Go-00ADD8?style=for-the-badge&logo=go&logoColor=white)](https://go.dev/)
[![sing-box](https://img.shields.io/badge/Kernel-sing--box_1.12.23-e11d48?style=for-the-badge)](https://github.com/SagerNet/sing-box)
[![GitHub Actions](https://img.shields.io/badge/Engine-Matrix_Concurrency-8b5cf6?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/features/actions)
[![Vercel](https://img.shields.io/badge/Deploy-Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-c9a86a?style=for-the-badge)](LICENSE)

**A self-verifying aggregator of public proxy configs for bypassing DPI / SORM (ТСПУ).**

[🌐 Live Demo](https://scarlet-devil.vercel.app/) · [💬 Telegram](https://t.me/ScDevNetwork) · [🛡 Channel](https://t.me/ScarletDevilTeam)

**English** · [Русский](./README.ru.md)

</div>

> [!WARNING]
> **Strict copyleft — AGPL-3.0.** Using this code in any network service, fork, or bot obligates you to release your project's source under AGPL-3.0. Monetizing closed-source modifications is prohibited.

> [!NOTE]
> Scarlet Devil Network is **not a VPN provider** and runs **no servers** of its own. It collects publicly available configs, verifies them, and publishes the ones that actually work. Your traffic goes straight from your client to the chosen node — never through us.

---

## Table of Contents

- [Overview](#overview)
- [Subscriptions](#subscriptions)
- [Dashboard](#dashboard)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Local development](#local-development)
- [Deployment](#deployment)
- [FAQ](#faq)
- [Disclaimer](#disclaimer)
- [License](#license)

---

## Overview

Classic VPNs (OpenVPN, WireGuard, L2TP) are now fingerprinted by DPI in seconds. Scarlet Devil bets on **traffic masquerade** — first and foremost **VLESS Reality**, whose traffic is indistinguishable from an ordinary visit to a major website.

Unlike plain "link scrapers," we **never trust sources at their word**. Every node is put through a real L4/L7 connection via the `sing-box` kernel and an end-to-end speed test. Only survivors reach the output — usually a few percent of the raw pool — sorted by **actual throughput**. The collection is rebuilt automatically **every 4 hours**.

**Highlights**

- ⚡ **Multi-stage verification** — L4 TCP → L7 tunnel (`sing-box`) → speed test, with a 10 MB "champion" measurement for ranking.
- 🛡 **Modern obfuscation** — VLESS Reality, VMess, Trojan, Shadowsocks, Hysteria2.
- 🧩 **Sharded engine** — a 4-drone GitHub Actions matrix + Go core (`ANGRA-CORE`) over `sing-box`.
- 📊 **Live dashboard** — protocol/class/country stats, speed summary, trends & sparklines.
- 🔒 **No logs, no tracking** — a static site plus text subscription files; traffic never touches our infrastructure.

---

## Subscriptions

Verified traffic is split by **bypass class** and by **protocol**. Every endpoint is served as `text/plain` with `no-store` and `Access-Control-Allow-Origin: *`, and works with any modern client.

### By bypass class

| Spellcard | Endpoint | Description |
|-----------|----------|-------------|
| 🟣 **Nightbird** · WL | `/sub/bs` | `VLESS Reality` only. Breaks through hard mobile filters and white-list regimes (ТСПУ). Priority: stealth. |
| 🟢 **Vampire Dash** · BL | `/sub/chs` | Maximum speed for the open internet (4K streaming, voice, downloads). |
| 🔴 **Gungnir** · MIX | `/sub` · `/sub/all` | The full archive of survivors. For clients with latency auto-test and load balancing. |

### By protocol

| Protocol | Endpoint | Profile |
|----------|----------|---------|
| **VLESS** | `/sub/vless` | Reality / Vision — best masquerade |
| **VMess** | `/sub/vmess` | Classic transport, broad compatibility |
| **Trojan** | `/sub/trojan` | TLS, looks like ordinary HTTPS |
| **Shadowsocks** | `/sub/ss` | Lightweight and fast, minimal overhead |
| **Hysteria2** | `/sub/hy2` | QUIC/UDP — top speed on lossy links |

> [!TIP]
> Enable **auto-update** for the subscription in your client (every 4–6 h) and pick a node by the **URL/Latency test** — public nodes are short-lived by nature.

---

## Dashboard

The project's storefront — [scarlet-devil.vercel.app](https://scarlet-devil.vercel.app/) — is an interactive portal in a **"Refined Gensokyo"** aesthetic (Unbounded type, layered atmosphere of mesh + grain + danmaku rings + drifting sakura petals, kanji watermarks, scarlet-gold-purple).

- 🧙 **Setup wizard** — a step-by-step "platform → client → import" guide that picks a subscription and app for the device.
- 📱 **Client library** for Windows, Android, iOS, macOS, Linux, Android TV and routers (MikroTik / OpenWRT), with guides and troubleshooting.
- 🔳 **Built-in QR generator** — hand-rolled, zero dependencies (GF(256) + Reed-Solomon).
- 📊 **Live statistics** — protocol/class/country distribution and a speed summary, rendered from real build data; **trends (▲/▼) and sparklines** appear as `history.json` accumulates.
- 📖 **FAQ, protocol comparison and a glossary.**
- 🎨 **Effects & themes** — scarlet mist and stardust, color themes, `localStorage` persistence, a PWA manifest, and full `prefers-reduced-motion` support.

> [!NOTE]
> `index.html` is **generated** from `config/web/{template.html, style.css, main.js}` by `merge.py::build_html`. Edit the sources in `config/web/`, never the generated file.

---

## Architecture

Collection is a distributed pipeline on GitHub Actions: a **4-drone matrix** (`SHARD_COUNT=4`) processes its slice of nodes in parallel, then a `Nexus Merge` job consolidates results, builds the dashboard and publishes subscriptions. Runs on a 4-hour schedule (`cron: 0 */4 * * *`) or on demand.

```
            ┌──────────────── GitHub Actions (cron 0 */4 · dispatch) ────────────────┐
            │                                                                         │
 🦇 Drone   │  ① BASES      load RKN/ТСПУ white-lists (domains + CIDR)               │
 Matrix ×4  │  ② PARSE      fetch & decode source subscriptions (LinkParser)         │
(crawler)   │  ③ ENGINE     L4 TCP · L7 sing-box · speed test → go_core/ANGRA-CORE   │
            │  ④ AGGREGATE  dedup (strict_id), metrics, GeoIP (ip-api batch)         │
            │  ⑤ EXPORT     shard sub_*.txt + stats → artifacts                      │
            └───────────────────────────────┬─────────────────────────────────────────┘
                                            ▼
 🩸 Nexus    merge.py: VMess-aware cross-shard dedup · sort by speed ·
   Merge     build index.html (CSS+JS inline) · rolling pool + history.json ·
(merge)      Telegram report · git push → main
                                            ▼
                  📤  subscriptions + dashboard  ──►  Vercel  ──►  user
```

### The verification gauntlet — what "a live node" means

Python builds a valid `sing-box` outbound for each node and hands a batch to the Go engine via JSON. **ANGRA-CORE** runs every node through three barriers:

1. **L4 — reachability.** TCP handshake with retry and timeouts. Dead addresses, private/spoofed IPs and CDN ranges are dropped at the CIDR filter.
2. **L7 — tunnel.** The node is spun up in a local `sing-box`; a real HTTP request to `generate_204` endpoints runs through its SOCKS inbound, proving the server actually proxies traffic.
3. **Speed.** A quick measurement on each survivor plus a 10 MB "champion" download (Cloudflare) for the best nodes, to rank by real throughput.

Supported transports & features: `ws`, `grpc`, `httpupgrade`/`xhttp`, `http/h2`, `quic`; `TLS`, **`Reality`** (public-key validated), uTLS fingerprint, ALPN, SNI, obfs (Hysteria2). Pinned kernel: **sing-box v1.12.23**.

---

## Project structure

```
ScarletDevil/
├── main.py              # Drone entrypoint: one shard's pipeline
├── merge.py             # Nexus Merge: cross-shard dedup, index.html, pool/history, report
│
├── core/                # Async Python core
│   ├── parser.py        #   LinkParser — fetch & decode source subscriptions
│   ├── engine.py        #   Inspector + BatchEngine — sing-box translation, ANGRA-CORE bridge, GeoIP
│   ├── validator.py     #   RKNValidator — RKN/ТСПУ white-lists (domains + CIDR)
│   ├── exporter.py      #   Exporter — sub_*.txt by class and protocol
│   ├── models.py        #   ProxyNode + data models (Pydantic)
│   ├── settings.py      #   config/settings.yaml → CONFIG singleton
│   ├── logger.py        #   GHA — styled GitHub Actions output
│   └── util.py
│
├── go_core/             # ANGRA-CORE — Go verification engine
│   └── main.go          #   L4/L7 validator + speed test over sing-box
│
├── config/
│   ├── settings.yaml    # Sources, white-lists, speed/latency thresholds
│   └── web/             # Dashboard sources (inlined into index.html)
│       ├── template.html · style.css · main.js · manifest.json
│
├── tests/               # pytest — protocol parser, history/trends
├── .github/workflows/   # update.yml (Matrix Core) · ci.yml · cleanup.yml
├── data/                # pool.json · history.json · source_health.json (CI state)
├── assets/              # README banner
│
├── index.html           # Generated dashboard (build artifact)
├── sub_*.txt            # Generated subscriptions (build artifacts)
├── vercel.json          # Rewrites (/sub/* → sub_*.txt) and headers
├── .nojekyll            # Disables GitHub Pages' Jekyll build
└── requirements.txt
```

---

## Tech stack

| Layer | Technologies |
|-------|--------------|
| **Orchestration** | GitHub Actions (matrix sharding, cron), git-based deploy |
| **Collection / logic** | Python 3.11 · asyncio · aiohttp · Pydantic · loguru |
| **Verification engine** | Go (ANGRA-CORE) · sing-box 1.12.23 |
| **GeoIP** | ip-api.com (batch) |
| **Frontend** | Vanilla JS · CSS · inline SVG · PWA (no frameworks, no bundler) |
| **Hosting** | Vercel (production branch `main`) |

---

## Quick start

1. Open the [Live Demo](https://scarlet-devil.vercel.app/) and hit **"Quick setup"** — the wizard picks a client and subscription for your device.
2. Or copy a subscription directly into any compatible client:
   - **MIX (everything):** `https://scarlet-devil.vercel.app/sub`
   - **Nightbird · WL (hard filters):** `https://scarlet-devil.vercel.app/sub/bs`
   - **Vampire Dash · BL (speed):** `https://scarlet-devil.vercel.app/sub/chs`
3. Turn on **auto-update** (4–6 h) and select nodes by the **URL/Latency test**.
4. Recommended clients: **v2rayNG / Hiddify / NekoBox** (Android), **Streisand / Shadowrocket** (iOS), **Nekoray / Hiddify** (Desktop).

---

## Local development

<details>
<summary><b>Setup, build & test commands</b></summary>

```bash
# Python dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Build the Go engine (ANGRA-CORE); also auto-built on the first engine run
cd go_core && go build -ldflags "-s -w" -o angra_core main.go && cd ..

# Tests
python -m pytest -q          # core parser + history/trends
cd go_core && go vet ./...   # Go static analysis

# One shard run (needs a sing-box binary in PATH + env vars
# SUBSCRIPTION_SOURCES, SHARD_INDEX, SHARD_COUNT)
python main.py               # → data/sub_*.txt, data/stats_*.json

# Build the dashboard + merge shards
python merge.py              # → index.html, sub_*.txt, data/{pool,history}.json
```

> The dashboard is built from `config/web/` by `merge.py::build_html`. Edit the sources there — never `index.html` directly.

</details>

---

## Deployment

<details>
<summary><b>How the site ships</b></summary>

- **CI** (`.github/workflows/update.yml`) runs every 4 hours: 4 drones collect & verify nodes → `Nexus Merge` builds `index.html`, the subscriptions and updates `data/history.json` → commits the result to **`main`**.
- **Vercel** serves the site from `main` (Settings → Git → Production Branch = `main`). Routing and headers live in `vercel.json` (strict schema — no comments or unknown top-level keys, or Vercel rejects the deploy).
- **`.nojekyll`** at the repo root disables GitHub Pages' parallel Jekyll build (which otherwise fails on the template's `{{…}}` tokens).

</details>

---

## FAQ

<details>
<summary><b>Is it free? What's the catch?</b></summary>

Yes, fully free — no accounts, no payment. The catch is honest: these are **public, untrusted servers**. They're unstable and their operators are unknown, so treat them as a convenient but not a trusted transport (use HTTPS, prefer Reality/Nightbird for anything sensitive).
</details>

<details>
<summary><b>Do you keep logs or see my traffic?</b></summary>

No. The site is a static page plus text files — no accounts, no traffic analytics, no connection logs. Your traffic flows **directly** from your client to the chosen node, not through us; technically we can't see it.
</details>

<details>
<summary><b>What's the difference between WL (БС) and BL (ЧС)?</b></summary>

**WL / Nightbird** targets white-list regimes (everything blocked unless allowed) — Reality only, maximum stealth. **BL / Vampire Dash** targets normal networks (only specific resources blocked) — prioritizes speed. **MIX / Gungnir** contains both.
</details>

<details>
<summary><b>How often do nodes update?</b></summary>

A full collect-and-verify cycle runs every 4 hours. Public nodes live from a few hours to a couple of days — enable subscription auto-update in your client so dead addresses are replaced automatically.
</details>

---

## Disclaimer

This repository is an automated metadata parser, provided **AS IS** without warranty, **for educational and research purposes only**. The author does not own the servers listed in the output and is not responsible for their use by the end user or for any resulting damage. Using it to violate the laws of your jurisdiction is prohibited.

---

## License

Distributed under the **GNU AGPL-3.0**. See [`LICENSE`](LICENSE) for the full text.

<div align="center">
  <br>
  <sub>🦇 Scarlet Devil Network — Refined Gensokyo Routing Architecture · AGPL-3.0 · 紅魔郷</sub>
</div>
