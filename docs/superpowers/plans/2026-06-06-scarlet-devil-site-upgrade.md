# Scarlet Devil Site Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a git-stored history pipeline and a cohesive, lore-tinted "Live Command Center" visual upgrade (hero + stats showcase + subscription polish) to the Scarlet Devil dashboard, with zero new build steps or external libraries.

**Architecture:** `merge.py` gains a rolling `history.json` (mirrors the existing `pool.json` pattern) and feeds trend deltas + a sparkline series into `build_html` as new template tokens. The frontend (`template.html` + `style.css` + `main.js`) gains one shared motion system (single easing/timing/stagger + one reduced-motion guard) and one reveal choreography that drives count-up, an inline-SVG sparkline, trend chips, animated bars, and quiet Touhou spell-card captions.

**Tech Stack:** Python 3.11 + pytest (backend/history), vanilla HTML/CSS/JS (inline SVG, Canvas already present), GitHub Actions. No new dependencies.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `merge.py` | History load/save/update + trend computation + token injection in `build_html` | Modify |
| `tests/test_history.py` | Unit tests for history rotation, recovery, trend math | Create |
| `.github/workflows/update.yml` | Publish `data/history.json` | Modify |
| `config/web/style.css` | Motion tokens, reduced-motion guard, trend chips, sparkline, captions, bar animation | Modify |
| `config/web/main.js` | Motion helpers, reveal conductor, count-up, sparkline, sys-log rotator, copy feedback | Modify |
| `config/web/template.html` | Hero hooks (trend chips, sparkline svg), stats `data-*`, lore captions | Modify |
| `index.html` | Regenerated artifact | Regenerate (never hand-edit) |

**Preserve:** the existing `healPlaceholders()` (main.js), the server-side placeholder safety-net (`build_html`), and `body.fx-extreme`. Do not weaken them.

---

## Task 1: History store — load / save / update (TDD)

**Files:**
- Modify: `merge.py` (add after `update_pool`, ~line 333)
- Test: `tests/test_history.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history.py`:

```python
"""Tests for the rolling network-history store in merge.py."""
import json
import merge


def test_update_history_appends_one_snapshot(tmp_path):
    path = str(tmp_path / "history.json")
    stats = {
        "unique_alive": 100, "top_speed": 500.0, "avg_speed": 40.0,
        "median_speed": 35.0, "speed_percentile_90": 90.0,
        "vless_count": 50, "vmess_count": 10, "trojan_count": 8,
        "ss_count": 5, "hy2_count": 2, "bs_count": 30, "chs_count": 70,
        "country_stats": [{"code": "DE", "count": 9}],
    }
    merge.update_history(stats, path=path)
    data = json.load(open(path, encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["total"] == 100
    assert data[0]["max_speed"] == 500
    assert data[0]["countries"] == 1
    assert "t" in data[0]


def test_update_history_rotates_to_90(tmp_path):
    path = str(tmp_path / "history.json")
    seed = [{"t": str(i), "total": i} for i in range(95)]
    json.dump(seed, open(path, "w", encoding="utf-8"))
    merge.update_history({"unique_alive": 999}, path=path)
    data = json.load(open(path, encoding="utf-8"))
    assert len(data) == 90
    assert data[-1]["total"] == 999          # newest kept
    assert data[0]["total"] == 6             # oldest 6 dropped (95+1-90)


def test_load_history_recovers_from_garbage(tmp_path):
    path = str(tmp_path / "history.json")
    open(path, "w", encoding="utf-8").write("{ not json")
    assert merge.load_history(path) == []


def test_load_history_missing_file(tmp_path):
    assert merge.load_history(str(tmp_path / "nope.json")) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_history.py -v`
Expected: FAIL — `AttributeError: module 'merge' has no attribute 'update_history'`.

- [ ] **Step 3: Implement the history store**

In `merge.py`, immediately after `update_pool` (after line 333) add:

```python
HISTORY_PATH = "data/history.json"
HISTORY_MAX = 90


def load_history(path: str = HISTORY_PATH) -> list:
    """Load the rolling network-stats history (chronological, oldest first)."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            hist = json.load(f)
        return hist if isinstance(hist, list) else []
    except Exception:
        return []


def save_history(hist: list, path: str = HISTORY_PATH) -> None:
    """Persist the rolling history to disk."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)


def _snapshot(stats: dict) -> dict:
    """Reduce the aggregate stats dict to one compact, serialisable point."""
    return {
        "t":         datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total":     int(stats.get("unique_alive", 0)),
        "max_speed": int(stats.get("top_speed", 0.0)),
        "avg":       round(stats.get("avg_speed", 0.0), 1),
        "median":    round(stats.get("median_speed", 0.0), 1),
        "p90":       round(stats.get("speed_percentile_90", 0.0), 1),
        "vless":     int(stats.get("vless_count", 0)),
        "vmess":     int(stats.get("vmess_count", 0)),
        "trojan":    int(stats.get("trojan_count", 0)),
        "ss":        int(stats.get("ss_count", 0)),
        "hy2":       int(stats.get("hy2_count", 0)),
        "bs":        int(stats.get("bs_count", 0)),
        "chs":       int(stats.get("chs_count", 0)),
        "countries": len(stats.get("country_stats", [])),
    }


def update_history(stats: dict, path: str = HISTORY_PATH) -> list:
    """Append one snapshot of this run and rotate to the last HISTORY_MAX."""
    hist = load_history(path)
    hist.append(_snapshot(stats))
    if len(hist) > HISTORY_MAX:
        hist = hist[-HISTORY_MAX:]
    save_history(hist, path)
    logger.info(f"  History: {len(hist)} snapshots (cap {HISTORY_MAX})")
    return hist
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_history.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add merge.py tests/test_history.py
git commit -m "feat(web): rolling network-history store (merge.py) with rotation+recovery"
```

---

## Task 2: Trend computation helper (TDD)

**Files:**
- Modify: `merge.py` (add after `update_history`)
- Test: `tests/test_history.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_history.py`:

```python
def test_compute_trends_insufficient_history():
    t = merge.compute_trends([{"total": 100, "max_speed": 500}])
    assert t["nodes_pct"] is None
    assert t["speed_pct"] is None
    assert t["series_total"] == [100]


def test_compute_trends_percent_delta():
    hist = [
        {"total": 100, "max_speed": 400},
        {"total": 110, "max_speed": 500},
    ]
    t = merge.compute_trends(hist)
    assert round(t["nodes_pct"], 1) == 10.0
    assert round(t["speed_pct"], 1) == 25.0
    assert t["series_total"] == [100, 110]
    assert t["series_speed"] == [400, 500]


def test_compute_trends_zero_previous_is_safe():
    hist = [{"total": 0, "max_speed": 0}, {"total": 5, "max_speed": 9}]
    t = merge.compute_trends(hist)
    assert t["nodes_pct"] is None       # no divide-by-zero
    assert t["speed_pct"] is None


def test_compute_trends_series_capped_to_30():
    hist = [{"total": i, "max_speed": i} for i in range(50)]
    t = merge.compute_trends(hist)
    assert len(t["series_total"]) == 30
    assert t["series_total"][0] == 20   # last 30 of 0..49
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_history.py -k compute_trends -v`
Expected: FAIL — `module 'merge' has no attribute 'compute_trends'`.

- [ ] **Step 3: Implement `compute_trends`**

In `merge.py`, after `update_history`, add:

```python
TREND_SERIES_LEN = 30


def _pct(prev: float, cur: float):
    """Signed percent change prev→cur, or None when prev is non-positive."""
    if prev is None or prev <= 0:
        return None
    return (cur - prev) / prev * 100.0


def compute_trends(history: list) -> dict:
    """Derive sparkline series + signed percent deltas from history.

    Returns nodes_pct/speed_pct (None when <2 points or prev<=0) and the
    last TREND_SERIES_LEN totals/speeds for the hero sparkline.
    """
    totals = [int(h.get("total", 0)) for h in history]
    speeds = [int(h.get("max_speed", 0)) for h in history]
    nodes_pct = speed_pct = None
    if len(history) >= 2:
        nodes_pct = _pct(totals[-2], totals[-1])
        speed_pct = _pct(speeds[-2], speeds[-1])
    return {
        "nodes_pct":    nodes_pct,
        "speed_pct":    speed_pct,
        "series_total": totals[-TREND_SERIES_LEN:],
        "series_speed": speeds[-TREND_SERIES_LEN:],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_history.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add merge.py tests/test_history.py
git commit -m "feat(web): compute_trends — sparkline series + signed deltas"
```

---

