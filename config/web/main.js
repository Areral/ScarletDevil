const BASE_URL = window.location.origin;

// ─── QR Code Generator (Byte mode, EC Level L, versions 1-6) ───
const QR = (function() {
    const EXP = new Int32Array(512);
    const LOG = new Int32Array(256);

    // GF(256) with primitive polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11D)
    (function initGF() {
        let v = 1;
        for (let i = 0; i < 256; i++) {
            EXP[i] = v;
            LOG[v] = i;
            v <<= 1;
            if (v & 256) v ^= 285;
        }
        for (let i = 256; i < 512; i++) EXP[i] = EXP[i - 255];
        LOG[1] = 0;
    })();

    // EC level L parameters for versions 1-6
    const EC_INFO = [
        null,
        { total: 26,  ecPerBlock: 7,  blocks: 1, dataPerBlock: 19  }, // v1
        { total: 44,  ecPerBlock: 10, blocks: 1, dataPerBlock: 34  }, // v2
        { total: 70,  ecPerBlock: 15, blocks: 1, dataPerBlock: 55  }, // v3
        { total: 100, ecPerBlock: 20, blocks: 1, dataPerBlock: 80  }, // v4
        { total: 134, ecPerBlock: 26, blocks: 1, dataPerBlock: 108 }, // v5
        { total: 172, ecPerBlock: 18, blocks: 2, dataPerBlock: 68  }, // v6
    ];

    const ALIGNMENT_POS = [
        [], [], [6,18], [6,22], [6,26], [6,30], [6,34]
    ];

    // Precomputed format info for EC L + mask 0-7
    const FORMAT_INFO = [0x5412, 0x5125, 0x5E7C, 0x5B4B, 0x45F9, 0x40CE, 0x4F97, 0x4AA0];

    function gfMul(a, b) {
        if (a === 0 || b === 0) return 0;
        return EXP[LOG[a] + LOG[b]];
    }

    function gfInv(a) {
        return EXP[255 - LOG[a]];
    }

    function polyMul(a, b) {
        const r = new Array(a.length + b.length - 1).fill(0);
        for (let i = 0; i < a.length; i++)
            for (let j = 0; j < b.length; j++)
                r[i + j] ^= gfMul(a[i], b[j]);
        return r;
    }

    function generatorPoly(degree) {
        let g = [1];
        for (let i = 0; i < degree; i++)
            g = polyMul(g, [EXP[i], 1]);
        return g;
    }

    function computeEC(data, ecCount) {
        const gen = generatorPoly(ecCount);
        const msg = data.concat(new Array(ecCount).fill(0));
        const invG0 = gfInv(gen[0]);
        for (let i = 0; i < data.length; i++) {
            if (msg[i] === 0) continue;
            const factor = gfMul(msg[i], invG0);
            for (let j = 0; j < gen.length; j++)
                msg[i + j] ^= gfMul(gen[j], factor);
        }
        return msg.slice(data.length);
    }

    function selectVersion(dataLen) {
        const bits = 4 + 8 + dataLen * 8 + 4;
        const cwNeeded = Math.ceil(bits / 8);
        for (let v = 1; v <= 6; v++)
            if (EC_INFO[v].dataPerBlock * EC_INFO[v].blocks >= cwNeeded) return v;
        return 6;
    }

    function encodeByteMode(text, version) {
        const info = EC_INFO[version];
        const totalDataCW = info.dataPerBlock * info.blocks;
        const bits = [];

        // Mode indicator: 0100
        bits.push(0, 1, 0, 0);
        // Character count (8 bits for v1-9)
        const len = text.length;
        for (let i = 7; i >= 0; i--) bits.push((len >> i) & 1);
        // Data bytes
        for (let i = 0; i < len; i++) {
            const c = text.charCodeAt(i);
            for (let j = 7; j >= 0; j--) bits.push((c >> j) & 1);
        }
        // Terminator
        const termLen = Math.min(4, totalDataCW * 8 - bits.length);
        for (let i = 0; i < termLen; i++) bits.push(0);
        // Pad to byte
        while (bits.length % 8) bits.push(0);
        // Pad bytes
        const padBytes = [0xEC, 0x11];
        let pi = 0;
        while (bits.length < totalDataCW * 8) {
            const b = padBytes[pi % 2]; pi++;
            for (let j = 7; j >= 0; j--) bits.push((b >> j) & 1);
        }
        // Convert to codewords
        const cw = [];
        for (let i = 0; i < totalDataCW; i++) {
            let val = 0;
            for (let j = 0; j < 8; j++) val = (val << 1) | bits[i * 8 + j];
            cw.push(val);
        }
        return cw;
    }

    function placeFinder(m, r, c) {
        for (let i = 0; i < 7; i++)
            for (let j = 0; j < 7; j++)
                m[r + i][c + j] = (
                    i === 0 || i === 6 || j === 0 || j === 6 ||
                    (i >= 2 && i <= 4 && j >= 2 && j <= 4)
                ) ? 1 : 0;
    }

    function placeAlignment(m, row, col) {
        for (let i = -2; i <= 2; i++)
            for (let j = -2; j <= 2; j++)
                m[row + i][col + j] = (
                    i === -2 || i === 2 || j === -2 || j === 2 || (i === 0 && j === 0)
                ) ? 1 : 0;
    }

    function buildMatrix(dataCW, ecBlocks, version) {
        const size = version * 4 + 17;
        // Init matrix: 0=empty, 1=reserved dark, 2=reserved light
        const m = Array.from({length: size}, () => new Int32Array(size));

        // Finder patterns
        placeFinder(m, 0, 0);
        placeFinder(m, 0, size - 7);
        placeFinder(m, size - 7, 0);

        // Separators
        for (let i = 0; i < 8; i++) {
            m[i][7] = m[7][i] = 2;
            m[i][size - 8] = m[7][size - 1 - i] = 2;
            m[size - 8][i] = m[size - 1 - i][7] = 2;
        }

        // Timing patterns
        for (let i = 8; i < size - 8; i++)
            m[6][i] = m[i][6] = (i % 2 === 0) ? 1 : 0;

        // Alignment patterns
        const apos = ALIGNMENT_POS[version];
        for (const ar of apos) {
            for (const ac of apos) {
                if ((ar <= 8 && ac <= 8) || (ar <= 8 && ac >= size - 8) || (ar >= size - 8 && ac <= 8)) continue;
                placeAlignment(m, ar, ac);
            }
        }

        // Dark module
        m[size - 8][8] = 1;

        // Reserve format info areas
        for (let i = 0; i < 9; i++) {
            if (m[i][8] === 0) m[i][8] = 3;
            if (i < 8 && m[8][i] === 0) m[8][i] = 3;
        }
        for (let i = 0; i < 8; i++) {
            m[size - 1 - i][8] = 3;
            if (i < 7) m[8][size - 1 - i] = 3;
        }
        // Reserve version info (v7+): none needed for v1-6

        // Flatten all EC blocks into bit stream
        const allBits = [];
        for (let b = 0; b < EC_INFO[version].blocks; b++) {
            for (let i = 0; i < EC_INFO[version].dataPerBlock; i++) {
                const cw = dataCW[b * EC_INFO[version].dataPerBlock + i];
                for (let j = 7; j >= 0; j--) allBits.push((cw >> j) & 1);
            }
            for (let i = 0; i < EC_INFO[version].ecPerBlock; i++) {
                const cw = ecBlocks[b * EC_INFO[version].ecPerBlock + i];
                for (let j = 7; j >= 0; j--) allBits.push((cw >> j) & 1);
            }
        }

        // Place data in zigzag pattern, bottom-right to top-left
        let bitIdx = 0;
        let up = true;
        for (let col = size - 1; col >= 0; col -= 2) {
            if (col === 6) col = 5;
            for (let row = up ? size - 1 : 0; up ? row >= 0 : row < size; row += up ? -1 : 1) {
                for (const c of [col, col - 1]) {
                    if (c < 0 || c >= size) continue;
                    if (m[row][c] === 0) {
                        if (bitIdx < allBits.length) {
                            m[row][c] = allBits[bitIdx] ? 5 : 4; // 5=data-dark, 4=data-light
                        } else {
                            m[row][c] = 4; // fill remaining with light
                        }
                        bitIdx++;
                    }
                }
            }
            up = !up;
        }

        return m;
    }

    function applyMaskPattern(row, col, mask) {
        switch (mask) {
            case 0: return (row + col) % 2 === 0;
            case 1: return row % 2 === 0;
            case 2: return col % 3 === 0;
            case 3: return (row + col) % 3 === 0;
            case 4: return (Math.floor(row / 2) + Math.floor(col / 3)) % 2 === 0;
            case 5: return (row * col) % 2 + (row * col) % 3 === 0;
            case 6: return ((row * col) % 2 + (row * col) % 3) % 2 === 0;
            case 7: return ((row + col) % 2 + (row * col) % 3) % 2 === 0;
        }
        return false;
    }

    function maskMatrix(m, size, mask) {
        const result = Array.from({length: size}, () => new Uint8Array(size));
        for (let r = 0; r < size; r++) {
            for (let c = 0; c < size; c++) {
                let val = (m[r][c] === 1 || m[r][c] === 5); // 1=reserved dark, 5=data dark
                // Don't mask function patterns (0-2 are basic, 3 is format reserve)
                if (m[r][c] >= 4) { // data modules
                    if (applyMaskPattern(r, c, mask)) val = !val;
                } else if (m[r][c] === 3) { // format reserve
                    if (applyMaskPattern(r, c, mask)) val = !val;
                }
                result[r][c] = val ? 1 : 0;
            }
        }
        return result;
    }

    function evalPenalty(m, size) {
        let penalty = 0;
        // Rule 1: 5+ same-color modules in row/col
        for (let r = 0; r < size; r++) {
            let run = 1;
            for (let c = 1; c < size; c++) {
                if (m[r][c] === m[r][c - 1]) { run++; }
                else { if (run >= 5) penalty += run - 2; run = 1; }
            }
            if (run >= 5) penalty += run - 2;
        }
        for (let c = 0; c < size; c++) {
            let run = 1;
            for (let r = 1; r < size; r++) {
                if (m[r][c] === m[r - 1][c]) { run++; }
                else { if (run >= 5) penalty += run - 2; run = 1; }
            }
            if (run >= 5) penalty += run - 2;
        }
        // Rule 2: 2x2 blocks
        for (let r = 0; r < size - 1; r++)
            for (let c = 0; c < size - 1; c++)
                if (m[r][c] === m[r+1][c] && m[r][c] === m[r][c+1] && m[r][c] === m[r+1][c+1])
                    penalty += 3;
        // Rule 3: finder-like patterns (1011101)
        const PAT = [1,0,1,1,1,0,1];
        for (let r = 0; r < size; r++) {
            for (let c = 0; c <= size - 7; c++) {
                let match = true;
                for (let k = 0; k < 7; k++)
                    if (m[r][c+k] !== PAT[k]) { match = false; break; }
                if (match) penalty += 40;
            }
        }
        for (let c = 0; c < size; c++) {
            for (let r = 0; r <= size - 7; r++) {
                let match = true;
                for (let k = 0; k < 7; k++)
                    if (m[r+k][c] !== PAT[k]) { match = false; break; }
                if (match) penalty += 40;
            }
        }
        // Rule 4: dark/light ratio
        let dark = 0;
        for (let r = 0; r < size; r++)
            for (let c = 0; c < size; c++)
                if (m[r][c]) dark++;
        const ratio = (dark / (size * size)) * 100;
        const dev = Math.abs(Math.round(ratio / 5) * 5 - 50) / 5;
        penalty += dev * 10;
        return penalty;
    }

    function placeFormat(m, size, mask) {
        const fi = FORMAT_INFO[mask];
        // Top-left: bits 14..0
        const coords = [
            [8,0],[8,1],[8,2],[8,3],[8,4],[8,5], // bits 14-9
            [size-1,8],[size-2,8],[size-3,8],[size-4,8],[size-5,8],[size-6,8],[size-7,8], // bits 8-2... wait
        ];
        // Actually, let me just use the right coordinates
        // Location 1: around top-left finder
        // bit 0: [size-1,8]
        // Actually, the QR spec places format bits as follows:
        // Location A (around top-left):
        const locA = [[8,0],[8,1],[8,2],[8,3],[8,4],[8,5],[8,7],[8,8],[7,8],[5,8],[4,8],[3,8],[2,8],[1,8],[0,8]];
        // Location B (split):
        const locB = [[size-1,8],[size-2,8],[size-3,8],[size-4,8],[size-5,8],[size-6,8],[size-7,8],[8,size-8],[8,size-7],[8,size-6],[8,size-5],[8,size-4],[8,size-3],[8,size-2],[8,size-1]];

        for (let i = 0; i < 15; i++) {
            const bit = (fi >> i) & 1;
            const [rA, cA] = locA[i];
            const [rB, cB] = locB[i];
            m[rA][cA] = bit;
            m[rB][cB] = bit;
        }
    }

    function generateMatrix(text) {
        const version = selectVersion(text.length);
        const info = EC_INFO[version];
        const encoded = encodeByteMode(text, version);

        // Split into blocks and compute EC per block
        const ecBlocks = [];
        for (let b = 0; b < info.blocks; b++) {
            const blockData = encoded.slice(b * info.dataPerBlock, (b + 1) * info.dataPerBlock);
            ecBlocks.push(...computeEC(blockData, info.ecPerBlock));
        }

        const raw = buildMatrix(encoded, ecBlocks, version);
        const size = version * 4 + 17;

        // Evaluate all 8 masks
        let bestMask = 0, bestPenalty = Infinity, bestMatrix = null;
        for (let mask = 0; mask < 8; mask++) {
            const masked = maskMatrix(raw, size, mask);
            placeFormat(masked, size, mask);
            const penalty = evalPenalty(masked, size);
            if (penalty < bestPenalty) {
                bestPenalty = penalty;
                bestMask = mask;
                bestMatrix = masked;
            }
        }
        placeFormat(bestMatrix, size, bestMask);
        return { matrix: bestMatrix, size };
    }

    function toCanvas(text, moduleSize) {
        const { matrix, size } = generateMatrix(text);
        const pixSize = moduleSize || 6;
        const padding = pixSize * 4;
        const total = size * pixSize + padding * 2;

        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = total;
        const ctx = canvas.getContext('2d');

        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, total, total);

        ctx.fillStyle = '#000000';
        for (let r = 0; r < size; r++) {
            for (let c = 0; c < size; c++) {
                if (matrix[r][c]) {
                    ctx.fillRect(padding + c * pixSize, padding + r * pixSize, pixSize, pixSize);
                }
            }
        }
        return canvas;
    }

    return { toCanvas };
})();

