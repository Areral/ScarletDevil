const BASE_URL = window.location.origin;

const APP_DATABASE = {
    "throne": {
        name: "Throne", icon: "fa-solid fa-chess-rook", url: "https://github.com/throneproj/Throne/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Нажмите <b>«Получить доступ»</b> выше и скопируйте ссылку на подписку.</div>
                <div class="step-item">В клиенте нажмите на <b>«Профили»</b> -> <b>«Добавить профиль из буфера обмена»</b>.</div>
                <div class="step-item">Выделите все профили (Ctrl+A), нажмите <b>«Профили»</b> -> <b>«Тест задержки (пинга)»</b>.</div>
                <div class="step-item">Дождитесь надписи <i>«Тест задержек завершён!»</i> в логах снизу.</div>
                <div class="step-item">Кликните по колонке <b>«Задержка (пинг)»</b> для сортировки от меньшего к большему.</div>
                <div class="step-item">Сверху установите галочку <b>«Режим TUN»</b> (важно для обхода DPI).</div>
                <div class="step-item">Выберите сервер с лучшим пингом -> Правая кнопка мыши -> <b>«Запустить»</b>.</div>
            </div>
        `
    },
    "nekobox": {
        name: "NekoBox", icon: "fa-solid fa-cat", url: "https://github.com/MatsuriDayo/nekoray/releases/latest",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">Перейдите в <b>«Настройки»</b> -> <b>«Группы»</b> -> <b>«Новая группа»</b>.</div>
                <div class="step-item">Выберите тип <b>«Подписка»</b> и вставьте вашу ссылку. Нажмите Ок.</div>
                <div class="step-item">Нажмите кнопку <b>«Обновить подписки»</b>.</div>
                <div class="step-item">Включите галочку <b>«Режим TUN»</b> и запустите выбранный сервер.</div>
            </div>
        `
    },
    "v2rayn": {
        name: "v2rayN", icon: "fa-solid fa-v", url: "https://github.com/2dust/v2rayN/releases/latest",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на конфиг.</div>
                <div class="step-item">Перейдите в <b>«Подписки»</b> -> <b>«Настройки подписки»</b> -> <b>«Добавить»</b>.</div>
                <div class="step-item">Вставьте ссылку в поле <code>Url</code>, сохраните.</div>
                <div class="step-item">В главном меню нажмите <b>«Обновить подписку»</b>.</div>
                <div class="step-item">Выделите сервер с хорошим пингом и нажмите <b>Enter</b> для подключения.</div>
            </div>
        `
    },
    "singbox": {
        name: "Sing-box UI", icon: "fa-solid fa-box", url: "https://github.com/Leadaxe/singbox-launcher/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">Запустите Singbox-launcher и перейдите во вкладку профилей.</div>
                <div class="step-item">Нажмите <b>«Добавить»</b> и вставьте вашу ссылку.</div>
                <div class="step-item">Сделайте тест задержки и выберите оптимальный маршрут.</div>
                <div class="step-item">Нажмите главную кнопку старта для активации туннеля.</div>
            </div>
        `
    },
    "karing": {
        name: "Karing", icon: "fa-solid fa-paper-plane", url: "https://github.com/KaringX/karing/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">Откройте приложение Karing.</div>
                <div class="step-item">Нажмите на значок <b>«+»</b> и выберите <b>«Импорт из буфера обмена»</b>.</div>
                <div class="step-item">Запустите тест задержки.</div>
                <div class="step-item">Выберите лучший сервер и сдвиньте переключатель подключения.</div>
            </div>
        `
    },
    "v2rayng": {
        name: "v2rayNG", icon: "fa-brands fa-android", url: "https://github.com/2dust/v2rayNG/releases/latest",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В приложении нажмите на <b>«+»</b> (справа сверху) -> <b>«Импорт из буфера обмена»</b>.</div>
                <div class="step-item">Нажмите три точки -> <b>«Проверка профилей группы»</b>.</div>
                <div class="step-item">Снова три точки -> <b>«Сортировка по результатам теста»</b>.</div>
                <div class="step-item">Выберите сервер с зеленым пингом и нажмите кнопку <b>▶️ (Старт)</b>.</div>
            </div>
        `
    },
    "v2raytun": {
        name: "v2RayTun", icon: "fa-solid fa-rocket", url: "https://v2raytun.com/",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">Откройте v2RayTun и перейдите в раздел управления серверами.</div>
                <div class="step-item">Нажмите иконку <b>добавления</b> -> выберите <b>«Импорт из буфера обмена»</b>.</div>
                <div class="step-item">Обновите подписку, выберите сервер с зеленым пингом и нажмите кнопку старта.</div>
            </div>
        `
    },
    "v2box": {
        name: "V2Box", icon: "fa-brands fa-app-store-ios", url: "https://apps.apple.com/ru/app/v2box-v2ray-client/id6446814690",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку с нашего сайта.</div>
                <div class="step-item">Откройте V2Box, перейдите во вкладку <b>«Config»</b>.</div>
                <div class="step-item">Нажмите на <b>«+»</b> -> <b>«Добавить подписку»</b>.</div>
                <div class="step-item">Вставьте ссылку в поле <code>URL</code>, введите Имя и сохраните.</div>
                <div class="step-item">Дождитесь проверки пинга, выберите сервер и нажмите <b>«Подключиться»</b>.</div>
            </div>
        `
    },
    "shadowrocket": {
        name: "Shadowrocket", icon: "fa-solid fa-rocket", url: "https://apps.apple.com/us/app/shadowrocket/id932747118",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">Откройте Shadowrocket (клиент платный, но стабильный на iOS).</div>
                <div class="step-item">Нажмите <b>«+»</b> в правом верхнем углу, выберите тип <b>«Subscribe»</b>.</div>
                <div class="step-item">Вставьте ссылку в поле URL и сохраните.</div>
                <div class="step-item">Сделайте тест подключения (Connectivity Test), выберите сервер и включите VPN.</div>
            </div>
        `
    },
    "streisand": {
        name: "Streisand", icon: "fa-solid fa-shield-cat", url: "https://apps.apple.com/us/app/streisand/id6450534064",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на маршрут.</div>
                <div class="step-item">Откройте Streisand, нажмите на иконку <b>«+»</b> в правом верхнем углу.</div>
                <div class="step-item">Выберите <b>«Add Subscription»</b>.</div>
                <div class="step-item">Вставьте ссылку в поле <code>URL</code> и сохраните.</div>
                <div class="step-item">Зажмите палец на названии подписки и выберите <b>«Latency Test»</b>.</div>
                <div class="step-item">Выберите лучший узел и нажмите главную кнопку подключения.</div>
            </div>
        `
    },
    "hiddify": {
        name: "Hiddify", icon: "fa-solid fa-shield-halved", url: "https://github.com/hiddify/hiddify-app/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">Откройте приложение Hiddify и нажмите <b>«Новый профиль»</b>.</div>
                <div class="step-item">Выберите <b>«Добавить из буфера обмена»</b>.</div>
                <div class="step-item"><b>Важно:</b> Перейдите в настройки программы и измените "Вариант маршрутизации" на <b>"Индонезия"</b> (или "Россия").</div>
                <div class="step-item">Нажмите огромную круглую кнопку посередине экрана для запуска.</div>
            </div>
        `
    },
    "flclash": {
        name: "FlClash", icon: "fa-solid fa-fire", url: "https://github.com/chen08209/FlClash/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку с нашего сайта.</div>
                <div class="step-item">В FlClash перейдите в раздел <b>«Profiles»</b> и нажмите <b>«+»</b> -> <b>«Import from URL»</b>.</div>
                <div class="step-item">Вставьте скопированную ссылку и нажмите <b>«Save»</b>.</div>
                <div class="step-item">На главном экране нажмите <b>«Test Latency»</b> (значок таймера) для проверки всех узлов.</div>
                <div class="step-item">Отсортируйте по задержке, выберите узел и включите переключатель VPN.</div>
            </div>
        `
    },
    "mihomo": {
        name: "Mihomo (Clash Meta)", icon: "fa-solid fa-layer-group", url: "https://github.com/MetaCubeX/mihomo/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В веб-интерфейсе (metacubexd/yacd) перейдите в раздел <b>«Profiles»</b>.</div>
                <div class="step-item">Нажмите <b>«New Profile»</b>, вставьте URL подписки и нажмите <b>«Download»</b>.</div>
                <div class="step-item">На вкладке <b>«Proxies»</b> выберите узел с низкой задержкой (зелёный индикатор).</div>
                <div class="step-item">Включите <b>«System Proxy»</b> или TUN-режим для перенаправления всего трафика.</div>
            </div>
        `
    },
    "amneziawg": {
        name: "AmneziaWG", icon: "fa-solid fa-lock", url: "https://github.com/amnezia-vpn/amnezia-client/releases/latest",
        protocols: ['wireguard'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку нужного маршрута (рекомендуется ЧС/VLESS).</div>
                <div class="step-item">Откройте Amnezia, нажмите <b>«Добавить»</b> -> <b>«Импорт из URL»</b>.</div>
                <div class="step-item">Вставьте ссылку и дождитесь загрузки конфигурации.</div>
                <div class="step-item">В настройках подключения включите <b>«Маскировка трафика»</b> (обфускация WireGuard).</div>
                <div class="step-item">Нажмите <b>«Подключиться»</b> для активации защищённого туннеля.</div>
            </div>
        `
    },
    "sagernet": {
        name: "SagerNet", icon: "fa-solid fa-code-branch", url: "https://github.com/SagerNet/SagerNet/releases/latest",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В SagerNet откройте боковое меню и нажмите <b>«Manage Subscriptions»</b>.</div>
                <div class="step-item">Нажмите <b>«+»</b>, вставьте URL подписки и нажмите <b>«OK»</b>.</div>
                <div class="step-item">Нажмите на подписку для обновления списка серверов, затем выполните <b>«URL Test»</b>.</div>
                <div class="step-item">Выберите узел с наименьшей задержкой и нажмите кнопку подключения внизу экрана.</div>
            </div>
        `
    },
    "foxray": {
        name: "FoXray", icon: "fa-solid fa-shield", url: "https://github.com/FoXray/foXray/releases/latest",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В FoXray перейдите в раздел <b>«Подписки»</b> и нажмите <b>«+»</b>.</div>
                <div class="step-item">Вставьте ссылку в поле URL и нажмите <b>«Сохранить»</b>.</div>
                <div class="step-item">Обновите подписку (потяните вниз или кнопка обновления) и дождитесь загрузки узлов.</div>
                <div class="step-item">Выберите сервер с лучшим пингом и нажмите кнопку подключения в центре экрана.</div>
            </div>
        `
    },
    "surge": {
        name: "Surge", icon: "fa-solid fa-wave-square", url: "https://nssurge.com/",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В Surge перейдите в <b>«Config»</b> (верхнее меню) -> <b>«Download Configuration from URL»</b>.</div>
                <div class="step-item">Вставьте ссылку и нажмите <b>«Download»</b>.</div>
                <div class="step-item">После загрузки нажмите <b>«Setup»</b> и выберите политику маршрутизации (Rule/Global).</div>
                <div class="step-item">Запустите туннель кнопкой <b>«Start»</b> на главном экране.</div>
            </div>
        `
    },
    "stash": {
        name: "Stash", icon: "fa-solid fa-box-archive", url: "https://apps.apple.com/app/stash/id1596063349",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В Stash перейдите в <b>«Proxies»</b> -> <b>«Import»</b> -> <b>«From URL»</b>.</div>
                <div class="step-item">Вставьте URL подписки и нажмите <b>«OK»</b>.</div>
                <div class="step-item">На вкладке <b>«Dashboard»</b> выберите узел с низкой задержкой (зелёный индикатор).</div>
                <div class="step-item">Нажмите <b>«Connect»</b> для запуска прокси-туннеля через выбранный узел.</div>
            </div>
        `
    },
    "singbox_cli": {
        name: "Sing-box CLI", icon: "fa-solid fa-terminal", url: "https://github.com/SagerNet/sing-box/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скачайте готовый <code>config.json</code> из подписки или сгенерируйте его из ссылки.</div>
                <div class="step-item">Установите sing-box: <code>brew install sing-box</code> (Mac), <code>scoop install sing-box</code> (Win), или скачайте бинарник из GitHub Releases.</div>
                <div class="step-item">Поместите <code>config.json</code> в <code>/etc/sing-box/</code> или в произвольную директорию.</div>
                <div class="step-item">Запустите: <code>sudo sing-box run -c config.json</code> (Linux/Mac) или <code>sing-box.exe run -c config.json</code> (Windows).</div>
                <div class="step-item">Проверьте работу: <code>curl --proxy http://127.0.0.1:2080 https://www.google.com</code></div>
            </div>
        `
    },
    "mikrotik": {
        name: "MikroTik (RouterOS)", icon: "fa-solid fa-wifi", url: "https://mikrotik.com/download",
        protocols: ['sstp','l2tp','wireguard'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте данные выбранного сервера (SSTP/L2TP/WireGuard) из подписки.</div>
                <div class="step-item">Подключитесь к RouterOS через <b>WinBox</b> или SSH.</div>
                <div class="step-item">Создайте туннель: <b>«PPP»</b> -> <b>«Interfaces»</b> -> <b>«+»</b> -> выберите тип (SSTP Client/L2TP Client).</div>
                <div class="step-item">Введите адрес сервера, логин и пароль. На вкладке <b>«Dial Out»</b> настройте параметры подключения.</div>
                <div class="step-item">В <b>«IP»</b> -> <b>«Routes»</b> добавьте маршрут: <code>Dst. Address=0.0.0.0/0</code>, <code>Gateway=&lt;sstp-interface&gt;</code>.</div>
                <div class="step-item">Проверьте: <code>/tool traceroute 8.8.8.8</code> — трафик должен идти через VPN-туннель.</div>
                <div class="step-item"><b>Совет:</b> Для VLESS/VMess/обфускации установите OpenWRT или подключите внешний sing-box к роутеру.</div>
            </div>
        `
    },
    "openwrt": {
        name: "OpenWRT", icon: "fa-solid fa-globe", url: "https://firmware-selector.openwrt.org/",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Установите OpenWRT на ваш роутер (см. <b>Firmware Selector</b>).</div>
                <div class="step-item">Установите sing-box: <code>opkg update && opkg install sing-box</code>.</div>
                <div class="step-item">Через <b>LuCI</b> веб-интерфейс: <b>«Services»</b> -> <b>«PassWall»</b> / <b>«PassWall2»</b> -> <b>«Node List»</b> -> <b>«Add»</b>.</div>
                <div class="step-item">Вставьте конфигурацию подписки (URL или готовый JSON) и назначьте политику маршрутизации.</div>
                <div class="step-item">Примените настройки и проверьте соединение через <b>«Tools»</b> -> <b>«Ping»</b>.</div>
                <div class="step-item"><b>Альтернатива:</b> Установите <code>luci-app-openclash</code> для работы с Clash-подписками напрямую.</div>
            </div>
        `
    },
    "nekoray": {
        name: "NekoRay", icon: "fa-solid fa-skull", url: "https://github.com/MatsuriDayo/nekoray/releases/latest",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В NekoRay нажмите правой кнопкой в пустой области -> <b>«Добавить профиль из буфера обмена»</b>.</div>
                <div class="step-item">Или через меню: <b>«Программа»</b> -> <b>«Добавить подписку»</b> -> вставьте URL -> <b>«Обновить подписку»</b>.</div>
                <div class="step-item">Выделите все профили (Ctrl+A) -> правый клик -> <b>«Тест скорости»</b>.</div>
                <div class="step-item">Отсортируйте по колонке скорости, выберите узел и нажмите <b>Enter</b> для запуска.</div>
            </div>
        `
    }
};

