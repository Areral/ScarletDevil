<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=e11d48&height=250&section=header&text=Scarlet%20Devil%20Network&fontSize=60&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Advanced%20Neo-Gensokyo%20Routing%20Architecture&descAlignY=62&descAlign=50" />
</div>

<div align="center">

![Python](https://img.shields.io/badge/python-3.11+-38bdf8.svg?style=for-the-badge&logo=python&logoColor=white)
![Go](https://img.shields.io/badge/ANGRA--CORE-Go-00ADD8.svg?style=for-the-badge&logo=go&logoColor=white)
![sing-box](https://img.shields.io/badge/Kernel-sing--box_1.12-e11d48.svg?style=for-the-badge)
![GitHub Actions](https://img.shields.io/badge/Engine-Matrix_Concurrency-8b5cf6.svg?style=for-the-badge&logo=githubactions&logoColor=white)
![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-success.svg?style=for-the-badge)
![Copyleft](https://img.shields.io/badge/Copyleft-Strict-0f0508.svg?style=for-the-badge)

**Автоматизированный аналитический кластер для обхода систем глубокой фильтрации (DPI / ТСПУ)**

<br />[🌐 Web Nexus (Доступ)](https://scarlet-devil.vercel.app/) • [💬 Telegram Форум](https://t.me/ScDevNetwork) • [🛡 Канал](https://t.me/ScarletDevilTeam)

</div>

> **⚠️ ВНИМАНИЕ (STRICT COPYLEFT):** Данное программное обеспечение распространяется под лицензией **AGPL-3.0**.
> Любое использование кода в сетевых сервисах, форках или ботах обязывает вас предоставлять открытый доступ к исходному коду вашего проекта в соответствии с требованиями Free Software Foundation. Монетизация закрытых модификаций запрещена.

---

## 🩸 О проекте (Scarlet Devil Network)

**Scarlet Devil Network** — это независимая технологическая инициатива и система децентрализованной агрегации. Проект сканирует десятки тысяч публичных VPN-конфигураций, пропускает их через собственный **Matrix Engine** (асинхронный движок проверок) и выдаёт очищенные, высокоскоростные маршруты.

В условиях жёстких сетевых блэкаутов обычные протоколы (OpenVPN, WireGuard) бесполезны. Наше ядро фокусируется на современных методах обфускации:

- **VLESS + Reality** — мимикрия под легальный TLS-трафик (банки, маркетплейсы, зарубежные IT-гиганты).
- **VLESS, VMess, Trojan, Hysteria2 и Shadowsocks** — ультра-быстрые UDP/TCP туннели для стриминга и 4K-контента.

В отличие от обычных «парсеров ссылок», мы **не доверяем источникам на слово**: каждый узел проходит реальное L4/L7-подключение через ядро `sing-box` и сквозной замер скорости. В финальную выдачу попадают только живые узлы — отсортированные по фактической пропускной способности.

---

## 🗃️ Типология Маршрутов (Spellcards)

Весь собранный и проверенный трафик делится на магистрали по **классу обхода** и по **протоколу**.

### По классу обхода

| Spellcard | Эндпоинт | Описание |
|-----------|----------|----------|
| 🟣 **Nightbird** (Обход БС) | `/sub/bs` | Только `VLESS Reality`. Гарантированный прорыв жёстких мобильных фильтров и белых списков (ТСПУ). |
| 🟢 **Vampire Dash** (Обход ЧС) | `/sub/chs` | Максимальная скорость для свободного интернета (YouTube 4K, Discord, стриминг). |
| 🔴 **Gungnir** (MIX База) | `/sub` `/sub/all` | Полный архив выживших узлов. Для продвинутых пользователей с балансировщиками нагрузки. |
| 👑 **Remilia** (RU-verified) `NEW` | `/sub/ru` | Узлы, прошедшие верификацию доступности из РФ. Приоритет стабильности над количеством. |

### По протоколу `NEW`

Для тонкой настройки клиента под конкретный транспорт доступны отдельные подписки по каждому протоколу:

| Протокол | Эндпоинт | Профиль |
|----------|----------|---------|
| **VLESS** | `/sub/vless` | Reality / Vision — лучшая маскировка |
| **VMess** | `/sub/vmess` | Классический транспорт, широкая совместимость |
| **Trojan** | `/sub/trojan` | TLS-маскировка под HTTPS |
| **Shadowsocks** | `/sub/ss` | Лёгкий и быстрый, минимум overhead |
| **Hysteria2** | `/sub/hy2` | QUIC/UDP — максимум скорости на нестабильных каналах |

> Все подписки отдаются с заголовками `Content-Type: text/plain`, `no-store` и `Access-Control-Allow-Origin: *`, обновляются по расписанию и совместимы с любым современным клиентом (`#profile-update-interval: 6`).

---

## 🌐 Web Nexus — Дашборд `NEW`

Витрина проекта ([scarlet-devil.vercel.app](https://scarlet-devil.vercel.app/)) — это не просто список ссылок, а полноценный интерактивный портал в стилистике Touhou / Cyberpunk:

- **🧙 Интерактивный мастер настройки** — пошаговый гид (платформа → клиент → инструкция), который подбирает подписку и приложение под устройство пользователя.
- **📱 База из 22+ клиентов** для Windows, Android, iOS, macOS, Linux, Android TV и **роутеров** (MikroTik / OpenWRT) — с пошаговыми гайдами, советами и блоками «решение проблем».
- **🔳 Встроенный генератор QR-кодов** — самописный, без внешних зависимостей (GF(256) + Reed-Solomon), для мгновенного импорта на телефон.
- **📊 Живая статистика** — распределение узлов по протоколам, классам и странам, рендерится из реальных данных сборки.
- **❓ FAQ и сравнение протоколов** — что выбрать и почему.
- **🎨 Эффекты и темы** — CRT-scanlines, звёздная пыль, глитч-эффекты, переключаемая интенсивность и цветовые темы; всё сохраняется в `localStorage`. PWA-манифест для установки как приложения.

---

## ⚙️ Архитектура «Matrix Engine»

Сбор данных построен как распределённый конвейер на GitHub Actions: **матрица из 4 дронов** (`SHARD_COUNT=4`) параллельно обрабатывает свою долю узлов, после чего отдельная задача `Nexus Merge` сводит результаты, строит дашборд и публикует подписки. Запуск — по расписанию каждые 4 часа (`cron: 0 */4 * * *`) или вручную.

```
                       ┌─────────────────────── GitHub Actions (cron / dispatch) ───────────────────────┐
                       │                                                                                 │
   🦇 Drone Matrix  ×4 │   ① BASES      загрузка белых списков РКН/ТСПУ (домены + CIDR)                  │
   (matrix-crawler)    │   ② PARSE      сбор и декодирование подписок-источников (LinkParser)            │
                       │   ③ ENGINE     L4 TCP · L7 sing-box · замер скорости  ──►  go_core/ANGRA-CORE   │
                       │   ④ AGGREGATE  дедупликация (strict_id), метрики, GeoIP (ip-api batch)          │
                       │   ⑤ EXPORT     запись шардовых sub_*.txt в артефакты                            │
                       └───────────────────────────────────┬─────────────────────────────────────────────┘
                                                           ▼
   🩸 Nexus Merge       merge.py: VMess-aware дедуп между шардами · сортировка по скорости ·
   (matrix-merge)       сборка index.html (CSS+JS inline) · статистика · Telegram-отчёт · git push
                                                           ▼
                            📤  9 подписок + dashboard  ──►  Vercel  ──►  пользователь
```

### 🔩 ANGRA-CORE (Go)

Сердце проверок — самостоятельный высоконагруженный движок на **Go** (`go_core/main.go`). Python готовит для каждого узла валидный `sing-box` outbound и передаёт пачку в Go-бинарь через JSON-handoff. ANGRA-CORE поднимает локальные `sing-box` инстансы, проверяет реальную L4/L7-связность по нескольким `generate_204`-эндпоинтам и проводит сквозной спидтест (включая «чемпионский» замер на 10 МБ через Cloudflare). Узлы, ведущие в защищённые/служебные подсети, отсекаются на уровне CIDR-фильтра.

Поддерживаемые транспорты и фичи: `ws`, `grpc`, `httpupgrade`/`xhttp`, `http/h2`, `quic`; `TLS`, **`Reality`** (с валидацией public key), uTLS-fingerprint, ALPN, SNI, obfs (для Hysteria2).

---

## 🗂️ Структура проекта

```
ScarletDevil/
├── main.py                  # Точка входа дрона: оркестрация пайплайна одного шарда
├── merge.py                 # Nexus Merge: сведение шардов, дедуп, сборка index.html, отчёт
│
├── core/                    # Python-ядро (асинхронное)
│   ├── parser.py            #   LinkParser — сбор и декодирование подписок-источников
│   ├── engine.py            #   Inspector + BatchEngine — трансляция в sing-box, мост к ANGRA-CORE, GeoIP
│   ├── validator.py         #   RKNValidator — загрузка белых списков РКН/ТСПУ (домены + CIDR)
│   ├── exporter.py          #   Exporter — генерация sub_*.txt по классам и протоколам
│   ├── models.py            #   ProxyNode и модели данных (Pydantic)
│   ├── settings.py          #   Загрузка config/settings.yaml → singleton CONFIG
│   └── logger.py            #   GHA — оформленный вывод для GitHub Actions
│
├── go_core/                 # ANGRA-CORE — движок проверок на Go
│   ├── main.go              #   Высоконагруженный L4/L7-валидатор поверх sing-box
│   └── go.mod
│
├── config/
│   ├── settings.yaml        # Конфигурация: источники, белые списки, пороги скорости/задержки
│   └── web/                 # Исходники дашборда (собираются в index.html)
│       ├── template.html    #   Разметка: hero, мастер настройки, модалки, FAQ, статистика
│       ├── style.css        #   Стилистика Touhou / Cyberpunk, темы, эффекты
│       ├── main.js          #   Логика UI, QR-генератор, мастер, база клиентов
│       └── manifest.json    #   PWA-манифест
│
├── .github/workflows/
│   ├── update.yml           # ⏣ Matrix Core — матрица дронов + Nexus Merge + деплой
│   └── cleanup.yml          # Обслуживание/очистка
│
├── vercel.json              # Rewrites (/sub/* → sub_*.txt) и заголовки
├── requirements.txt
└── README.md
```

> **Артефакты сборки** (`index.html`, `sub_*.txt`) генерируются автоматически в `Nexus Merge` и публикуются force-push'ем в ту же ветку — отдельно их править вручную не нужно.

---

## 🛠️ Технологический стек

| Слой | Технологии |
|------|------------|
| **Оркестрация** | GitHub Actions (matrix sharding, cron), git-based deploy |
| **Сбор / логика** | Python 3.11 · asyncio · aiohttp · Pydantic · loguru |
| **Движок проверок** | Go (ANGRA-CORE) · sing-box 1.12 kernel |
| **GeoIP** | ip-api.com (batch) |
| **Frontend** | Vanilla JS · CSS · PWA (без фреймворков и сборщиков) |
| **Хостинг** | Vercel |

---

## 🔌 Быстрый старт (для пользователя)

1. Откройте [Web Nexus](https://scarlet-devil.vercel.app/) и нажмите **«Быстрая настройка»** — мастер подберёт клиент и подписку под ваше устройство.
2. Либо скопируйте нужную подписку напрямую и вставьте в любой совместимый клиент:
   - **Универсальная (MIX):** `https://scarlet-devil.vercel.app/sub`
   - **Обход БС (мобильные фильтры):** `https://scarlet-devil.vercel.app/sub/bs`
   - **Свободный интернет (скорость):** `https://scarlet-devil.vercel.app/sub/chs`
3. Рекомендуемые клиенты: **v2rayNG / NekoBox** (Android), **Streisand / V2Box** (iOS), **Nekoray / FlClash** (Desktop).

---

## 🚀 Деплой (Deployment)

- **GitHub Actions** запускает парсинг и проверку каждые 4 часа.
- Результат (подписки `sub_all.txt`, `sub_bs.txt`, `sub_chs.txt` и `index.html`) публикуется обычным коммитом в ветку **`gh-pages`** (без `--amend` и `--force`).
- **Vercel** раздаёт файлы из ветки `gh-pages` (настройка: Vercel Dashboard → проект → Settings → Git → Production Branch = `gh-pages`).
- Файл `vercel.json` синхронизируется в `gh-pages` вместе с результатами — правки в него вносятся в `main`, а при следующем прогоне CI они автоматически попадают в `gh-pages`.

---

## 🇷🇺 RU-проба (RU-verified подписка)

Раннеры GitHub находятся **вне РФ**, поэтому «живость» узла не гарантирует его
доступность за ТСПУ (см. `AUDIT.md` §5.1). Чтобы выдавать узлы, *реально проверенные
изнутри России*, есть отдельная подписка **`sub_ru.txt`** (`/sub/ru`), наполняемая
вердиктом внешнего RU-воркера.

**Контракт ингестии (env-gated):**
- Узел помечается `ru_verified=True`, если его `strict_id` присутствует в вердикт-файле.
- Путь к файлу задаётся переменной окружения **`RU_VERDICT_FILE`**.
- Формат файла — JSON: либо голый список id (`["vless:host:443:uuid:tcp", ...]`),
  либо объект `{"verified": [...]}` / `{"ids": [...]}`.
- Если `RU_VERDICT_FILE` не задан или файл отсутствует — `sub_ru.txt` просто пустой
  (никаких ошибок), поведение остального пайплайна не меняется.

**Как запустить RU-воркер (операционно, вне CI этого репозитория):**
1. Поднимите дешёвый RU-VPS (или мобильный RU-прокси) как воркер.
2. Воркер скачивает опубликованную подписку (`/sub` → `sub_all.txt`).
3. Для каждой строки-URI вычисляет `strict_id` тем же парсером, что и репозиторий:
   `LinkParser.parse_link(uri).strict_id` (см. `core/parser.py`).
4. Повторяет L7-проверку узла **изнутри РФ** и собирает список `strict_id` выживших.
5. Публикует этот список JSON-файлом (артефакт/релиз/эндпоинт).
6. В CullDrone-шаге (`.github/workflows/update.yml` → «Execute Shard Protocol»)
   добавьте шаг, который скачивает вердикт и экспортирует `RU_VERDICT_FILE`,
   указывающий на него. Дроны пометят совпавшие узлы и положат их в `sub_ru.txt`,
   `merge.py` сольёт шардовые `sub_ru_*.txt`, а publish-шаг опубликует `sub_ru.txt`
   в `gh-pages`.

> Сам RU-воркер не входит в этот репозиторий и не требуется для корректности кода —
> это лишь точка интеграции. Без него подписка `sub_ru` остаётся пустой.

---

## ⚖️ Граница ответственности (Disclaimer)

Данный репозиторий и скрипты являются автоматизированным парсером метаданных. Программное обеспечение предоставляется «как есть» (AS IS), без каких-либо гарантий. Код предоставляется исключительно в образовательных и исследовательских целях. Автор не является владельцем представленных в выдаче серверов и не несёт ответственности за использование предоставленных конфигураций конечным пользователем, а также за любой возможный ущерб. Использование скрипта для действий, нарушающих законодательство вашей юрисдикции, строго запрещено.

<div align="center">
  <br />
  <sub>🦇 Scarlet Devil Network — Neo-Gensokyo Routing Architecture · AGPL-3.0</sub>
</div>