const APP_DATABASE = {
    "throne": {
        name: "Throne", icon: "fa-solid fa-chess-rook", url: "https://github.com/throneproj/Throne/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Нажмите <b>«Получить доступ»</b> выше и скопируйте ссылку на подписку.</div>
                <div class="step-item">В клиенте нажмите <b>«Профили»</b> -> <b>«Добавить профиль из буфера обмена»</b>.</div>
                <div class="step-item">Выделите все профили (Ctrl+A), нажмите <b>«Профили»</b> -> <b>«Тест задержки (пинга)»</b>.</div>
                <div class="step-item">Дождитесь надписи <i>«Тест задержек завершён!»</i> в логах снизу.</div>
                <div class="step-item">Кликните по колонке <b>«Задержка (пинг)»</b> для сортировки от меньшего к большему.</div>
                <div class="step-item">Сверху установите галочку <b>«Режим TUN»</b> (важно для обхода DPI).</div>
                <div class="step-item">Выберите сервер с лучшим пингом -> Правая кнопка мыши -> <b>«Запустить»</b>.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Throne автоматически подбирает оптимальное ядро (Xray/sing-box). Для обхода жёсткого DPI вручную выберите <b>Xray-core</b> в настройках — он поддерживает Reality-обфускацию. Не забывайте обновлять ядро через встроенный менеджер: <b>«Настройки»</b> -> <b>«Обновление ядра»</b>.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>TUN не включается:</b> Запустите Throne от имени администратора. Проверьте, что другие VPN-клиенты (WireGuard, OpenVPN) полностью выключены.</li>
                    <li><b>Подписка не загружается:</b> Откройте ссылку подписки в браузере — если страница не грузится, проверьте интернет без VPN. Если грузится, попробуйте <b>«Добавить подписку по ссылке»</b> вместо буфера обмена.</li>
                    <li><b>Все узлы красные (нет связи):</b> Обновите geoip и geosite базы: <b>«Настройки»</b> -> <b>«Маршрутизация»</b> -> <b>«Обновить базы»</b>.</li>
                </ul>
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
                <div class="step-item">Выберите тип <b>«Подписка»</b> и вставьте вашу ссылку. Нажмите <b>«ОК»</b>.</div>
                <div class="step-item">Нажмите кнопку <b>«Обновить подписки»</b> (иконка облака со стрелкой).</div>
                <div class="step-item">Включите галочку <b>«Режим TUN»</b> (вкладка <b>«Параметры»</b> -> <b>«Настройки маршрутов»</b>) и запустите выбранный сервер.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> NekoBox поддерживает два ядра: <b>Xray</b> (лучше для Reality/обфускации) и <b>sing-box</b> (лучше для Hysteria2). Переключайте ядро в <b>«Настройки»</b> -> <b>«Основное ядро»</b>. Для максимальной производительности на слабых ПК используйте sing-box — он потребляет меньше ресурсов.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Подписка не обновляется:</b> Проверьте, что в поле URL нет лишних пробелов. Попробуйте обновить через меню <b>«Сервер»</b> -> <b>«Обновить все подписки»</b>.</li>
                    <li><b>Ошибка «Не удалось запустить ядро»:</b> Скачайте ядро вручную: <b>«Настройки»</b> -> <b>«Ядро»</b> -> <b>«Загрузить»</b>. Убедитесь, что антивирус не блокирует файл ядра.</li>
                    <li><b>Прокси работает только в браузере:</b> Убедитесь, что включён <b>«Режим TUN»</b>, а не просто «Системный прокси». TUN перенаправляет весь трафик системы.</li>
                </ul>
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
                <div class="step-item">Вставьте ссылку в поле <code>Url</code>, задайте <b>«Замечание»</b> (например, «Scarlet BS») и сохраните.</div>
                <div class="step-item">В главном меню нажмите <b>«Обновить подписку»</b> (или Ctrl+R).</div>
                <div class="step-item">Выделите сервер с хорошим пингом и нажмите <b>Enter</b> для подключения.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> В v2rayN обязательно включите <b>«Режим TUN»</b> (правый клик по иконке в трее -> <b>«Режим TUN»</b>). Это гарантирует, что весь системный трафик идёт через прокси, включая игры, мессенджеры и приложения Windows. Без TUN некоторые программы будут выходить в обход прокси.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>DNS-утечки:</b> В <b>«Настройки»</b> -> <b>«DNS»</b> включите <b>«Маршрутизировать DNS через прокси»</b>. Это предотвратит утечку запросов к провайдеру.</li>
                    <li><b>Подписка возвращает 0 узлов:</b> Проверьте ссылку в браузере — если она пуста, попробуйте другую подписку (MIX вместо БС). Некоторые подписки могут временно не иметь узлов нужного протокола.</li>
                    <li><b>Серверы не проходят тест пинга:</b> Убедитесь, что в <b>«Настройки»</b> -> <b>«Проверка»</b> выбран тип <b>«RealLatency»</b> (тест через HTTP), а не ICMP/TCP-пинг, который часто блокируется.</li>
                </ul>
            </div>
        `
    },
    "singbox": {
        name: "Sing-box UI", icon: "fa-solid fa-box", url: "https://github.com/Leadaxe/singbox-launcher/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">Запустите Singbox-launcher и перейдите во вкладку <b>«Профили»</b>.</div>
                <div class="step-item">Нажмите <b>«Добавить»</b> и вставьте вашу ссылку в поле URL.</div>
                <div class="step-item">Сделайте тест задержки: выделите узлы (Ctrl+A) и нажмите <b>«Тест»</b>.</div>
                <div class="step-item">Нажмите главную кнопку <b>▶ Старт</b> для активации туннеля.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Sing-box Launcher использует нативное ядро sing-box, которое быстрее Xray на слабых машинах. В настройках можно переключить режим на <b>«TUN»</b> (полный захват трафика) или <b>«Mixed»</b> (HTTP+SOCKS5 прокси для браузера). Для обхода DPI всегда выбирайте TUN.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Сервис не стартует (ошибка в логах):</b> Откройте консоль (вкладка <b>«Лог»</b>) — если видите <code>permission denied</code>, запустите лаунчер от имени администратора.</li>
                    <li><b>Узлы отображаются, но не работают:</b> Возможно, ядро sing-box устарело. Скачайте свежую версию с GitHub и замените файл в папке лаунчера.</li>
                    <li><b>Hysteria2 не подключается:</b> Проверьте, что порт в клиенте совпадает с портом в узле. Некоторые фаерволы блокируют UDP/QUIC — попробуйте переключиться на VLESS/TCP.</li>
                </ul>
            </div>
        `
    },
    "karing": {
        name: "Karing", icon: "fa-solid fa-paper-plane", url: "https://github.com/KaringX/karing/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку с нашего сайта.</div>
                <div class="step-item">Откройте приложение Karing и перейдите в раздел <b>«Profiles»</b> (Профили).</div>
                <div class="step-item">Нажмите на значок <b>«+»</b> и выберите <b>«Импорт из буфера обмена»</b>.</div>
                <div class="step-item">Запустите тест задержки: на главном экране нажмите <b>«Test Latency»</b> (значок таймера).</div>
                <div class="step-item">Выберите лучший сервер (зелёный индикатор) и сдвиньте переключатель подключения в положение <b>«Вкл»</b>.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Karing использует ядро Clash Meta, что даёт широкую совместимость. В разделе <b>«Settings»</b> -> <b>«Clash»</b> включите <b>«Unified Delay»</b> — это покажет реальную задержку через прокси, а не простой TCP-пинг. Для стриминга включите <b>«TUN Mode»</b> в основных настройках.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Все узлы показывают «Offline»:</b> Нажмите на подписку -> <b>«Update»</b> (обновить). Если не помогло, удалите подписку и добавьте заново через <b>«Import from URL»</b>.</li>
                    <li><b>Приложение вылетает на Android:</b> Отключите <b>«Battery Optimization»</b> (оптимизацию батареи) для Karing в настройках телефона. Агрессивная экономия энергии убивает фоновый процесс прокси.</li>
                    <li><b>Медленная скорость на ПК:</b> Проверьте, что в настройках профиля выбрано ядро <b>«mihomo»</b> (системное), а не встроенное — системное ядро работает быстрее.</li>
                </ul>
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
                <div class="step-item">Нажмите три точки (⋮) -> <b>«Проверка профилей группы»</b>.</div>
                <div class="step-item">Снова три точки -> <b>«Сортировка по результатам теста»</b>.</div>
                <div class="step-item">Выберите сервер с зелёным пингом и нажмите кнопку <b>▶️ (Старт)</b>.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> На Android обязательно отключите <b>оптимизацию батареи</b> для v2rayNG (Настройки телефона -> Приложения -> v2rayNG -> Батарея -> Без ограничений). Иначе система убьёт фоновый процесс VPN при выключенном экране, и соединение прервётся.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>VPN отключается при блокировке экрана:</b> Отключите оптимизацию батареи (см. совет выше). Также проверьте в настройках приложения: <b>«Настройки»</b> -> <b>«Локальный DNS»</b> -> включите <b>«Защита от разрыва»</b>.</li>
                    <li><b>Не отображаются узлы после импорта:</b> Проверьте формат ссылки — v2rayNG ожидает ссылку типа <code>https://...</code>, а не локальный файл. Скопируйте именно URL из модального окна.</li>
                    <li><b>Интернет не работает после подключения:</b> Откройте <b>«Настройки»</b> -> <b>«Прокси»</b> и убедитесь, что <b>«Перенаправлять весь трафик»</b> включено. Попробуйте другой узел — сервер мог упасть.</li>
                </ul>
            </div>
        `
    },
    "v2raytun": {
        name: "v2RayTun", icon: "fa-solid fa-rocket", url: "https://v2raytun.com/",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку с нашего сайта.</div>
                <div class="step-item">Откройте v2RayTun и перейдите в раздел <b>«Servers»</b> (Серверы).</div>
                <div class="step-item">Нажмите иконку <b>«+» (добавить)</b> -> выберите <b>«Import from Clipboard»</b>.</div>
                <div class="step-item">Нажмите на подписку и выберите <b>«Update Subscription»</b> для загрузки серверов.</div>
                <div class="step-item">Дождитесь завершения теста задержки, отсортируйте по пингу и нажмите кнопку <b>▶ Старт</b>.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> v2RayTun использует собственный TUN-драйвер, оптимизированный для Android. В настройках включите <b>«Bypass LAN»</b> (обход локальной сети), чтобы не терять доступ к роутеру и другим устройствам в домашней сети при активном VPN.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Не появляется запрос на VPN-разрешение:</b> Зайдите в Настройки Android -> <b>«Подключения»</b> -> <b>«VPN»</b> -> удалите старый профиль v2RayTun. Затем перезапустите приложение — диалог разрешения появится заново.</li>
                    <li><b>Подписка не обновляется (pending):</b> Проверьте стабильность интернета. Иногда v2RayTun требует ручного обновления: проведите вниз по экрану серверов для принудительного refresh.</li>
                    <li><b>Приложение зависает при запуске:</b> Очистите кэш приложения (Настройки -> Приложения -> v2RayTun -> Хранилище -> Очистить кэш). Переустановите, если проблема сохраняется.</li>
                </ul>
            </div>
        `
    },
    "v2box": {
        name: "V2Box", icon: "fa-brands fa-app-store-ios", url: "https://apps.apple.com/ru/app/v2box-v2ray-client/id6446814690",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку с нашего сайта.</div>
                <div class="step-item">Откройте V2Box, перейдите во вкладку <b>«Config»</b> (Конфигурации).</div>
                <div class="step-item">Нажмите на <b>«+»</b> -> <b>«Добавить подписку»</b>.</div>
                <div class="step-item">Вставьте ссылку в поле <code>URL</code>, введите Имя (например, «Scarlet») и сохраните.</div>
                <div class="step-item">Дождитесь проверки пинга, выберите сервер с зелёным индикатором и нажмите кнопку <b>«Подключиться»</b>.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> На iOS все VPN-клиенты ограничены системой — фоновая работа VPN может прерываться. В V2Box включите <b>«On Demand»</b> (Подключать по требованию) в настройках профиля. Это заставит iOS автоматически восстанавливать туннель при разрыве.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>VPN отключается в фоне (iOS):</b> iOS агрессивно управляет фоновыми процессами. Включите <b>«On Demand»</b> в настройках VPN-профиля (Настройки iOS -> VPN -> (i) -> Connect On Demand).</li>
                    <li><b>Серверы не проходят проверку:</b> V2Box может быть заблокирован в вашем регионе. Попробуйте установить приложение через смену региона Apple ID или используйте альтернативный клиент (Streisand, Shadowrocket).</li>
                    <li><b>Не копируется ссылка из браузера:</b> На iOS Safari иногда блокирует копирование длинных URL. Нажмите и удерживайте ссылку -> выберите <b>«Скопировать»</b>. Или откройте сайт в другом браузере (Chrome, Firefox).</li>
                </ul>
            </div>
        `
    },
    "shadowrocket": {
        name: "Shadowrocket", icon: "fa-solid fa-rocket", url: "https://apps.apple.com/us/app/shadowrocket/id932747118",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">Откройте Shadowrocket (приложение платное — ~$2.99, но стабильное и регулярно обновляется).</div>
                <div class="step-item">Нажмите <b>«+»</b> в правом верхнем углу, выберите тип <b>«Subscribe»</b>.</div>
                <div class="step-item">Вставьте ссылку в поле URL и нажмите <b>«Done»</b> (Готово).</div>
                <div class="step-item">Запустите <b>«Connectivity Test»</b> (Тест соединения), выберите сервер и включите переключатель VPN.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Shadowrocket поддерживает создание правил маршрутизации (Rule Sets). Настройте автоматический выбор: трафик к российским сайтам идёт напрямую, к зарубежным — через прокси. Вкладка <b>«Config»</b> -> <b>«Rule»</b> -> добавьте правило <code>GEOIP,RU,DIRECT</code> и <code>DOMAIN-SUFFIX,ru,DIRECT</code>.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Не устанавливается из App Store (РФ):</b> Приложение может быть скрыто в российском App Store. Смените регион Apple ID на другой (Казахстан, Турция) или используйте альтернативный аккаунт.</li>
                    <li><b>Серверы висят со статусом «Timeout»:</b> Отключите <b>«On Demand»</b> в настройках VPN-профиля iOS. Принудительно отключите и включите туннель переключателем на главном экране.</li>
                    <li><b>Прокси работает только в Safari:</b> В настройках Shadowrocket включите <b>«Global Routing»</b> (глобальная маршрутизация) вместо «Rule-based». Это направит весь трафик через прокси.</li>
                </ul>
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
                <div class="step-item">Выберите <b>«Add Subscription»</b> (Добавить подписку).</div>
                <div class="step-item">Вставьте ссылку в поле <code>URL</code>, дайте название и сохраните.</div>
                <div class="step-item">Зажмите палец на названии подписки и выберите <b>«Latency Test»</b>.</div>
                <div class="step-item">Выберите лучший узел (зелёный) и нажмите главную кнопку подключения.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Streisand — один из немногих iOS-клиентов с полной поддержкой Hysteria2 (QUIC). Для максимальной скорости на iOS выбирайте подписки с протоколом <b>Hysteria2</b> — они специально оптимизированы под мобильные сети с переменной задержкой.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Подписка не обновляется (висит «Updating...»):</b> Удалите подписку и добавьте заново. Убедитесь, что URL начинается с <code>https://</code>. HTTP-ссылки могут блокироваться провайдером.</li>
                    <li><b>Не удаётся установить из App Store (РФ):</b> Streisand недоступен в российском App Store. Создайте Apple ID другого региона (Казахстан, Армения) или установите через .ipa файл с помощью AltStore/SideStore.</li>
                    <li><b>Тест задержки не завершается:</b> Некоторые узлы могут виснуть на тесте. Проведите по экрану вниз для остановки теста и протестируйте только выбранные серверы — отключите лишние долгим нажатием -> <b>«Disable»</b>.</li>
                </ul>
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
                <div class="step-item"><b>Важно:</b> Перейдите в настройки профиля и установите <b>«Вариант маршрутизации»</b> на <b>«Обход Ирана»</b>. Для России этот режим также подходит — он оптимально обходит DPI.</div>
                <div class="step-item">Нажмите огромную круглую кнопку посередине экрана для запуска.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Hiddify поддерживает <b>Warp-интеграцию</b> (Cloudflare Warp поверх прокси). В настройках включите <b>«Использовать WARP»</b> — это добавит дополнительный слой шифрования и может улучшить скорость на слабых соединениях. Однако на некоторых сетях Warp сам блокируется — если скорость упала, отключите.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Не работает с российскими сайтами:</b> В настройках маршрутизации переключитесь с <b>«Обход Ирана»</b> на <b>«Свой вариант»</b> и добавьте правило: <code>DOMAIN-SUFFIX,ru,DIRECT</code>. Это направит российские сайты напрямую, а зарубежные — через прокси.</li>
                    <li><b>Приложение показывает «Нет соединения»:</b> Проверьте, не включён ли другой VPN на устройстве. iOS и Android не позволяют работать двум VPN-туннелям одновременно.</li>
                    <li><b>Прокси работает, но медленно:</b> Отключите <b>WARP</b> в настройках, если он включён. Попробуйте выбрать другой протокол в настройках профиля (VLESS Reality вместо Hysteria2).</li>
                </ul>
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
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> FlClash — это современный Clash Meta клиент с красивым Material You дизайном. В настройках включите <b>«TUN Mode»</b> для захвата всего трафика устройства. Для экономии батареи на телефоне используйте <b>«Rule Mode»</b> — трафик российских сайтов пойдёт напрямую, экономя заряд и трафик прокси.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Ошибка парсинга конфигурации:</b> FlClash ожидает Clash-формат подписки. Наши подписки отдаются в base64-формате, совместимом с Clash. Если ошибка повторяется, попробуйте подписку MIX (содержит все протоколы в одном файле).</li>
                    <li><b>Приложение не видит интернет при активном VPN:</b> Перейдите в <b>«Settings»</b> -> <b>«DNS»</b> и включите <b>«Fake-IP»</b> режим. Это решит большинство проблем с DNS-резолвингом.</li>
                    <li><b>Android TV: пульт не работает с приложением:</b> FlClash на TV может требовать мышь для навигации. Используйте FlClash в связке с кнопкой «Настройки» на пульте для переключения между элементами интерфейса.</li>
                </ul>
            </div>
        `
    },
    "mihomo": {
        name: "Mihomo (Clash Meta)", icon: "fa-solid fa-layer-group", url: "https://github.com/MetaCubeX/mihomo/releases/latest",
        protocols: ['vless','vmess','trojan','ss','hysteria2'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В веб-интерфейсе (<b>metacubexd</b> или <b>yacd</b>) перейдите в раздел <b>«Profiles»</b>.</div>
                <div class="step-item">Нажмите <b>«New Profile»</b>, вставьте URL подписки и нажмите <b>«Download»</b>.</div>
                <div class="step-item">На вкладке <b>«Proxies»</b> выберите узел с низкой задержкой (зелёный индикатор).</div>
                <div class="step-item">Включите <b>«System Proxy»</b> или TUN-режим для перенаправления всего трафика.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Mihomo — это ядро (backend), которому нужен веб-интерфейс. Самый популярный dashboard — <b>metacubexd</b> (MetaCubeX Dashboard). Откройте <code>http://127.0.0.1:9090/ui</code> в браузере после запуска mihomo. Для автозапуска на Windows настройте сервис через <code>nssm</code> или используйте готовый Mihomo Party (GUI-обёртку).
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Dashboard не открывается (localhost:9090):</b> Проверьте, что mihomo запущен. В Windows проверьте в Диспетчере задач наличие процесса <code>mihomo.exe</code>. В Linux: выполните <code>systemctl status mihomo</code>.</li>
                    <li><b>TUN-режим не работает:</b> На Windows TUN требует установки Wintun-драйвера. Скачайте <code>wintun.dll</code> с официального сайта и поместите в папку с mihomo.exe. Запустите от администратора.</li>
                    <li><b>Подписка не загружается (Connection Refused):</b> Если вы за прокси или корпоративным фаерволом, mihomo не может соединиться с интернетом. Добавьте прокси в настройки: <code>external-controller: 0.0.0.0:9090</code> в config.yaml.</li>
                </ul>
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
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> AmneziaWG использует модифицированный WireGuard с обфускацией. <b>Маскировка трафика</b> делает ваш WireGuard-трафик неотличимым от обычного HTTPS (TLS), обходя DPI-блокировки. Если провайдер блокирует стандартный WireGuard, включите маскировку и выберите протокол <b>«HTTPS/TLS»</b>.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Очень низкая скорость:</b> Обфускация добавляет накладные расходы ~10-15% к скорости. Если скорость критична, отключите маскировку в настройках (но тогда WireGuard может быть обнаружен и заблокирован провайдером).</li>
                    <li><b>Не подключается (Handshake failed):</b> Проверьте правильность ключей в конфигурации. Amnezia требует специфичный формат конфига — убедитесь, что вы импортировали готовый конфигурационный файл, а не ссылку на подписку.</li>
                    <li><b>Приложение конфликтует с другим VPN:</b> Amnezia и другие VPN-клиенты не могут работать одновременно. Полностью отключите все остальные VPN перед запуском Amnezia.</li>
                </ul>
            </div>
        `
    },
    "sagernet": {
        name: "SagerNet", icon: "fa-solid fa-code-branch", url: "https://github.com/SagerNet/SagerNet/releases/latest",
        protocols: ['vless','vmess','trojan','ss'],
        guide: `
            <div class="step-list">
                <div class="step-item">Скопируйте ссылку на подписку.</div>
                <div class="step-item">В SagerNet откройте боковое меню (свайп вправо) и нажмите <b>«Manage Subscriptions»</b>.</div>
                <div class="step-item">Нажмите <b>«+»</b>, вставьте URL подписки и нажмите <b>«OK»</b>.</div>
                <div class="step-item">Нажмите на подписку для обновления списка серверов, затем выполните <b>«URL Test»</b>.</div>
                <div class="step-item">Выберите узел с наименьшей задержкой и нажмите кнопку подключения внизу экрана.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> SagerNet — это форк v2rayNG с расширенной маршрутизацией и поддержкой прокси-цепочек (proxy chains). Для тонкой настройки откройте <b>«Route Settings»</b> и создайте правило: локальные/российские сайты — напрямую (DIRECT), зарубежные — через выбранный прокси. Это экономит трафик и снижает задержку на российских ресурсах.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Прокси-цепочка (chain) не работает:</b> Убедитесь, что оба прокси в цепочке живы. Протестируйте каждый по отдельности перед объединением в цепочку. Некоторые протоколы (Hysteria2) не поддерживают цепочки.</li>
                    <li><b>Приложение вылетает при импорте:</b> Очистите данные приложения: Настройки Android -> Приложения -> SagerNet -> Хранилище -> <b>«Очистить данные»</b>. Переустановите, если проблема остаётся.</li>
                    <li><b>Высокий расход батареи:</b> SagerNet может потреблять больше батареи, чем v2rayNG, из-за расширенной маршрутизации. Отключите неиспользуемые функции в <b>«Experimental Settings»</b>.</li>
                </ul>
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
                <div class="step-item">Обновите подписку (потяните вниз или нажмите кнопку обновления) и дождитесь загрузки узлов.</div>
                <div class="step-item">Выберите сервер с лучшим пингом и нажмите кнопку подключения в центре экрана.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> FoXray использует оригинальное ядро Xray, обеспечивая полную поддержку Reality и XTLS-Vision. В настройках подписки включите <b>«Автообновление»</b> с интервалом 4-6 часов — это критически важно, поскольку публичные узлы часто меняют IP, и без автообновления ваш список серверов устареет за сутки.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Connection timeout на всех узлах:</b> Проверьте, не блокирует ли ваш провайдер порты. Попробуйте узлы на портах 443/8443 (стандартные HTTPS-порты) — они реже блокируются. В FoXray отфильтруйте узлы по порту в настройках отображения.</li>
                    <li><b>Reality-узлы не работают:</b> Reality требует точного совпадения <code>serverName</code> (публичного ключа) на клиенте и сервере. Убедитесь, что вы не редактировали конфигурацию узла после импорта.</li>
                    <li><b>Приложение не запускается на Android 14+:</b> Android 14 ужесточил требования к фоновым процессам. Установите FoXray из GitHub Releases (а не из магазина приложений), чтобы получить версию с обходом ограничений.</li>
                </ul>
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
                <div class="step-item">После загрузки нажмите <b>«Setup»</b> и выберите политику маршрутизации (Rule — для выборочного прокси, Global — для всего трафика).</div>
                <div class="step-item">Запустите туннель кнопкой <b>«Start»</b> на главном экране.</div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Surge — самый мощный, но платный прокси-клиент для Apple-экосистемы (~$49.99, разовая покупка). Он поддерживает создание сложных Rulesets (наборов правил) для гибкой маршрутизации. Настройте автоматический failover: если основной узел падает, Surge автоматически переключится на резервный.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Прокси работает, но YouTube не грузится:</b> Настройте правило для Google-сервисов идти через прокси: <b>«Rule»</b> -> добавьте <code>DOMAIN-SUFFIX,googlevideo.com,PROXY</code> и <code>DOMAIN-SUFFIX,ytimg.com,PROXY</code>.</li>
                    <li><b>Высокий расход батареи на iPhone:</b> В настройках Surge уменьшите частоту обновления статистики и отключите <b>«Always-On»</b> в профиле VPN. Используйте Rule-режим вместо Global.</li>
                    <li><b>Не удаётся купить Surge из РФ:</b> Surge продаётся только через App Store (недоступен в РФ). Приобретите через Apple ID другого региона или используйте подарочную карту App Store.</li>
                </ul>
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
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Stash — это Clash-совместимый клиент для iOS на базе mihomo (Clash Meta). Он поддерживает все возможности Clash: прокси-группы, авто-выбор (URL-Test), failover. Настройте группу <b>«Auto Select»</b> — Stash будет автоматически выбирать самый быстрый узел из группы, избавляя вас от ручного перебора.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Высокое потребление памяти (iOS):</b> Stash на старых устройствах может использовать много RAM. Уменьшите количество одновременно активных узлов: оставьте только 20-30 лучших, удалив остальные из подписки.</li>
                    <li><b>Некоторые узлы не отображаются:</b> Stash может не поддерживать редкие типы узлов (например, SSH или HTTP-прокси). Убедитесь, что ваша подписка содержит только поддерживаемые протоколы (VLESS, VMess, Trojan, SS, Hysteria2).</li>
                    <li><b>Прокси работает, но приложения не видят интернет:</b> Проверьте правило маршрутизации: в <b>«Rules»</b> должно быть <code>MATCH,PROXY</code> для перенаправления всего неопознанного трафика через прокси.</li>
                </ul>
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
                <div class="step-item">Поместите <code>config.json</code> в <code>/etc/sing-box/</code> (Linux/Mac) или в папку с бинарником (Windows).</div>
                <div class="step-item">Запустите: <code>sudo sing-box run -c config.json</code> (Linux/Mac) или <code>sing-box.exe run -c config.json</code> (Windows, от админа).</div>
                <div class="step-item">Проверьте работу: <code>curl --proxy http://127.0.0.1:2080 https://www.google.com</code></div>
            </div>
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> Для продакшен-использования настройте sing-box как системный сервис. На Linux создайте systemd-unit: <code>sudo systemctl enable sing-box</code>. На Windows используйте <code>nssm install sing-box</code>. Это обеспечит автозапуск при старте системы и автоматический перезапуск при падении.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Permission denied при запуске:</b> На Linux/Mac требуется <code>sudo</code> для TUN-режима. Если TUN не нужен, используйте режим <code>mixed</code> (HTTP+SOCKS5 прокси без TUN): он не требует прав root.</li>
                    <li><b>Ошибка в config.json:</b> Проверьте валидность JSON: <code>sing-box check -c config.json</code>. Синтаксические ошибки в конфиге — частая причина отказа при запуске.</li>
                    <li><b>Прокси работает, но DNS не резолвится:</b> Проверьте секцию <code>"dns"</code> в config.json. Добавьте публичные DNS-серверы: <code>"servers": [{"tag": "dns-remote", "address": "https://dns.quad9.net/dns-query"}]</code>.</li>
                </ul>
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
            <div class="guide-config">
                <div class="guide-config-label"><i class="fa-solid fa-clipboard"></i> Конфигурация WireGuard (RouterOS CLI)</div>
                <pre>/interface wireguard add name=wg-scarlet private-key="YOUR_PRIVATE_KEY" listen-port=13231
            /interface wireguard peers add interface=wg-scarlet public-key="SERVER_PUBLIC_KEY" endpoint-address=SERVER_IP endpoint-port=443 allowed-address=0.0.0.0/0
            /ip address add address=10.0.0.2/24 interface=wg-scarlet
            /ip route add dst-address=0.0.0.0/0 gateway=wg-scarlet</pre>
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Туннель поднимается, но нет трафика:</b> Проверьте маршрут: <code>/ip route print</code>. VPN-маршрут должен иметь меньшую дистанцию (distance), чем основной шлюз провайдера.</li>
                    <li><b>SSTP ругается на сертификат:</b> Многие SSTP-серверы используют самоподписанные сертификаты. Включите опцию <b>«Verify Certificate» = no</b> в настройках SSTC-клиента.</li>
                    <li><b>VPN падает при смене IP провайдером:</b> Настройте скрипт в RouterOS для автоматического переподключения: <code>/system scheduler add interval=5m on-event="/interface sstp-client print"</code>.</li>
                </ul>
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
            <div class="guide-config">
                <div class="guide-config-label"><i class="fa-solid fa-clipboard"></i> Установка OpenClash (альтернативный метод)</div>
                <pre>opkg update
            opkg install dnsmasq-full ipset iptables-nft
            # Скачайте последний OpenClash с GitHub:
            wget https://github.com/vernesong/OpenClash/releases/latest/download/luci-app-openclash_all.ipk
            opkg install luci-app-openclash_all.ipk
            # После установки откройте LuCI -> Services -> OpenClash
            # Добавьте ссылку на подписку в Profiles -> Add</pre>
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>Не хватает памяти для установки пакетов:</b> Многие роутеры имеют всего 8-16MB flash. Используйте <b>extroot</b> (перенос корня на USB-флешку) или установите минимальную версию sing-box без лишних зависимостей.</li>
                    <li><b>PassWall не видит интерфейс после перезагрузки:</b> Убедитесь, что сервис добавлен в автозапуск: <code>/etc/init.d/passwall enable</code> и <code>/etc/init.d/sing-box enable</code>.</li>
                    <li><b>DNS-утечки через провайдера:</b> В настройках PassWall включите <b>«DNS Forwarding»</b> и выберите DoH-сервер (Quad9 или Cloudflare) вместо DNS провайдера.</li>
                </ul>
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
            <div class="guide-tip">
                <i class="fa-solid fa-lightbulb"></i> <b>Совет:</b> NekoRay позволяет гибко выбирать ядро для каждого профиля (Xray или sing-box). Для VLESS Reality всегда используйте <b>Xray-core</b> — только оно поддерживает полную обфускацию. Для Hysteria2 переключитесь на <b>sing-box</b>. Настройка ядра: правый клик по профилю -> <b>«Редактировать»</b> -> <b>«Ядро»</b>.
            </div>
            <div class="guide-troubleshoot">
                <i class="fa-solid fa-wrench"></i> <b>Решение проблем:</b>
                <ul>
                    <li><b>GUI не запускается (чёрный экран):</b> NekoRay использует Qt-фреймворк. На Linux установите зависимости: <code>sudo apt install qt6-base-dev libqt6svg6</code>. На Windows установите Visual C++ Redistributable.</li>
                    <li><b>Тест скорости зависает на первом узле:</b> Некоторые серверы могут «вешать» тест. Выделите узлы по одному (щёлкая с Shift) для тестирования подмножеств. Исключите проблемные узлы из теста.</li>
                    <li><b>Sing-box ядро не устанавливается автоматически:</b> Скачайте sing-box бинарник вручную и поместите в папку <code>nekoray/core/</code>. В настройках NekoRay укажите путь к ядру: <b>«Программа»</b> -> <b>«Настройки»</b> -> <b>«Основное ядро»</b>.</li>
                </ul>
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

// Platform display metadata for the setup wizard (US-W10)
const PLATFORM_META = {
    windows:   { label: 'Windows',    icon: 'fa-brands fa-windows' },
    android:   { label: 'Android',    icon: 'fa-brands fa-android' },
    androidtv: { label: 'Android TV', icon: 'fa-solid fa-tv' },
    ios:       { label: 'iOS',        icon: 'fa-brands fa-apple' },
    mac:       { label: 'macOS',      icon: 'fa-solid fa-laptop' },
    linux:     { label: 'Linux',      icon: 'fa-brands fa-linux' },
    router:    { label: 'Роутер',     icon: 'fa-solid fa-wifi' }
};

let currentPlatform = 'windows';
let currentAppId = PLATFORMS['windows'][0];

function init() {
    const ua = navigator.userAgent.toLowerCase();
    if (ua.includes("android") && ua.includes("tv")) currentPlatform = 'androidtv';
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
    initMobileNav();
    initLocalTime();
    initAccessibility();
    initFXControl();
    initTypewriter();
    initStarDust();
    initStats();
    initOnboarding();
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
    const mobileLinks = document.querySelectorAll('.mobile-nav-link');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const currentId = entry.target.getAttribute('id');
                navBtns.forEach(btn => {
                    btn.classList.toggle('active', btn.getAttribute('data-target') === currentId);
                });
                mobileLinks.forEach(link => {
                    link.classList.toggle('active', link.getAttribute('data-target') === currentId);
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

function openModal(id) {
    document.getElementById(id).classList.add('active');
    if (id === 'configs-modal') {
        switchConfigTab('class');
    }
}
function closeModal(id) {
    document.getElementById(id).classList.remove('active');
    // Hide QR display when closing configs modal
    const qrDiv = document.getElementById('qr-display');
    if (qrDiv) qrDiv.classList.remove('active');
    const tabContents = document.querySelectorAll('.config-tab-content');
    tabContents.forEach(tc => tc.style.display = '');
}

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const activeModals = document.querySelectorAll('.modal-overlay.active');
        activeModals.forEach(m => closeModal(m.id));
    }
});

// Close modal on overlay click
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay') && e.target.classList.contains('active')) {
        closeModal(e.target.id);
    }
});