const PLATFORMS = {
    windows:['throne', 'nekobox', 'v2rayn', 'hiddify', 'karing', 'singbox', 'flclash', 'mihomo', 'amneziawg', 'singbox_cli', 'nekoray'],
    android:['v2rayng', 'nekobox', 'v2raytun', 'hiddify', 'karing', 'flclash', 'amneziawg', 'sagernet', 'foxray'],
    androidtv:['v2rayng', 'sagernet', 'flclash'],
    ios:['v2box', 'streisand', 'shadowrocket', 'karing', 'v2raytun', 'hiddify', 'amneziawg', 'surge', 'stash'],
    mac:['hiddify', 'throne', 'karing', 'singbox', 'flclash', 'mihomo', 'amneziawg', 'surge', 'stash', 'singbox_cli'],
    linux:['throne', 'nekobox', 'hiddify', 'karing', 'flclash', 'mihomo', 'amneziawg', 'singbox_cli', 'nekoray'],
    router:['mikrotik', 'openwrt', 'singbox_cli', 'mihomo']
};

let currentPlatform = 'windows';
let currentAppId = PLATFORMS['windows'][0];

function init() {
    const ua = navigator.userAgent.toLowerCase();
    if (ua.includes("android") && (ua.includes("tv") || window.innerWidth > 1000)) currentPlatform = 'androidtv';
    else if (ua.includes("android")) currentPlatform = 'android';
    else if (ua.includes("iphone") || ua.includes("ipad")) currentPlatform = 'ios';
    else if (ua.includes("macintosh") || ua.includes("mac os")) currentPlatform = 'mac';
    else if (ua.includes("linux")) currentPlatform = 'linux';
    else currentPlatform = 'windows';
    
    currentAppId = PLATFORMS[currentPlatform][0];
    updateUI();
    initScrollSpy();
    initReveal();
    initFunPanel();
}

