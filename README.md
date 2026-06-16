# iPIXEL Enhanced for Home Assistant

A feature-rich Home Assistant integration for iPIXEL Color LED matrix displays (32×32, 64×20, 96×16, and more) via Bluetooth.

**Enhanced fork of [ha-ipixel-color](https://github.com/cagcoach/ha-ipixel-color)** with emoji support, a live pixel preview, and a YAML-based widget/template system.

---

## Features

- **Emoji support** — displays any emoji via Twemoji (auto-downloaded & cached)
- **Pixel-perfect bitmap font** — crisp rendering on small LED matrices
- **YAML template system** *(coming soon)* — define pages and widgets in YAML, preview them live
- **Multi-page playlist** *(coming soon)* — rotate pages automatically with configurable timing
- **Live 32×32 preview** *(coming soon)* — Lovelace card to see exactly what's on the display

---

## Installation via HACS

1. In HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/ptitzgeg-on-git/ha-ipixel-enhanced` as **Integration**
3. Install **iPIXEL Enhanced**
4. Restart Home Assistant
5. Go to Settings → Devices & Services → Add Integration → search **iPIXEL**

---

## Requirements

- Home Assistant 2024.1+
- HACS 1.32.0+
- An iPIXEL Color LED display (LED_BLE_*)
- Bluetooth adapter or HA Bluetooth proxy

---

## Credits

- Original integration: [@cagcoach](https://github.com/cagcoach/ha-ipixel-color)
- ESPHome component: [@DonKracho](https://github.com/DonKracho/ESPHome-component-iPixel-ble)
- Emoji: [Twemoji](https://github.com/twitter/twemoji) by Twitter/X