function acceptRules() {
    closeModal('rules-modal');
    setTimeout(() => openModal('configs-modal'), 300);
}

// --- SETUP WIZARD (US-W10) ---
let wizardStep = 1;
let wizardPlatform = null;
let wizardAppId = null;

function openWizard() {
    // Restore remembered platform choice
    wizardPlatform = null;
    try {
        const saved = localStorage.getItem('sd_wizard_platform');
        if (saved && PLATFORMS[saved]) wizardPlatform = saved;
    } catch (e) {}

    buildWizardPlatforms();
    if (wizardPlatform) {
        wizardAppId = PLATFORMS[wizardPlatform][0];
        buildWizardApps();
    }
    goWizardStep(1);
    openModal('wizard-modal');
    dismissOnboarding();
}

function makeWizardCard(icon, label, selected, ariaPrefix, onSelect) {
    const div = document.createElement('div');
    div.className = 'app-card' + (selected ? ' selected' : '');
    div.setAttribute('role', 'button');
    div.setAttribute('tabindex', '0');
    div.setAttribute('aria-label', ariaPrefix + ' ' + label);
    div.innerHTML = '<i class="' + icon + ' app-icon"></i><div class="app-name">' + label + '</div>';
    div.onclick = onSelect;
    div.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); div.click(); }
    });
    return div;
}