## Task 3: Wire history + trends into `build_html` and `main()`

**Files:**
- Modify: `merge.py` — `main()` (line 535) and `build_html` (lines 132–211)

- [ ] **Step 1: Call `update_history` before `build_html` in `main()`**

In `merge.py::main`, replace line 535:

```python
    build_html(stats["unique_alive"], stats["top_speed"], stats)
```

with:

```python
    history = update_history(stats)
    build_html(stats["unique_alive"], stats["top_speed"], stats, history)
```

- [ ] **Step 2: Accept `history` and inject the new tokens in `build_html`**

In `merge.py`, change the signature (line 132):

```python
def build_html(total_alive: int, top_speed: float, stats: dict,
               history: list | None = None) -> None:
```

Then, inside the `try:` block, right after `node_stats_json = json.dumps(node_stats, ensure_ascii=False)` (line 174), add:

```python
        trends = compute_trends(history or [])

        def _trend_str(pct):
            return f"{pct:+.1f}" if pct is not None else ""

        trend_nodes = _trend_str(trends["nodes_pct"])
        trend_speed = _trend_str(trends["speed_pct"])
        history_json = json.dumps(
            [{"total": t, "max_speed": s}
             for t, s in zip(trends["series_total"], trends["series_speed"])],
            ensure_ascii=False,
        )
```

Then, in the `.replace(...)` chain, add these three lines just before `.replace("{{COUNTRY_STATS_JSON}}", country_stats_json)`:

```python
               .replace("{{TREND_NODES}}", trend_nodes)
               .replace("{{TREND_SPEED}}", trend_speed)
               .replace("{{HISTORY_JSON}}", history_json)
```

- [ ] **Step 3: Verify merge.py still imports and the suite passes**

Run: `python -c "import merge" && python -m pytest tests/test_history.py -v`
Expected: import OK; 8 passed.

- [ ] **Step 4: Commit**

```bash
git add merge.py
git commit -m "feat(web): feed history trends + sparkline series into build_html tokens"
```

---

## Task 4: Publish `history.json` in CI

**Files:**
- Modify: `.github/workflows/update.yml` (line 151–153, `PUBLISH_FILES`)

- [ ] **Step 1: Add history.json to PUBLISH_FILES**

In `.github/workflows/update.yml`, change the `PUBLISH_FILES` block to include `data/history.json`:

```yaml
          PUBLISH_FILES="index.html sub_all.txt sub_bs.txt sub_chs.txt sub_ru.txt \
                  sub_vless.txt sub_vmess.txt sub_trojan.txt sub_ss.txt sub_hy2.txt \
                  data/source_health.json data/pool.json data/history.json"
```

- [ ] **Step 2: Verify YAML is valid**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/update.yml')); print('yaml ok')"`
Expected: `yaml ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update.yml
git commit -m "ci: publish data/history.json so trends persist across runs"
```

---

## Task 5: Motion system — CSS tokens + reduced-motion guard

**Files:**
- Modify: `config/web/style.css` (`:root` block, top of file)

- [ ] **Step 1: Add motion tokens to `:root`**

In `config/web/style.css`, inside the existing `:root { ... }`, after the `--trans-fast:` line, add:

```css
    /* --- Unified motion system ("Алый ритм") --- */
    --ease-scarlet: cubic-bezier(0.2, 0.8, 0.2, 1);
    --motion-fast: 0.2s;
    --motion-base: 0.4s;
    --motion-slow: 0.8s;
    --stagger-step: 60ms;
```

- [ ] **Step 2: Add a global reduced-motion guard at the END of style.css**

Append to `config/web/style.css`:

```css
/* One global switch: visitors who ask for less motion get final states only. */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.001ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.001ms !important;
        scroll-behavior: auto !important;
    }
    .hero-sparkline, .scan-sweep { display: none !important; }
}
```

- [ ] **Step 3: Verify CSS is well-formed (balanced braces)**

Run: `python -c "s=open('config/web/style.css',encoding='utf-8').read(); assert s.count('{')==s.count('}'), (s.count('{'),s.count('}')); print('braces ok')"`
Expected: `braces ok`.

- [ ] **Step 4: Commit**

```bash
git add config/web/style.css
git commit -m "feat(web): unified motion tokens + global reduced-motion guard"
```

---

## Task 6: Motion helpers + reveal conductor (JS foundation)

