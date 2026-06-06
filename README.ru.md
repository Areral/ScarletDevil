<div align="center">

<img src="assets/banner.svg" alt="Scarlet Devil Network" width="100%">

<br>

[![Python](https://img.shields.io/badge/Python-3.11+-38bdf8?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Go](https://img.shields.io/badge/ANGRA--CORE-Go-00ADD8?style=for-the-badge&logo=go&logoColor=white)](https://go.dev/)
[![sing-box](https://img.shields.io/badge/Kernel-sing--box_1.12.23-e11d48?style=for-the-badge)](https://github.com/SagerNet/sing-box)
[![GitHub Actions](https://img.shields.io/badge/Engine-Matrix_Concurrency-8b5cf6?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/features/actions)
[![Vercel](https://img.shields.io/badge/Deploy-Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-c9a86a?style=for-the-badge)](LICENSE)

**Самопроверяющийся агрегатор публичных прокси-конфигураций для обхода DPI / ТСПУ.**

[🌐 Живой сайт](https://scarlet-devil.vercel.app/) · [💬 Telegram](https://t.me/ScDevNetwork) · [🛡 Канал](https://t.me/ScarletDevilTeam)

[English](./README.md) · **Русский**

</div>

> [!WARNING]
> **Строгий копилефт — AGPL-3.0.** Использование кода в любом сетевом сервисе, форке или боте обязывает открыть исходный код вашего проекта по AGPL-3.0. Монетизация закрытых модификаций запрещена.

> [!NOTE]
> Scarlet Devil Network — **не VPN-провайдер** и **не держит собственных серверов**. Проект собирает публичные конфигурации, проверяет их и публикует те, что реально работают. Ваш трафик идёт напрямую от клиента к выбранному узлу — не через нас.

---

## Оглавление

- [О проекте](#о-проекте)
- [Подписки](#подписки)
- [Дашборд](#дашборд)
- [Архитектура](#архитектура)
- [Структура проекта](#структура-проекта)
- [Технологический стек](#технологический-стек)
- [Быстрый старт](#быстрый-старт)
- [Локальная разработка](#локальная-разработка)
- [Деплой](#деплой)
- [FAQ](#faq)
- [Дисклеймер](#дисклеймер)
- [Лицензия](#лицензия)

---

## О проекте

Классические VPN (OpenVPN, WireGuard, L2TP) сегодня вычисляются DPI по сигнатуре за секунды. Scarlet Devil делает ставку на **маскировку трафика** — прежде всего **VLESS Reality**, чей трафик неотличим от обычного захода на крупный сайт.

В отличие от обычных «парсеров ссылок», мы **не доверяем источникам на слово**: каждый узел проходит реальное L4/L7-подключение через ядро `sing-box` и сквозной замер скорости. В выдачу попадают только выжившие — обычно считанные проценты от исходной массы, отсортированные по **фактической пропускной способности**. Коллекция пересобирается автоматически **каждые 4 часа**.

**Кратко**

- ⚡ **Многоступенчатая проверка** — L4 TCP → L7-туннель (`sing-box`) → спидтест, с «чемпионским» замером на 10 МБ для сортировки.
- 🛡 **Современная обфускация** — VLESS Reality, VMess, Trojan, Shadowsocks, Hysteria2.
- 🧩 **Шардированный движок** — матрица из 4 дронов в GitHub Actions + Go-ядро (`ANGRA-CORE`) поверх `sing-box`.
- 📊 **Живой дашборд** — статистика по протоколам/классам/странам, сводка скоростей, тренды и спарклайны.
- 🔒 **Без логов и трекинга** — статический сайт плюс текстовые файлы подписок; трафик не касается нашей инфраструктуры.

---

## Подписки

Проверенный трафик делится по **классу обхода** и по **протоколу**. Каждый эндпоинт отдаётся как `text/plain` с `no-store` и `Access-Control-Allow-Origin: *` и работает с любым современным клиентом.

### По классу обхода

| Spellcard | Эндпоинт | Описание |
|-----------|----------|----------|
| 🟣 **Nightbird** · БС | `/sub/bs` | Только `VLESS Reality`. Прорыв жёстких мобильных фильтров и белых списков (ТСПУ). Приоритет — маскировка. |
| 🟢 **Vampire Dash** · ЧС | `/sub/chs` | Максимальная скорость для свободного интернета (4K-стриминг, голос, загрузки). |
| 🔴 **Gungnir** · MIX | `/sub` · `/sub/all` | Полный архив выживших узлов. Для клиентов с авто-тестом задержки и балансировкой. |

### По протоколу

| Протокол | Эндпоинт | Профиль |
|----------|----------|---------|
| **VLESS** | `/sub/vless` | Reality / Vision — лучшая маскировка |
| **VMess** | `/sub/vmess` | Классический транспорт, широкая совместимость |
| **Trojan** | `/sub/trojan` | TLS — выглядит как обычный HTTPS |
| **Shadowsocks** | `/sub/ss` | Лёгкий и быстрый, минимум overhead |
| **Hysteria2** | `/sub/hy2` | QUIC/UDP — максимум скорости на нестабильных каналах |

> [!TIP]
> Включите **автообновление** подписки в клиенте (каждые 4–6 ч) и выбирайте узел по **URL/Latency-тесту** — публичные узлы недолговечны по природе.

---

## Дашборд

Витрина проекта — [scarlet-devil.vercel.app](https://scarlet-devil.vercel.app/) — интерактивный портал в эстетике **«Refined Gensokyo»** (шрифт Unbounded, многослойная атмосфера mesh + зерно + даммаку-кольца + лепестки сакуры, кандзи-водяные знаки, алый-золото-пурпур).

- 🧙 **Мастер настройки** — пошаговый гид «платформа → клиент → импорт», подбирающий подписку и приложение.
- 📱 **База клиентов** для Windows, Android, iOS, macOS, Linux, Android TV и роутеров (MikroTik / OpenWRT), с гайдами и «решением проблем».
- 🔳 **Встроенный генератор QR** — самописный, без зависимостей (GF(256) + Reed-Solomon).
- 📊 **Живая статистика** — распределение по протоколам/классам/странам и сводка скоростей из реальных данных сборки; **тренды (▲/▼) и спарклайны** появляются по мере накопления `history.json`.
- 📖 **FAQ, сравнение протоколов и глоссарий.**
- 🎨 **Эффекты и темы** — алый туман и звёздная пыль, цветовые темы, сохранение в `localStorage`, PWA-манифест и полная поддержка `prefers-reduced-motion`.

> [!NOTE]
> `index.html` **генерируется** из `config/web/{template.html, style.css, main.js}` функцией `merge.py::build_html`. Правьте исходники в `config/web/`, а не сам файл.

---

## Архитектура

Сбор построен как распределённый конвейер на GitHub Actions: **матрица из 4 дронов** (`SHARD_COUNT=4`) параллельно обрабатывает свою долю узлов, после чего задача `Nexus Merge` сводит результаты, строит дашборд и публикует подписки. Запуск — по расписанию каждые 4 часа (`cron: 0 */4 * * *`) или вручную.

```
            ┌──────────────── GitHub Actions (cron 0 */4 · dispatch) ────────────────┐
            │                                                                         │
 🦇 Drone   │  ① BASES      загрузка белых списков РКН/ТСПУ (домены + CIDR)          │
 Matrix ×4  │  ② PARSE      сбор и декодирование подписок-источников (LinkParser)    │
(crawler)   │  ③ ENGINE     L4 TCP · L7 sing-box · спидтест → go_core/ANGRA-CORE     │
            │  ④ AGGREGATE  дедуп (strict_id), метрики, GeoIP (ip-api batch)         │
            │  ⑤ EXPORT     шардовые sub_*.txt + stats → артефакты                   │
            └───────────────────────────────┬─────────────────────────────────────────┘
                                            ▼
 🩸 Nexus    merge.py: VMess-aware дедуп между шардами · сортировка по скорости ·
   Merge     сборка index.html (CSS+JS inline) · rolling pool + history.json ·
(merge)      Telegram-отчёт · git push → main
                                            ▼
                  📤  подписки + дашборд  ──►  Vercel  ──►  пользователь
```

### Конвейер проверки — что значит «живой узел»

Python готовит для каждого узла валидный `sing-box` outbound и передаёт пачку в Go-движок через JSON. **ANGRA-CORE** прогоняет каждый узел сквозь три барьера:

1. **L4 — связь.** TCP-рукопожатие с повтором и тайм-аутами. Мёртвые адреса, приватные/подменные IP и диапазоны CDN отсекаются на CIDR-фильтре.
2. **L7 — туннель.** Узел поднимается в локальном `sing-box`; через SOCKS-инбаунд выполняется реальный HTTP-запрос к `generate_204`. Подтверждает, что сервер действительно проксирует трафик.
3. **Скорость.** Быстрый замер на каждом выжившем + «чемпионская» загрузка 10 МБ (Cloudflare) для лучших — для сортировки по реальной скорости.

Поддерживаемые транспорты и фичи: `ws`, `grpc`, `httpupgrade`/`xhttp`, `http/h2`, `quic`; `TLS`, **`Reality`** (с валидацией public key), uTLS-fingerprint, ALPN, SNI, obfs (Hysteria2). Закреплённое ядро — **sing-box v1.12.23**.

---

## Структура проекта

```
ScarletDevil/
├── main.py              # Точка входа дрона: пайплайн одного шарда
├── merge.py             # Nexus Merge: дедуп шардов, index.html, pool/history, отчёт
│
├── core/                # Асинхронное Python-ядро
│   ├── parser.py        #   LinkParser — сбор и декодирование подписок-источников
│   ├── engine.py        #   Inspector + BatchEngine — трансляция в sing-box, мост к ANGRA-CORE, GeoIP
│   ├── validator.py     #   RKNValidator — белые списки РКН/ТСПУ (домены + CIDR)
│   ├── exporter.py      #   Exporter — sub_*.txt по классам и протоколам
│   ├── models.py        #   ProxyNode + модели данных (Pydantic)
│   ├── settings.py      #   config/settings.yaml → singleton CONFIG
│   ├── logger.py        #   GHA — оформленный вывод для GitHub Actions
│   └── util.py
│
├── go_core/             # ANGRA-CORE — движок проверок на Go
│   └── main.go          #   L4/L7-валидатор + спидтест поверх sing-box
│
├── config/
│   ├── settings.yaml    # Источники, белые списки, пороги скорости/задержки
│   └── web/             # Исходники дашборда (инлайнятся в index.html)
│       ├── template.html · style.css · main.js · manifest.json
│
├── tests/               # pytest — парсер протоколов, история/тренды
├── .github/workflows/   # update.yml (Matrix Core) · ci.yml · cleanup.yml
├── data/                # pool.json · history.json · source_health.json (состояние CI)
├── assets/              # баннер для README
│
├── index.html           # Сгенерированный дашборд (артефакт сборки)
├── sub_*.txt            # Сгенерированные подписки (артефакты сборки)
├── vercel.json          # Rewrites (/sub/* → sub_*.txt) и заголовки
├── .nojekyll            # Отключает Jekyll-сборку GitHub Pages
└── requirements.txt
```

---

## Технологический стек

| Слой | Технологии |
|------|------------|
| **Оркестрация** | GitHub Actions (matrix sharding, cron), git-based deploy |
| **Сбор / логика** | Python 3.11 · asyncio · aiohttp · Pydantic · loguru |
| **Движок проверок** | Go (ANGRA-CORE) · sing-box 1.12.23 |
| **GeoIP** | ip-api.com (batch) |
| **Frontend** | Vanilla JS · CSS · inline SVG · PWA (без фреймворков и сборщиков) |
| **Хостинг** | Vercel (production branch `main`) |

---

## Быстрый старт

1. Откройте [сайт](https://scarlet-devil.vercel.app/) и нажмите **«Быстрая настройка»** — мастер подберёт клиент и подписку под ваше устройство.
2. Либо скопируйте подписку напрямую в любой совместимый клиент:
   - **MIX (всё сразу):** `https://scarlet-devil.vercel.app/sub`
   - **Nightbird · БС (жёсткие фильтры):** `https://scarlet-devil.vercel.app/sub/bs`
   - **Vampire Dash · ЧС (скорость):** `https://scarlet-devil.vercel.app/sub/chs`
3. Включите **автообновление** (4–6 ч) и выбирайте узлы по **URL/Latency-тесту**.
4. Рекомендуемые клиенты: **v2rayNG / Hiddify / NekoBox** (Android), **Streisand / Shadowrocket** (iOS), **Nekoray / Hiddify** (Desktop).

---

## Локальная разработка

<details>
<summary><b>Команды установки, сборки и тестов</b></summary>

```bash
# Python-зависимости
pip install -r requirements.txt -r requirements-dev.txt

# Сборка Go-движка (ANGRA-CORE); также собирается автоматически при первом прогоне
cd go_core && go build -ldflags "-s -w" -o angra_core main.go && cd ..

# Тесты
python -m pytest -q          # core-парсер + история/тренды
cd go_core && go vet ./...   # статанализ Go

# Один прогон шарда (нужен бинарь sing-box в PATH + переменные окружения
# SUBSCRIPTION_SOURCES, SHARD_INDEX, SHARD_COUNT)
python main.py               # → data/sub_*.txt, data/stats_*.json

# Сборка дашборда + сведение шардов
python merge.py              # → index.html, sub_*.txt, data/{pool,history}.json
```

> Дашборд собирается из `config/web/` функцией `merge.py::build_html`. Редактируйте исходники там — не сам `index.html`.

</details>

---

## Деплой

<details>
<summary><b>Как сайт попадает в прод</b></summary>

- **CI** (`.github/workflows/update.yml`) запускается каждые 4 часа: 4 дрона собирают и проверяют узлы → `Nexus Merge` строит `index.html`, подписки и обновляет `data/history.json` → коммитит результат в ветку **`main`**.
- **Vercel** раздаёт сайт из `main` (Settings → Git → Production Branch = `main`). Маршрутизация и заголовки — в `vercel.json` (строгая схема: без комментариев и неизвестных ключей, иначе Vercel отклоняет деплой).
- **`.nojekyll`** в корне отключает параллельную Jekyll-сборку GitHub Pages (которая иначе падает на `{{…}}`-токенах шаблона).

</details>

---

## FAQ

<details>
<summary><b>Это бесплатно? В чём подвох?</b></summary>

Да, полностью бесплатно — без аккаунтов и оплаты. Честный нюанс: это **публичные, недоверенные серверы**. Они нестабильны, их владельцы неизвестны — относитесь к ним как к удобному, но не доверенному транспорту (используйте HTTPS, для чувствительного — Reality/Nightbird).
</details>

<details>
<summary><b>Вы храните логи или видите мой трафик?</b></summary>

Нет. Сайт — статическая страница плюс текстовые файлы: ни аккаунтов, ни серверной аналитики трафика, ни логов подключений. Ваш трафик идёт **напрямую** от клиента к узлу, мимо нас; технически мы его не видим.
</details>

<details>
<summary><b>Чем отличаются БС и ЧС?</b></summary>

**БС / Nightbird** — для белых списков (закрыто всё, кроме разрешённого): только Reality, максимум маскировки. **ЧС / Vampire Dash** — для обычных сетей (закрыты лишь отдельные ресурсы): приоритет скорости. **MIX / Gungnir** — оба класса сразу.
</details>

<details>
<summary><b>Как часто обновляются узлы?</b></summary>

Полный цикл сбора и проверки — каждые 4 часа. Публичные узлы живут от нескольких часов до пары дней, поэтому включайте автообновление подписки в клиенте, чтобы мёртвые адреса заменялись сами.
</details>

---

## Дисклеймер

Репозиторий — автоматизированный парсер метаданных, предоставляется «как есть» (**AS IS**) без гарантий, **исключительно в образовательных и исследовательских целях**. Автор не владеет представленными в выдаче серверами и не несёт ответственности за их использование конечным пользователем и за любой возможный ущерб. Использование для действий, нарушающих законодательство вашей юрисдикции, запрещено.

---

## Лицензия

Распространяется под **GNU AGPL-3.0**. Полный текст — в файле [`LICENSE`](LICENSE).

<div align="center">
  <br>
  <sub>🦇 Scarlet Devil Network — Refined Gensokyo Routing Architecture · AGPL-3.0 · 紅魔郷</sub>
</div>