function buildWizardPlatforms() {
    const grid = document.getElementById('wizard-platform-grid');
    if (!grid) return;
    grid.innerHTML = '';
    Object.keys(PLATFORM_META).forEach(function (pid) {
        const meta = PLATFORM_META[pid];
        grid.appendChild(makeWizardCard(meta.icon, meta.label, pid === wizardPlatform, 'Платформа', function () {
            wizardSelectPlatform(pid);
        }));
    });
}

function wizardSelectPlatform(pid) {
    wizardPlatform = pid;
    wizardAppId = PLATFORMS[pid][0];
    try { localStorage.setItem('sd_wizard_platform', pid); } catch (e) {}
    buildWizardPlatforms();
    buildWizardApps();
    goWizardStep(2);
}

function buildWizardApps() {
    const grid = document.getElementById('wizard-app-grid');
    const nameEl = document.getElementById('wizard-platform-name');
    if (nameEl && wizardPlatform) nameEl.textContent = PLATFORM_META[wizardPlatform].label;
    if (!grid || !wizardPlatform) return;
    grid.innerHTML = '';
    PLATFORMS[wizardPlatform].forEach(function (appId) {
        const app = APP_DATABASE[appId];
        grid.appendChild(makeWizardCard(app.icon, app.name, appId === wizardAppId, 'Клиент', function () {
            wizardSelectApp(appId);
        }));
    });
}