function switchPlatform(platform) {
    currentPlatform = platform;
    currentAppId = PLATFORMS[platform][0];
    updateUI();
}

function selectApp(appId) {
    currentAppId = appId;
    updateUI();
}

function updateUI() {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    const activeTab = document.getElementById(`tab-${currentPlatform}`);
    if(activeTab) activeTab.classList.add('active');

    const grid = document.getElementById('app-grid');
    grid.innerHTML = '';
    
    PLATFORMS[currentPlatform].forEach(appId => {
        const appInfo = APP_DATABASE[appId];
        const div = document.createElement('div');
        div.className = `app-card ${appId === currentAppId ? 'selected' : ''}`;
        div.onclick = () => selectApp(appId);
        div.innerHTML = `<i class="${appInfo.icon} app-icon"></i><div class="app-name">${appInfo.name}</div>`;
        grid.appendChild(div);
    });

    const currentApp = APP_DATABASE[currentAppId];
    const btn = document.getElementById('download-btn');
    btn.href = currentApp.url;
    document.getElementById('app-name-display').innerText = currentApp.name;
    document.getElementById('instruction-text').innerHTML = currentApp.guide;

    const protoDisplay = document.getElementById('protocol-display');
    if (protoDisplay && currentApp.protocols) {
        protoDisplay.innerHTML = currentApp.protocols.map(p =>
            `<span class="proto-tag">${p.toUpperCase()}</span>`
        ).join('');
    }
}

