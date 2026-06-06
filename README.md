<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=e11d48&height=240&section=header&text=Scarlet%20Devil%20Network&fontSize=58&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Self-verifying%20proxy%20aggregator%20%C2%B7%20Reality%20%2F%20Hysteria2%20%C2%B7%20DPI%20bypass&descAlignY=60&descAlign=50" />
</div>

<div align="center">

![Python](https://img.shields.io/badge/python-3.11+-38bdf8.svg?style=for-the-badge&logo=python&logoColor=white)
![Go](https://img.shields.io/badge/ANGRA--CORE-Go-00ADD8.svg?style=for-the-badge&logo=go&logoColor=white)
![sing-box](https://img.shields.io/badge/Kernel-sing--box_1.12.23-e11d48.svg?style=for-the-badge)
![GitHub Actions](https://img.shields.io/badge/Engine-Matrix_Concurrency-8b5cf6.svg?style=for-the-badge&logo=githubactions&logoColor=white)
![Vercel](https://img.shields.io/badge/Deploy-Vercel-000000.svg?style=for-the-badge&logo=vercel&logoColor=white)
![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-success.svg?style=for-the-badge)

**Автоматический агрегатор и верификатор публичных конфигураций для обхода DPI / ТСПУ**

<br />[🌐 Web Nexus (Доступ)](https://scarlet-devil.vercel.app/) • [💬 Telegram-форум](https://t.me/ScDevNetwork) • [🛡 Канал](https://t.me/ScarletDevilTeam)

</div>

> **⚠️ STRICT COPYLEFT (AGPL-3.0).** Любое использование кода в сетевых сервисах, форках или ботах обязывает открыть исходный код вашего проекта согласно AGPL-3.0. Монетизация закрытых модификаций запрещена.

---

## 🩸 О проекте

**Scarlet Devil Network** — независимый движок, который непрерывно ищет, проверяет и публикует **рабочие** конфигурации для обхода сетевых барьеров. Это **не VPN-провайдер и не магазин подписок**: своих серверов мы не держим и ваш трафик не видим — мы лишь отбираем из открытых источников то, что реально работает прямо сейчас.

Классические VPN (OpenVPN, WireGuard, L2TP) сегодня вычисляются DPI по сигнатуре за секунды. Ставка проекта — на маскировку, прежде всего **VLESS Reality**, чей трафик неотличим от обычного захода на крупный сайт.

В отличие от обычных «парсеров ссылок», мы **не доверяем источникам на слово**: каждый узел проходит реальное L4/L7-подключение через ядро `sing-box` и сквозной замер скорости. В финальную выдачу попадают только выжившие — обычно считанные проценты от исходной массы, отсортированные по фактической пропускной способности. Список пересобирается автоматически **каждые 4 часа**.

---

## 🗃️ Подписки (Spellcards)

Проверенный трафик делится по **классу обхода** и по **протоколу**. Все эндпоинты отдаются с `Content-Type: text/plain`, `no-store`, `Access-Control-Allow-Origin: *` и совместимы с любым современным клиентом.

### По классу обхода

| Spellcard | Эндпоинт | Описание |
|-----------|----------|----------|
| 🟣 **Nightbird** · БС | `/sub/bs` | Только `VLESS Reality`. Прорыв жёстких мобильных фильтров и белых списков (ТСПУ). Приоритет — маскировка. |
| 🟢 **Vampire Dash** · ЧС | `/sub/chs` | Максимальная скорость для свободного интернета (YouTube 4K, стриминг, голос). |
| 🔴 **Gungnir** · MIX | `/sub` · `/sub/all` | Полный архив выживших узлов. Для клиентов с авто-тестом задержки и балансировкой. |

### По протоколу

| Протокол | Эндпоинт | Профиль |
|----------|----------|---------|
| **VLESS** | `/sub/vless` | Reality / Vision — лучшая маскировка |
| **VMess** | `/sub/vmess` | Классический транспорт, широкая совместимость |
| **Trojan** | `/sub/trojan` | TLS-маскировка под обычный HTTPS |
| **Shadowsocks** | `/sub/ss` | Лёгкий и быстрый, минимум overhead |
| **Hysteria2** | `/sub/hy2` | QUIC/UDP — максимум скорости на нестабильных каналах |

> Опционально доступна экспериментальная подписка **Remilia** (`/sub/ru`) — узлы, проверенные *изнутри РФ* внешним воркером (см. [RU-verified](#-ru-verified-опционально)). Без подключённого воркера она пустая.

---

## 🌐 Web Nexus — дашборд

Витрина проекта ([scarlet-devil.vercel.app](https://scarlet-devil.vercel.app/)) — интерактивный портал в эстетике **«Refined Gensokyo»** (утончённый Touhou / Scarlet): шрифт Unbounded, многослойная атмосфера (mesh + зерно + даммаку-кольца + дрейфующие лепестки сакуры), кандзи-водяные знаки, золото-алый-пурпур.

- **🧙 Мастер настройки** — пошаговый гид «платформа → клиент → импорт», подбирающий подписку и приложение под устройство.
- **📱 База клиентов** для Windows, Android, iOS, macOS, Linux, Android TV и роутеров (MikroTik / OpenWRT) — с гайдами и блоками «решение проблем».
- **🔳 Встроенный генератор QR** — самописный, без зависимостей (GF(256) + Reed-Solomon), для импорта на телефон.
- **📊 Живая статистика** — распределение узлов по протоколам, классам и странам + сводка скоростей, рендерится из реальных данных сборки. По мере накопления `history.json` появляются **тренды (▲/▼) и спарклайны**.
- **📖 FAQ, сравнение протоколов и глоссарий** — что выбрать и почему.
- **🎨 Эффекты и темы** — алый туман и звёздная пыль, цветовые темы; состояние хранится в `localStorage`. PWA-манифест для установки как приложения. Полная поддержка `prefers-reduced-motion`.

---

## ⚙️ Архитектура «Matrix Engine»

Сбор построен как распределённый конвейер на GitHub Actions: **матрица из 4 дронов** (`SHARD_COUNT=4`) параллельно обрабатывает свою долю узлов, после чего задача `Nexus Merge` сводит результаты, строит дашборд и публикует подписки. Запуск — по расписанию каждые 4 часа (`cron: 0 */4 * * *`) или вручную.

```
            ┌──────────────────── GitHub Actions (cron 0 */4 · dispatch) ────────────────────┐
            │                                                                                 │
 🦇 Drone   │   ① BASES      загрузка белых списков РКН/ТСПУ (домены + CIDR)                  │
 Matrix ×4  │   ② PARSE      сбор и декодирование подписок-источников (LinkParser)            │
(crawler)   │   ③ ENGINE     L4 TCP · L7 sing-box · спидтест  ──►  go_core / ANGRA-CORE       │
            │   ④ AGGREGATE  дедуп (strict_id), метрики, GeoIP (ip-api batch)                 │
            │   ⑤ EXPORT     шардовые sub_*.txt + stats → артефакты                           │
            └───────────────────────────────────┬─────────────────────────────────────────────┘
                                                ▼
 🩸 Nexus    merge.py: VMess-aware дедуп между шардами · сортировка по скорости ·
   Merge     сборка index.html (CSS+JS inline) · rolling pool + history.json ·
(merge)      Telegram-отчёт · git push → main
                                                ▼
                  📤  подписки + dashboard  ──►  Vercel  ──►  пользователь
```

### 🔩 Конвейер проверки (что значит «живой узел»)

Python готовит для каждого узла валидный `sing-box` outbound и передаёт пачку в Go-движок через JSON-handoff. **ANGRA-CORE** прогоняет каждый узел сквозь три барьера:

1. **L4 — связь.** TCP-рукопожатие с повтором и тайм-аутами. Отсекаются мёртвые адреса, приватные/подменные IP и диапазоны CDN на уровне CIDR-фильтра.
2. **L7 — туннель.** Узел поднимается в локальном `sing-box`, и через SOCKS-инбаунд выполняется реальный HTTP-запрос к `generate_204`-эндпоинтам. Подтверждает, что сервер действительно проксирует трафик.
3. **Скорость.** Быстрый замер на каждом выжившем узле и контрольная «чемпионская» загрузка **10 МБ** (Cloudflare) для лучших — для точной сортировки по реальной скорости.

Поддерживаемые транспорты и фичи: `ws`, `grpc`, `httpupgrade`/`xhttp`, `http/h2`, `quic`; `TLS`, **`Reality`** (с валидацией public key), uTLS-fingerprint, ALPN, SNI, obfs (Hysteria2). Закреплённое ядро — **sing-box v1.12.23**.

---

## 🗂️ Структура проекта

```
ScarletDevil/
├── main.py                  # Точка входа дрона: пайплайн одного шарда
├── merge.py                 # Nexus Merge: сведение шардов, дедуп, index.html, pool/history, отчёт
│
├── core/                    # Python-ядро (асинхронное)
│   ├── parser.py            #   LinkParser — сбор и декодирование подписок-источников
│   ├── engine.py            #   Inspector + BatchEngine — трансляция в sing-box, мост к ANGRA-CORE, GeoIP
│   ├── validator.py         #   RKNValidator — белые списки РКН/ТСПУ (домены + CIDR)
│   ├── exporter.py          #   Exporter — генерация sub_*.txt по классам и протоколам
│   ├── models.py            #   ProxyNode и модели данных (Pydantic)
│   ├── settings.py          #   config/settings.yaml → singleton CONFIG
│   ├── logger.py            #   GHA — оформленный вывод для GitHub Actions
│   └── util.py
│
├── go_core/                 # ANGRA-CORE — движок проверок на Go
│   ├── main.go              #   L4/L7-валидатор + спидтест поверх sing-box
│   ├── go.mod / go.sum
│
├── config/
│   ├── settings.yaml        # Источники, белые списки, пороги скорости/задержки
│   └── web/                 # Исходники дашборда (инлайнятся в index.html)
│       ├── template.html    #   Разметка: hero, мастер, модалки, статистика, FAQ, глоссарий
│       ├── style.css        #   Дизайн «Refined Gensokyo», темы, атмосфера, анимации
│       ├── main.js          #   UI, QR-генератор, мастер, база клиентов, графики
│       └── manifest.json    #   PWA-манифест
│
├── tests/                   # pytest — парсер протоколов, история/тренды
├── .github/workflows/       # update.yml (Matrix Core) · ci.yml · cleanup.yml
├── data/                    # pool.json · history.json · source_health.json (состояние CI)
│
├── index.html               # Сгенерированный дашборд (артефакт сборки)
├── sub_*.txt                # Сгенерированные подписки (артефакты сборки)
├── vercel.json              # Rewrites (/sub/* → sub_*.txt) и заголовки
├── .nojekyll                # Отключает Jekyll-сборку GitHub Pages
└── requirements.txt
```

> **Артефакты** (`index.html`, `sub_*.txt`, `data/*.json`) генерируются автоматически в `Nexus Merge` и коммитятся в `main` — править их вручную не нужно (на каждом прогоне CI они перезаписываются).

---

## 🛠️ Технологический стек

| Слой | Технологии |
|------|------------|
| **Оркестрация** | GitHub Actions (matrix sharding, cron), git-based deploy |
| **Сбор / логика** | Python 3.11 · asyncio · aiohttp · Pydantic · loguru |
| **Движок проверок** | Go (ANGRA-CORE) · sing-box 1.12.23 |
| **GeoIP** | ip-api.com (batch) |
| **Frontend** | Vanilla JS · CSS · inline-SVG · PWA (без фреймворков и сборщиков) |
| **Хостинг** | Vercel (production branch = `main`) |

---

## 🔌 Быстрый старт (для пользователя)

1. Откройте [Web Nexus](https://scarlet-devil.vercel.app/) и нажмите **«Быстрая настройка»** — мастер подберёт клиент и подписку под ваше устройство.
2. Либо скопируйте подписку напрямую и вставьте в любой совместимый клиент:
   - **MIX (всё сразу):** `https://scarlet-devil.vercel.app/sub`
   - **Nightbird · БС (жёсткие фильтры):** `https://scarlet-devil.vercel.app/sub/bs`
   - **Vampire Dash · ЧС (скорость):** `https://scarlet-devil.vercel.app/sub/chs`
3. Включите **автообновление** подписки в клиенте (интервал 4–6 ч) и выбирайте узел по **URL/Latency-тесту**.
4. Рекомендуемые клиенты: **v2rayNG / Hiddify / NekoBox** (Android), **Streisand / Shadowrocket** (iOS), **Nekoray / Hiddify** (Desktop).

---

## 🧪 Локальная разработка

```bash
# Python-зависимости
pip install -r requirements.txt -r requirements-dev.txt

# Go-движок ANGRA-CORE (собирается автоматически при первом прогоне engine,
# либо вручную):
cd go_core && go build -ldflags "-s -w" -o angra_core main.go && cd ..

# Тесты
python -m pytest -q          # core-парсер + история/тренды
cd go_core && go vet ./...   # статанализ Go-движка

# Один прогон шарда (нужен бинарь sing-box в PATH и переменные окружения):
#   SUBSCRIPTION_SOURCES, SHARD_INDEX, SHARD_COUNT
python main.py               # → data/sub_*.txt, data/stats_*.json

# Сборка дашборда + сведение (читает артефакты шардов):
python merge.py              # → index.html, sub_*.txt, data/{pool,history}.json
```

> `index.html` **генерируется** из `config/web/{template.html, style.css, main.js}` функцией `merge.py::build_html` — редактируйте исходники в `config/web/`, а не сам `index.html`.

---

## 🚀 Деплой

- **CI** (`.github/workflows/update.yml`) запускается каждые 4 часа: 4 дрона собирают и проверяют узлы → `Nexus Merge` строит `index.html`, подписки и обновляет `data/history.json` → коммитит результат в ветку **`main`**.
- **Vercel** раздаёт сайт из ветки `main` (Settings → Git → Production Branch = `main`). Маршрутизация и заголовки заданы в `vercel.json` (строгая схема — без комментариев и неизвестных ключей, иначе Vercel отклоняет деплой).
- **`.nojekyll`** в корне отключает параллельную Jekyll-сборку GitHub Pages (иначе она падает на `{{…}}`-токенах шаблона).

---

## 🇷🇺 RU-verified (опционально)

Раннеры GitHub находятся **вне РФ**, поэтому «живость» узла не гарантирует доступность за ТСПУ. Для узлов, *реально проверенных изнутри России*, предусмотрена подписка **`/sub/ru`**, наполняемая вердиктом внешнего RU-воркера (в этот репозиторий не входит).

**Контракт (env-gated):** узел помечается `ru_verified`, если его `strict_id` есть в JSON-файле вердикта, путь к которому задан в `RU_VERDICT_FILE`. Формат — список id или `{"verified": [...]}` / `{"ids": [...]}`. Если переменная не задана — `sub_ru.txt` просто пустой, остальной пайплайн не меняется. Воркер скачивает `/sub`, пересчитывает `strict_id` тем же `LinkParser`, повторяет L7-проверку изнутри РФ и публикует список выживших.

---

## ⚖️ Дисклеймер

Репозиторий является автоматизированным парсером метаданных и предоставляется «как есть» (AS IS), без гарантий, исключительно в образовательных и исследовательских целях. Автор не владеет представленными в выдаче серверами и не несёт ответственности за их использование конечным пользователем и за любой возможный ущерб. Использование для действий, нарушающих законодательство вашей юрисдикции, запрещено.

<div align="center">
  <br />
  <sub>🦇 Scarlet Devil Network — Refined Gensokyo Routing Architecture · AGPL-3.0</sub>
</div>