function wizardSelectApp(appId) {
    wizardAppId = appId;
    buildWizardApps();
    buildWizardFinal();
    goWizardStep(3);
}

function buildWizardFinal() {
    const app = APP_DATABASE[wizardAppId];
    if (!app) return;
    const icon = document.getElementById('wizard-final-icon');
    if (icon) icon.className = app.icon;
    const nm = document.getElementById('wizard-final-name');
    if (nm) nm.textContent = app.name;
    const dl = document.getElementById('wizard-final-dl');
    if (dl) dl.textContent = app.name;
    const btn = document.getElementById('wizard-download-btn');
    if (btn) btn.href = app.url;
    const guide = document.getElementById('wizard-guide');
    if (guide) guide.innerHTML = app.guide;
    const protos = document.getElementById('wizard-final-protos');
    if (protos) {
        protos.innerHTML = (app.protocols || []).map(function (p) {
            return '<span class="proto-tag">' + p.toUpperCase() + '</span>';
        }).join('');
    }
}

function goWizardStep(step) {
    wizardStep = step;
    for (let i = 1; i <= 3; i++) {
        const pane = document.getElementById('wizard-pane-' + i);
        if (pane) pane.style.display = (i === step) ? '' : 'none';
    }
    document.querySelectorAll('.wizard-step-dot').forEach(function (dot) {
        const s = parseInt(dot.getAttribute('data-step'));
        dot.classList.toggle('active', s === step);
        dot.classList.toggle('done', s < step);
    });
    const ptext = document.getElementById('wizard-progress-text');
    if (ptext) ptext.textContent = 'Шаг ' + step + '/3';

    const back = document.getElementById('wizard-back-btn');
    if (back) back.style.display = (step > 1) ? '' : 'none';
    const finish = document.getElementById('wizard-finish-btn');
    if (finish) finish.style.display = (step === 3) ? '' : 'none';

    const body = document.querySelector('#wizard-modal .modal-body');
    if (body) body.scrollTop = 0;
}