function initReveal() {
    const reveals = document.querySelectorAll('.reveal');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('active');
            }
        });
    }, { threshold: 0.1 });
    
    reveals.forEach(reveal => observer.observe(reveal));
}

function initScrollSpy() {
    const sections = document.querySelectorAll('section');
    const navBtns = document.querySelectorAll('.nav-btn');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const currentId = entry.target.getAttribute('id');
                navBtns.forEach(btn => {
                    btn.classList.remove('active');
                    if (btn.getAttribute('data-target') === currentId) {
                        btn.classList.add('active');
                    }
                });
            }
        });
    }, { rootMargin: '-40% 0px -60% 0px' });

    sections.forEach(sec => observer.observe(sec));

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            document.getElementById(targetId).scrollIntoView({ behavior: 'smooth' });
        });
    });
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

function acceptRules() {
    closeModal('rules-modal');
    setTimeout(() => openModal('configs-modal'), 300);
}

function copySub(path, name) {
    const fullUrl = BASE_URL + path;
    navigator.clipboard.writeText(fullUrl).then(() => {
        closeModal('configs-modal');
        const toast = document.getElementById('toast');
        document.getElementById('toast-text').innerText = `Спелл-карта [${name}] скопирована!`;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3500);
    });
}

// --- FUN PANEL EFFECTS (TOUHOU EASTER EGGS) ---
function initFunPanel() {
    const btnMist = document.getElementById('btn-mist');
    const btnDanmaku = document.getElementById('btn-danmaku');
    const btnBats = document.getElementById('btn-bats');
    
    const mistLayer = document.getElementById('mist-layer');
    
    let danmakuInterval = null;
    let batsInterval = null;

    btnMist.addEventListener('click', () => {
        btnMist.classList.toggle('active');
        mistLayer.classList.toggle('active');
    });

    btnDanmaku.addEventListener('click', () => {
        if (danmakuInterval) {
            clearInterval(danmakuInterval);
            danmakuInterval = null;
            btnDanmaku.classList.remove('active');
        } else {
            btnDanmaku.classList.add('active');
            danmakuInterval = setInterval(() => {
                const orb = document.createElement('div');
                orb.className = 'danmaku-bullet';
                const size = Math.random() * 12 + 6;
                orb.style.width = size + 'px';
                orb.style.height = size + 'px';
                orb.style.left = Math.random() * 100 + 'vw';
                orb.style.top = '-20px';
                orb.style.color = Math.random() > 0.5 ? '#f472b6' : '#e11d48';
                orb.style.backgroundColor = 'currentColor';
                orb.style.animationDuration = (Math.random() * 3 + 2) + 's';
                document.body.appendChild(orb);
                setTimeout(() => orb.remove(), 6000);
            }, 150);
        }
    });

    btnBats.addEventListener('click', () => {
        if (batsInterval) {
            clearInterval(batsInterval);
            batsInterval = null;
            btnBats.classList.remove('active');
        } else {
            btnBats.classList.add('active');
            batsInterval = setInterval(() => {
                const bat = document.createElement('div');
                bat.className = 'bat-spirit';
                bat.innerHTML = '<i class="fa-solid fa-ghost"></i>';
                bat.style.color = Math.random() > 0.5 ? '#8b5cf6' : '#e11d48';
                bat.style.left = '-50px';
                bat.style.top = (Math.random() * 80 + 10) + 'vh';
                bat.style.setProperty('--y-end', (Math.random() * 200 - 100) + 'px');
                bat.style.animationDuration = (Math.random() * 4 + 4) + 's';
                document.body.appendChild(bat);
                setTimeout(() => bat.remove(), 9000);
            }, 800);
        }
    });
}

init();