**Files:**
- Modify: `config/web/main.js` — add helpers above `function init()`; call conductor from `init()`

- [ ] **Step 1: Add motion helpers above `init()`**

In `config/web/main.js`, immediately above `// --- ROBUSTNESS:` / `function healPlaceholders()` (the block added earlier), insert:

```javascript
// --- UNIFIED MOTION HELPERS ("Алый ритм") ---
var PREFERS_REDUCED = (function () {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
    catch (e) { return false; }
})();

// Eased count-up from 0 to `target`. Instant under reduced-motion.
function animateCount(el, target, opts) {
    opts = opts || {};
    var decimals = opts.decimals || 0;
    var dur = opts.duration || 800;
    var fmt = function (v) { return v.toFixed(decimals); };
    if (PREFERS_REDUCED || !target || target <= 0) {
        el.textContent = fmt(target || 0);
        return;
    }
    var start = null;
    function frame(ts) {
        if (start === null) start = ts;
        var p = Math.min((ts - start) / dur, 1);
        var eased = 1 - Math.pow(1 - p, 3);   // easeOutCubic — matches --ease-scarlet
        el.textContent = fmt(target * eased);
        if (p < 1) requestAnimationFrame(frame);
        else el.textContent = fmt(target);
    }
    requestAnimationFrame(frame);
}

// Draw a sparkline into an inline <svg> from a numeric series.
function drawSparkline(svg, series) {
    if (!svg || !series || series.length < 2) {
        if (svg) svg.style.display = 'none';
        return;
    }
    var w = 100, h = 28, pad = 2;
    var min = Math.min.apply(null, series), max = Math.max.apply(null, series);
    var span = (max - min) || 1;
    var step = (w - pad * 2) / (series.length - 1);
    var pts = series.map(function (v, i) {
        var x = pad + i * step;
        var y = h - pad - ((v - min) / span) * (h - pad * 2);
        return x.toFixed(1) + ',' + y.toFixed(1);
    });
    var d = 'M' + pts.join(' L');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.innerHTML =
        '<defs><linearGradient id="spark-grad" x1="0" y1="0" x2="1" y2="0">' +
        '<stop offset="0%" stop-color="var(--touhou-crimson)"/>' +
        '<stop offset="100%" stop-color="var(--touhou-red-glow)"/></linearGradient></defs>' +
        '<polyline points="' + pts.join(' ') + '" fill="none" ' +
        'stroke="url(#spark-grad)" stroke-width="1.5" ' +
        'stroke-linecap="round" stroke-linejoin="round"/>';
    var line = svg.querySelector('polyline');
    if (line && !PREFERS_REDUCED) {
        var len = line.getTotalLength ? line.getTotalLength() : 200;
        line.style.strokeDasharray = len;
        line.style.strokeDashoffset = len;
        line.style.transition = 'stroke-dashoffset var(--motion-slow) var(--ease-scarlet)';
        requestAnimationFrame(function () { line.style.strokeDashoffset = '0'; });
    }
}

// Read the embedded node-stats blob once (null if absent/unsubstituted).
function readNodeStats() {
    var el = document.getElementById('stats-data');
    if (!el) return null;
    var raw = el.getAttribute('data-node-stats');
    if (!raw || raw.indexOf('{{') !== -1) return null;
    try { return JSON.parse(raw); } catch (e) { return null; }
}
```

- [ ] **Step 2: Syntax-check**

Run: `node --check config/web/main.js`
Expected: no output (valid).

- [ ] **Step 3: Commit**

```bash
git add config/web/main.js
git commit -m "feat(web): shared motion helpers (count-up, sparkline, reduced-motion)"
```

---

## Task 7: Hero "Live Command Center" — markup + behavior + style

**Files:**
- Modify: `config/web/template.html` (hero dashboard, lines 156–171)
- Modify: `config/web/main.js` (new `initHero()`, call from `init()`)
- Modify: `config/web/style.css` (trend chips, sparkline, scan-sweep)

- [ ] **Step 1: Add hero hooks to the template**

In `config/web/template.html`, replace the `<div class="dashboard"> ... </div>` block (lines 156–171) with:

```html
                <div class="dashboard">
                    <div class="scan-sweep" aria-hidden="true"></div>
                    <div class="stat-panel">
                        <div class="stat-title"><i class="fa-solid fa-gauge-high"></i> Max Speed</div>
                        <div class="stat-value text-touhou">
                            <span id="hero-max-speed">{{MAX_SPEED}}</span><span>Mbps</span>
                            <span class="trend-chip" id="trend-speed" data-trend="{{TREND_SPEED}}"></span>
                        </div>
                    </div>
                    <div class="stat-panel">
                        <div class="stat-title"><i class="fa-solid fa-server"></i> Active Nodes</div>
                        <div class="stat-value">
                            <span id="hero-total-nodes">{{PROXY_COUNT}}</span><span>UP</span>
                            <span class="trend-chip" id="trend-nodes" data-trend="{{TREND_NODES}}"></span>
                        </div>
                    </div>

                    <svg class="hero-sparkline" id="hero-sparkline" data-history='{{HISTORY_JSON}}'
                         preserveAspectRatio="none" aria-hidden="true"></svg>

                    <div class="sys-log">
                        <div class="line">> last_sync: <span class="sys-log-time" data-utc="{{UPDATE_TIME_ISO}}">{{UPDATE_TIME}} MSK</span></div>
                        <div class="line">> telemetry: <span class="magic" id="sys-telemetry">…</span></div>
                        <div class="line">> obfuscation: <span class="magic">REALITY_ACTIVE</span></div>
                    </div>
                </div>
```

- [ ] **Step 2: Add `initHero()` to main.js and call it from `init()`**

In `config/web/main.js`, add this function (e.g. directly after `readNodeStats`):

```javascript
// --- HERO: live command center ---
function initHero() {
    var node = readNodeStats();

    var hs = document.getElementById('hero-max-speed');
    var hn = document.getElementById('hero-total-nodes');
    if (hs && node && typeof node.max_speed === 'number') animateCount(hs, node.max_speed);
    if (hn && node && typeof node.total === 'number') animateCount(hn, node.total);

    // Trend chips: show ▲/▼ +N% from the data-trend attr; hide when empty.
    document.querySelectorAll('.trend-chip').forEach(function (chip) {
        var v = chip.getAttribute('data-trend');
        var n = parseFloat(v);
        if (!v || v.indexOf('{{') !== -1 || isNaN(n) || n === 0) { chip.style.display = 'none'; return; }
        var up = n > 0;
        chip.classList.add(up ? 'trend-up' : 'trend-down');
        chip.textContent = (up ? '▲ ' : '▼ ') + (up ? '+' : '') + n.toFixed(1) + '%';
    });

    // Sparkline from embedded history.
    var svg = document.getElementById('hero-sparkline');
    if (svg) {
        var raw = svg.getAttribute('data-history'), series = null;
        if (raw && raw.indexOf('{{') === -1) {
            try {
                var arr = JSON.parse(raw);
                series = arr.map(function (p) { return p.total; });
            } catch (e) { series = null; }
        }
        drawSparkline(svg, series);
    }

    // Quiet, truthful telemetry rotator in the sys-log.
    var tEl = document.getElementById('sys-telemetry');
    if (tEl && node) {
        var lines = [];
        if (typeof node.median_speed === 'number') lines.push('median ' + node.median_speed + ' Mbps');
        if (typeof node.total === 'number') lines.push('verified ' + node.total + ' nodes');
        if (node.countries && node.countries.length) lines.push('top: ' + (node.countries[0].code || '??'));
        if (typeof node.bs === 'number') lines.push('reality ' + node.bs + ' nodes');
        if (!lines.length) { tEl.textContent = 'online'; }
        else {
            var i = 0;
            tEl.textContent = lines[0];
            if (!PREFERS_REDUCED && lines.length > 1) {
                setInterval(function () {
                    i = (i + 1) % lines.length;
                    tEl.style.opacity = '0';
                    setTimeout(function () { tEl.textContent = lines[i]; tEl.style.opacity = '1'; }, 250);
                }, 4000);
            }
        }
    }
}
```

Then add `initHero();` inside `init()` — insert it right after `healPlaceholders();`:

```javascript
function init() {
    healPlaceholders();
    initHero();
    const ua = navigator.userAgent.toLowerCase();
```

- [ ] **Step 3: Add hero styles**

Append to `config/web/style.css`:

```css
/* --- Hero: trend chips, sparkline, scan-sweep --- */
.trend-chip {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    font-weight: 700;
    margin-left: 8px;
    padding: 2px 6px;
    border-radius: 6px;
    vertical-align: middle;
    letter-spacing: 0.02em;
}
.trend-chip.trend-up   { color: var(--cyber-green-glow); background: rgba(16, 185, 129, 0.12); }
.trend-chip.trend-down { color: var(--touhou-red-glow);  background: rgba(225, 29, 72, 0.12); }

.hero-sparkline {
    display: block;
    width: 100%;
    height: 28px;
    margin: 6px 0 2px;
    opacity: 0.9;
}

.dashboard { position: relative; overflow: hidden; }
.scan-sweep {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(120deg, transparent 0%,
        rgba(225, 29, 72, 0.07) 48%, rgba(255, 45, 85, 0.12) 50%,
        rgba(225, 29, 72, 0.07) 52%, transparent 100%);
    background-size: 220% 100%;
    background-position: 200% 0;
    animation: scan-sweep-move 7s var(--ease-scarlet) infinite;
}
@keyframes scan-sweep-move {
    0%   { background-position: 200% 0; }
    60%  { background-position: -60% 0; }
    100% { background-position: -60% 0; }
}
#sys-telemetry { transition: opacity var(--motion-fast) var(--ease-scarlet); }
```

- [ ] **Step 4: Verify JS + CSS**

Run: `node --check config/web/main.js && python -c "s=open('config/web/style.css',encoding='utf-8').read(); assert s.count('{')==s.count('}'); print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add config/web/template.html config/web/main.js config/web/style.css
git commit -m "feat(web): hero live command center — count-up, sparkline, trend chips, telemetry"
```

---

## Task 8: Stats showcase — animated bars, count-up, delta chips

**Files:**
- Modify: `config/web/main.js` — `initStats()` (lines ~1796–1900)
- Modify: `config/web/template.html` — add delta chips to speed summary (lines 433–457)
- Modify: `config/web/style.css` — staggered bar transition

- [ ] **Step 1: Animate bar values + add stagger in `initStats`**

In `config/web/main.js`, in `initStats`, replace the `setBar` function (lines 1829–1834) with:

```javascript
    var barIndex = 0;
    function setBar(id, val) {
        var bar = document.getElementById(id);
        var valEl = document.getElementById('val-' + id.split('-')[1]);
        var delay = (barIndex++) * 60;          // --stagger-step
        if (bar) {
            bar.style.transition = 'width var(--motion-base) var(--ease-scarlet) ' + delay + 'ms';
            requestAnimationFrame(function () { bar.style.width = (val / maxCount * 100) + '%'; });
        }
        if (valEl) animateCount(valEl, val);
    }
```

- [ ] **Step 2: Animate the speed-summary values**

In `config/web/main.js`, in `initStats`, find where summary values are assigned (the `sumMax`, `sumAvg`, etc. block after line 1894). Replace the direct `.textContent = ...` assignments for the numeric summaries with `animateCount`, e.g.:

```javascript
    if (sumMax)   animateCount(sumMax,   parseFloat(maxSpeed)    || 0, { decimals: 0 });
    if (sumAvg)   animateCount(sumAvg,   parseFloat(avgSpeed)    || 0, { decimals: 1 });
    if (sumMed)   animateCount(sumMed,   parseFloat(medianSpeed) || 0, { decimals: 1 });
    if (sumP90)   animateCount(sumP90,   parseFloat(speedP90)    || 0, { decimals: 1 });
    if (sumTotal) animateCount(sumTotal, parseInt(totalNodes)    || 0, { decimals: 0 });
```

(Leave `sumBS` and any non-numeric assignments as they are.)

- [ ] **Step 3: Syntax-check**

Run: `node --check config/web/main.js`
Expected: valid.

- [ ] **Step 4: Commit**

```bash
git add config/web/main.js config/web/template.html config/web/style.css
git commit -m "feat(web): stats showcase — staggered bar growth + count-up summaries"
```

---

## Task 9: Lore captions + subscription/onboarding polish

**Files:**
- Modify: `config/web/template.html` — faint spell-card captions on section headers
- Modify: `config/web/style.css` — `.lore-caption` style
- Modify: `config/web/main.js` — unify copy feedback (verify existing helper)

- [ ] **Step 1: Add a `.lore-caption` style**

Append to `config/web/style.css`:

```css
/* Quiet Touhou spell-card captions — present if you look, ignorable if not. */
.lore-caption {
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--touhou-sakura);
    opacity: 0.33;
    margin-top: 4px;
    font-weight: 400;
    user-select: none;
}
```

- [ ] **Step 2: Add captions under two or three section headers**

In `config/web/template.html`, add a caption span under the hero `<h1>` (after line 134) and the stats `<h2>` (after line 328). Examples:

Hero (after `<h1>Scarlet Devil <span>Network</span></h1>`):

```html
                <span class="lore-caption">紅魔郷 ~ Embodiment of Scarlet Network</span>
```

Stats (after the stats `<h2>...</h2>` on line 328):

```html
                <span class="lore-caption">幻想結界 ~ Phantasm Telemetry</span>
```

- [ ] **Step 3: Confirm copy feedback is consistent**

Run: `grep -n "Скопировано\|copyToClipboard\|navigator.clipboard\|copy-btn" config/web/main.js | head`
Expected: identify the existing copy handler. If a single handler sets the "Скопировано ✓" state, no change needed. If multiple copy paths exist with inconsistent feedback, route them through the existing handler (do not introduce a second pattern). Record findings in the commit message.

- [ ] **Step 4: Verify**

Run: `node --check config/web/main.js && python -c "s=open('config/web/style.css',encoding='utf-8').read(); assert s.count('{')==s.count('}'); print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add config/web/template.html config/web/style.css config/web/main.js
git commit -m "feat(web): quiet spell-card lore captions + consistent copy feedback"
```

---

## Task 10: Regenerate index.html + full verification

**Files:**
- Regenerate: `index.html` (never hand-edit)

- [ ] **Step 1: Regenerate index.html from the current template**

Run:

```bash
python - <<'PY'
import re
tpl = open("config/web/template.html", encoding="utf-8").read()
css = open("config/web/style.css", encoding="utf-8").read()
js  = open("config/web/main.js", encoding="utf-8").read()
out = tpl.replace("{{INJECT_CSS}}", css).replace("{{INJECT_JS}}", js)
out = re.sub(r"\{\{[A-Z0-9_]+\}\}", "—", out)   # mirror build_html safety-net (no live data locally)
open("index.html", "w", encoding="utf-8").write(out)
print("regenerated; visible tokens:", re.findall(r"\{\{[A-Z0-9_]+\}\}", out))
PY
```

Expected: `visible tokens: []`.

- [ ] **Step 2: Full verification sweep**

Run:

```bash
node --check config/web/main.js \
 && python -m pytest tests/test_history.py -q \
 && python -c "import merge; print('merge import ok')" \
 && python -c "s=open('index.html',encoding='utf-8').read(); import re; vis=[m for m in re.findall(r'\{\{[A-Z0-9_]+\}\}', s)]; print('visible placeholder tokens:', vis)"
```

Expected: pytest passes; merge imports; `visible placeholder tokens: []`.

- [ ] **Step 3: Manual check (local)**

Open `index.html` in a browser. Confirm:
- hero numbers count up; sparkline/trend chips hidden gracefully (no live data → "—"/hidden);
- no raw `{{...}}` anywhere on screen;
- toggling OS "reduce motion" removes count-up/sweep, values still correct;
- mobile width: dashboard, sparkline, captions, stats bars all lay out cleanly.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "build(web): regenerate index.html with motion system + live command center"
```

---

## Self-Review Notes

- **Spec coverage:** Component 1 → Tasks 1–4; Motion system → Tasks 5–6; Lore → Task 9; Component 2 (hero) → Task 7; Component 3 (stats) → Task 8; Component 4 (polish) → Task 9; regeneration/verify → Task 10. All spec sections mapped.
- **Token consistency:** new tokens `{{TREND_NODES}}`, `{{TREND_SPEED}}`, `{{HISTORY_JSON}}` are introduced in Task 3 (build_html) and consumed in Task 7 (template `data-trend` / `data-history`). Helper names (`animateCount`, `drawSparkline`, `readNodeStats`, `compute_trends`, `update_history`, `load_history`) are defined once and reused verbatim.
- **Preserved invariants:** `healPlaceholders()`, server safety-net sweep, and `body.fx-extreme` are untouched and explicitly relied upon.
- **Degradation:** every consumer guards on `indexOf('{{')` / numeric checks / `PREFERS_REDUCED`, so missing data or reduced-motion never breaks the page.