function wizardBack() {
    if (wizardStep > 1) goWizardStep(wizardStep - 1);
}

function wizardFinish() {
    // Sync the main guide UI to the wizard's choice for consistency
    if (wizardPlatform && wizardAppId) {
        currentPlatform = wizardPlatform;
        currentAppId = wizardAppId;
        updateUI();
    }
    closeModal('wizard-modal');
    setTimeout(function () { openModal('configs-modal'); }, 300);
}

// --- ONBOARDING (learning mode tooltip on first visit) ---
function initOnboarding() {
    let visited = false;
    try { visited = localStorage.getItem('sd_visited') === '1'; } catch (e) {}
    if (visited) return;

    const bubble = document.getElementById('wizard-hint-bubble');
    const btn = document.querySelector('.btn-wizard');
    if (bubble) {
        // Reveal after the hero animation settles
        setTimeout(function () { bubble.classList.add('show'); }, 1500);
        setTimeout(dismissOnboarding, 14000);
    }
    if (btn) btn.classList.add('pulse-hint');
}

function dismissOnboarding() {
    try { localStorage.setItem('sd_visited', '1'); } catch (e) {}
    const bubble = document.getElementById('wizard-hint-bubble');
    if (bubble) bubble.classList.remove('show');
    const btn = document.querySelector('.btn-wizard');
    if (btn) btn.classList.remove('pulse-hint');
}

function switchConfigTab(tab) {
    document.querySelectorAll('.config-tab-btn').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(`config-tab-${tab}`);
    if (activeBtn) activeBtn.classList.add('active');

    document.querySelectorAll('.config-tab-content').forEach(ct => ct.style.display = 'none');
    const activeContent = document.getElementById(`config-tab-${tab}-content`);
    if (activeContent) activeContent.style.display = '';

    // Hide QR display when switching tabs
    const qrDiv = document.getElementById('qr-display');
    if (qrDiv) qrDiv.classList.remove('active');
}

function copySub(path, name) {
    const fullUrl = BASE_URL + path;
    const doCopy = function(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }
        // Fallback: execCommand
        return new Promise(function(resolve, reject) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.left = '-9999px';
            textarea.style.top = '-9999px';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            try {
                const ok = document.execCommand('copy');
                document.body.removeChild(textarea);
                if (ok) resolve();
                else reject(new Error('execCommand failed'));
            } catch (e) {
                document.body.removeChild(textarea);
                reject(e);
            }
        });
    };

    doCopy(fullUrl).then(function() {
        closeModal('configs-modal');
        var toast = document.getElementById('toast');
        document.getElementById('toast-text').innerText = 'Спелл-карта [' + name + '] скопирована!';
        toast.classList.add('show');
        setTimeout(function() { toast.classList.remove('show'); }, 3500);
    }).catch(function() {
        // Last resort: show URL in a prompt
        var toast = document.getElementById('toast');
        document.getElementById('toast-text').innerText = 'URL: ' + fullUrl;
        toast.classList.add('show');
        setTimeout(function() { toast.classList.remove('show'); }, 8000);
        prompt('Скопируйте ссылку вручную (Ctrl+C):', fullUrl);
    });
}

function showQR(path, name) {
    const fullUrl = BASE_URL + path;
    const qrDisplay = document.getElementById('qr-display');
    const qrLabel = document.getElementById('qr-label');
    const qrContainer = document.getElementById('qr-container');

    qrLabel.innerText = name;
    qrContainer.innerHTML = '';

    try {
        const canvas = QR.toCanvas(fullUrl, 5);
        canvas.style.maxWidth = '100%';
        canvas.style.height = 'auto';
        qrContainer.appendChild(canvas);
    } catch (e) {
        qrContainer.innerHTML = '<p style="color: var(--touhou-red);">Ошибка генерации QR-кода</p>';
    }

    // Hide tab contents, show QR display
    document.querySelectorAll('.config-tab-content').forEach(function(ct) { ct.style.display = 'none'; });
    document.querySelectorAll('.config-tab-btn').forEach(function(btn) { btn.style.pointerEvents = 'none'; btn.style.opacity = '0.4'; });
    qrDisplay.classList.add('active');
}

function hideQR() {
    const qrDisplay = document.getElementById('qr-display');
    qrDisplay.classList.remove('active');
    document.querySelectorAll('.config-tab-btn').forEach(function(btn) { btn.style.pointerEvents = ''; btn.style.opacity = ''; });
    // Re-show current active tab content
    var activeTab = document.querySelector('.config-tab-btn.active');
    if (activeTab) {
        var tabName = activeTab.id.replace('config-tab-', '');
        var content = document.getElementById('config-tab-' + tabName + '-content');
        if (content) content.style.display = '';
    }
}

// --- FUN PANEL EFFECTS (TOUHOU EASTER EGGS) ---
function initFunPanel() {
    const btnMist = document.getElementById('btn-mist');
    const btnDanmaku = document.getElementById('btn-danmaku');
    const btnBats = document.getElementById('btn-bats');
    const btnScanline = document.getElementById('btn-scanline');
    const btnStardust = document.getElementById('btn-stardust');

    const mistLayer = document.getElementById('mist-layer');
    const scanlineOverlay = document.getElementById('scanline-overlay');
    const stardustCanvas = document.getElementById('stardust-canvas');

    let danmakuInterval = null;
    let batsInterval = null;

    // Restore saved effect states
    try {
        const savedFX = JSON.parse(localStorage.getItem('sd_fx_states') || '{}');
        if (savedFX.mist) { btnMist.classList.add('active'); mistLayer.classList.add('active'); }
        if (savedFX.danmaku) startDanmaku();
        if (savedFX.bats) startBats();
        if (savedFX.scanline) { btnScanline.classList.add('active'); scanlineOverlay.classList.add('active'); }
        if (savedFX.stardust) { btnStardust.classList.add('active'); stardustCanvas.classList.add('active'); startStardust(); }
    } catch(e) {}

    function saveFXStates() {
        try {
            localStorage.setItem('sd_fx_states', JSON.stringify({
                mist: btnMist.classList.contains('active'),
                danmaku: btnDanmaku.classList.contains('active'),
                bats: btnBats.classList.contains('active'),
                scanline: btnScanline.classList.contains('active'),
                stardust: btnStardust.classList.contains('active')
            }));
        } catch(e) {}
    }

    btnMist.addEventListener('click', () => {
        btnMist.classList.toggle('active');
        mistLayer.classList.toggle('active');
        saveFXStates();
    });

    const mistParticleInterval = { ref: null };
    function startMistParticles() {
        if (mistParticleInterval.ref) return;
        mistParticleInterval.ref = setInterval(() => {
            if (!mistLayer.classList.contains('active')) return;
            const p = document.createElement('div');
            p.className = 'mist-particle';
            const size = Math.random() * 80 + 30;
            p.style.width = size + 'px';
            p.style.height = size + 'px';
            p.style.left = Math.random() * 100 + 'vw';
            p.style.bottom = '-10px';
            p.style.setProperty('--px', (Math.random() * 60 - 30) + 'px');
            p.style.animationDuration = (Math.random() * 6 + 4) + 's';
            document.body.appendChild(p);
            setTimeout(() => p.remove(), 11000);
        }, 600);
    }
    // Observe mist for extreme mode particle spawning
    const mistObserver = new MutationObserver(() => {
        if (mistLayer.classList.contains('active') && document.body.classList.contains('fx-extreme')) {
            startMistParticles();
        } else {
            if (mistParticleInterval.ref) { clearInterval(mistParticleInterval.ref); mistParticleInterval.ref = null; }
        }
    });
    mistObserver.observe(mistLayer, { attributes: true, attributeFilter: ['class'] });
    // Also observe body for fx class changes
    const bodyObserver = new MutationObserver(() => {
        if (mistLayer.classList.contains('active') && document.body.classList.contains('fx-extreme')) {
            startMistParticles();
        } else if (!document.body.classList.contains('fx-extreme')) {
            if (mistParticleInterval.ref) { clearInterval(mistParticleInterval.ref); mistParticleInterval.ref = null; }
        }
    });
    bodyObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });

    function startDanmaku() {
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
    function stopDanmaku() {
        if (danmakuInterval) { clearInterval(danmakuInterval); danmakuInterval = null; }
        btnDanmaku.classList.remove('active');
    }
    btnDanmaku.addEventListener('click', () => {
        if (danmakuInterval) { stopDanmaku(); } else { startDanmaku(); }
        saveFXStates();
    });

    function startBats() {
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
    function stopBats() {
        if (batsInterval) { clearInterval(batsInterval); batsInterval = null; }
        btnBats.classList.remove('active');
    }
    btnBats.addEventListener('click', () => {
        if (batsInterval) { stopBats(); } else { startBats(); }
        saveFXStates();
    });

    // Scanline toggle
    btnScanline.addEventListener('click', () => {
        btnScanline.classList.toggle('active');
        scanlineOverlay.classList.toggle('active');
        saveFXStates();
    });

    // Stardust toggle
    btnStardust.addEventListener('click', () => {
        btnStardust.classList.toggle('active');
        stardustCanvas.classList.toggle('active');
        if (stardustCanvas.classList.contains('active')) {
            startStardust();
        } else {
            stopStardust();
        }
        saveFXStates();
    });
}

// --- MOBILE NAVIGATION ---
function initMobileNav() {
    const hamburger = document.getElementById('hamburger-btn');
    const overlay = document.getElementById('mobile-nav-overlay');
    const closeBtn = document.getElementById('mobile-nav-close');
    if (!hamburger || !overlay || !closeBtn) return;

    function openMobileNav() {
        hamburger.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        // Mirror active state from desktop nav
        const activeDesktopBtn = document.querySelector('.nav-btn.active');
        if (activeDesktopBtn) {
            const target = activeDesktopBtn.getAttribute('data-target');
            document.querySelectorAll('.mobile-nav-link').forEach(link => {
                link.classList.toggle('active', link.getAttribute('data-target') === target);
            });
        }
    }

    function closeMobileNav() {
        hamburger.classList.remove('active');
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    hamburger.addEventListener('click', openMobileNav);
    closeBtn.addEventListener('click', closeMobileNav);
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeMobileNav();
    });

    // Nav link clicks
    document.querySelectorAll('.mobile-nav-link').forEach(link => {
        link.addEventListener('click', function() {
            const targetId = this.getAttribute('data-target');
            const target = document.getElementById(targetId);
            if (target) target.scrollIntoView({ behavior: 'smooth' });
            closeMobileNav();
        });
    });

    // Sync mobile fun buttons with desktop fun buttons
    const mobileFunBtns = {
        'btn-mist-mobile': 'btn-mist',
        'btn-danmaku-mobile': 'btn-danmaku',
        'btn-bats-mobile': 'btn-bats',
        'btn-scanline-mobile': 'btn-scanline',
        'btn-stardust-mobile': 'btn-stardust'
    };
    Object.entries(mobileFunBtns).forEach(function([mobileId, desktopId]) {
        const mobileBtn = document.getElementById(mobileId);
        const desktopBtn = document.getElementById(desktopId);
        if (mobileBtn && desktopBtn) {
            mobileBtn.addEventListener('click', function() {
                desktopBtn.click();
                // Reflect state
                mobileBtn.classList.toggle('active', desktopBtn.classList.contains('active'));
            });
        }
    });
}

// --- LOCAL TIME CONVERSION ---
function initLocalTime() {
    const timeEl = document.querySelector('.sys-log-time');
    if (!timeEl) return;
    const utcAttr = timeEl.getAttribute('data-utc');
    if (!utcAttr) return;
    try {
        const date = new Date(utcAttr);
        if (isNaN(date.getTime())) return;
        const opts = { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' };
        const localStr = date.toLocaleString('ru-RU', opts);
        const tz = date.toLocaleString('ru-RU', { timeZoneName: 'short' }).split(' ').pop();
        timeEl.textContent = localStr + ' ' + tz;
        timeEl.style.color = 'var(--cyber-green)';
    } catch(e) {
        // Leave server time as fallback
    }
}

// --- ACCESSIBILITY ENHANCEMENTS ---
function initAccessibility() {
    // Add aria-labels and keyboard support to dynamically generated app cards
    const appGrid = document.getElementById('app-grid');
    if (!appGrid) return;
    const observer = new MutationObserver(function() {
        document.querySelectorAll('.app-card').forEach(function(card) {
            if (card.hasAttribute('aria-label')) return;
            var nameEl = card.querySelector('.app-name');
            if (nameEl) {
                card.setAttribute('aria-label', 'Выбрать клиент ' + nameEl.textContent);
                card.setAttribute('role', 'button');
                card.setAttribute('tabindex', '0');
                card.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        card.click();
                    }
                });
            }
        });
    });
    observer.observe(appGrid, { childList: true, subtree: true });
}

// --- EFFECT INTENSITY CONTROL (Minimal / Normal / Extreme) ---
function initFXControl() {
    const toggle = document.getElementById('fx-toggle');
    if (!toggle) return;

    const levels = ['M', 'N', 'E'];
    const classes = ['fx-minimal', '', 'fx-extreme'];
    const titles = ['Minimal — базовые эффекты', 'Normal — стандартные эффекты', 'Extreme — максимальные эффекты'];
    const labels = ['Min', 'Norm', 'Ext'];

    // Restore saved intensity
    let idx = 1; // default: Normal
    try {
        const saved = parseInt(localStorage.getItem('sd_fx_intensity'));
        if (!isNaN(saved) && saved >= 0 && saved <= 2) idx = saved;
    } catch(e) {}

    function applyIntensity(i) {
        // Remove all fx classes
        document.body.classList.remove('fx-minimal', 'fx-extreme');
        if (classes[i]) document.body.classList.add(classes[i]);
        toggle.textContent = levels[i];
        toggle.title = titles[i];
        try { localStorage.setItem('sd_fx_intensity', i); } catch(e) {}

        // Show/hide intensity label
        const label = document.querySelector('.fx-label');
        if (label) label.textContent = labels[i];
    }

    applyIntensity(idx);

    toggle.addEventListener('click', () => {
        idx = (idx + 1) % 3;
        applyIntensity(idx);
    });
}

// --- TYPEWRITER EFFECT FOR SYS-LOG ---
function initTypewriter() {
    const log = document.querySelector('.sys-log');
    if (!log) return;

    const lines = log.querySelectorAll('.line');
    if (lines.length === 0) return;

    // Store original HTMLs
    const originals = [];
    lines.forEach(function(line) {
        originals.push(line.innerHTML);
        line.innerHTML = '';
        line.style.opacity = '0';
    });

    // Add blinking cursor
    const cursor = document.createElement('span');
    cursor.className = 'sys-log-cursor';
    cursor.textContent = '▮';
    log.appendChild(cursor);

    let currentLine = 0;
    let currentChar = 0;

    function typeNext() {
        if (currentLine >= originals.length) {
            // All lines typed, keep cursor blinking
            cursor.style.animation = 'blink-cursor 1s step-end infinite';
            return;
        }

        const line = lines[currentLine];
        const html = originals[currentLine];
        line.style.opacity = '1';

        if (currentChar === 0) {
            line.innerHTML = '';
        }

        // Type one character at a time (handle HTML tags as single units)
        if (currentChar < html.length) {
            // Check if we're at a tag
            if (html[currentChar] === '<') {
                const tagEnd = html.indexOf('>', currentChar);
                if (tagEnd !== -1) {
                    line.innerHTML = html.substring(0, tagEnd + 1);
                    currentChar = tagEnd + 1;
                } else {
                    line.innerHTML = html.substring(0, currentChar + 1);
                    currentChar++;
                }
            } else {
                line.innerHTML = html.substring(0, currentChar + 1);
                currentChar++;
            }

            // Move cursor after current line
            cursor.remove();
            line.appendChild(cursor);

            const delay = Math.random() * 25 + 15; // 15-40ms per char
            setTimeout(typeNext, delay);
        } else {
            // Line complete
            line.innerHTML = html;
            currentLine++;
            currentChar = 0;

            if (currentLine < originals.length) {
                setTimeout(typeNext, 200); // Pause between lines
            } else {
                // Done — move cursor to end of last line
                cursor.remove();
                const lastLine = lines[lines.length - 1];
                lastLine.appendChild(cursor);
                line.appendChild(cursor);
            }
        }
    }

    // Start typing after a short delay
    setTimeout(typeNext, 400);
}

// --- STAR DUST BACKGROUND (canvas particle system) ---
let stardustAnimId = null;
let stardustParticles = [];

function initStarDust() {
    // Just init the canvas reference; actual animation starts on toggle
    const canvas = document.getElementById('stardust-canvas');
    if (!canvas) return;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);
}

function startStardust() {
    const canvas = document.getElementById('stardust-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Create particles
    const count = 80;
    stardustParticles = [];
    for (let i = 0; i < count; i++) {
        stardustParticles.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            r: Math.random() * 1.5 + 0.5,
            vx: (Math.random() - 0.5) * 0.2,
            vy: (Math.random() - 0.5) * 0.2,
            alpha: Math.random() * 0.6 + 0.2,
            pulse: Math.random() * Math.PI * 2
        });
    }

    function animate() {
        if (!canvas.classList.contains('active')) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            stardustAnimId = null;
            return;
        }

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const time = Date.now() * 0.001;
        const intensity = document.body.classList.contains('fx-extreme') ? 1.2 : 0.7;

        stardustParticles.forEach(function(p) {
            p.x += p.vx;
            p.y += p.vy;

            // Wrap around edges
            if (p.x < 0) p.x = canvas.width;
            if (p.x > canvas.width) p.x = 0;
            if (p.y < 0) p.y = canvas.height;
            if (p.y > canvas.height) p.y = 0;

            // Pulsing alpha
            const alpha = (Math.sin(time * 2 + p.pulse) * 0.3 + 0.7) * p.alpha * intensity;

            // Draw particle with glow
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(244, 114, 182, ' + alpha + ')';
            ctx.fill();

            // Glow halo
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r * 3, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(244, 114, 182, ' + (alpha * 0.15) + ')';
            ctx.fill();
        });

        stardustAnimId = requestAnimationFrame(animate);
    }

    stardustAnimId = requestAnimationFrame(animate);
}

function stopStardust() {
    if (stardustAnimId) {
        cancelAnimationFrame(stardustAnimId);
        stardustAnimId = null;
    }
    const canvas = document.getElementById('stardust-canvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    stardustParticles = [];
}

// --- STATISTICS CHARTS (US-W07) ---
function initStats() {
    var statsData = document.getElementById('stats-data');
    if (!statsData) return;

    // Prefer the consolidated node-stats blob; fall back to individual
    // data attributes if it is absent or malformed.
    var node = null;
    var nodeJson = statsData.getAttribute('data-node-stats');
    if (nodeJson) {
        try { node = JSON.parse(nodeJson); } catch (e) { node = null; }
    }
    function attr(name, key) {
        if (node && typeof node[key] === 'number') return node[key];
        return parseInt(statsData.getAttribute(name)) || 0;
    }

    var total = attr('data-total-nodes', 'total');
    if (total === 0) return;

    // Max value for bar scaling (find the maximum across all counts)
    var counts = {
        vless:  attr('data-vless-count', 'vless'),
        vmess:  attr('data-vmess-count', 'vmess'),
        trojan: attr('data-trojan-count', 'trojan'),
        ss:     attr('data-ss-count', 'ss'),
        hy2:    attr('data-hy2-count', 'hy2'),
        bs:     attr('data-bs-count', 'bs'),
        chs:    attr('data-chs-count', 'chs'),
        ru:     attr('data-ru-count', 'ru')
    };

    var maxCount = Math.max(counts.vless, counts.vmess, counts.trojan, counts.ss, counts.hy2, 1);

    // Render protocol bars
    function setBar(id, val) {
        var bar = document.getElementById(id);
        var valEl = document.getElementById('val-' + id.split('-')[1]);
        if (bar) bar.style.width = (val / maxCount * 100) + '%';
        if (valEl) valEl.textContent = val;
    }
    setBar('bar-vless', counts.vless);
    setBar('bar-vmess', counts.vmess);
    setBar('bar-trojan', counts.trojan);
    setBar('bar-ss', counts.ss);
    setBar('bar-hy2', counts.hy2);

    // Render class bars
    var maxClass = Math.max(counts.bs, counts.chs, counts.ru, 1);
    function setClassBar(id, val) {
        var bar = document.getElementById(id);
        var valEl = document.getElementById('val-' + id.split('-')[1]);
        if (bar) bar.style.width = (val / maxClass * 100) + '%';
        if (valEl) valEl.textContent = val;
    }
    setClassBar('bar-bs', counts.bs);
    setClassBar('bar-chs', counts.chs);
    setClassBar('bar-ru', counts.ru);

    // Render country distribution
    var countryStats = (node && Array.isArray(node.countries)) ? node.countries : null;
    if (!countryStats) {
        var countryJson = statsData.getAttribute('data-country-stats');
        if (countryJson) {
            try { countryStats = JSON.parse(countryJson); } catch(e) { countryStats = null; }
        }
    }
    if (countryStats) {
        try {
            var countryChart = document.getElementById('country-chart');
            if (countryChart && countryStats.length > 0) {
                var maxCountry = countryStats[0].count || 1;
                var html = '';
                countryStats.forEach(function(c) {
                    var pct = (c.count / maxCountry * 100);
                    html += '<div class="chart-bar-row">' +
                        '<span class="chart-bar-label">' + (c.flag || '') + ' ' + (c.code || '??') + '</span>' +
                        '<div class="chart-bar-track">' +
                            '<div class="chart-bar-fill bar-country" style="width:' + pct + '%;"></div>' +
                        '</div>' +
                        '<span class="chart-bar-value">' + c.count + '</span>' +
                    '</div>';
                });
                countryChart.innerHTML = html;
            }
        } catch(e) {
            // If rendering fails, leave the placeholder
        }
    }

    // Render speed summary
    var maxSpeed = (node && typeof node.max_speed === 'number')
        ? node.max_speed : (statsData.getAttribute('data-max-speed') || '—');
    var totalNodes = (node && typeof node.total === 'number')
        ? node.total : (statsData.getAttribute('data-total-nodes') || '—');
    var sumMax = document.getElementById('sum-max-speed');
    var sumTotal = document.getElementById('sum-total');
    var sumBS = document.getElementById('sum-bs');
    if (sumMax) sumMax.textContent = maxSpeed + ' Mbps';
    if (sumTotal) sumTotal.textContent = totalNodes;
    if (sumBS) sumBS.textContent = counts.bs;
}

init();
