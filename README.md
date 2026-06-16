# iPIXEL Enhanced for Home Assistant

A feature-rich Home Assistant integration for **iPIXEL Color** LED matrix
displays (32×32 and similar) over Bluetooth — with a **visual page designer**,
**emoji support**, and a **live 32×32 preview** right inside the dashboard.

Enhanced fork of [ha-ipixel-color](https://github.com/cagcoach/ha-ipixel-color).

---

## What makes it "enhanced"

- **Page designer card** — build pages by dropping widgets (text, sensor,
  emoji, clock, line, rectangle, progress bar, image) onto a 32×32 canvas.
  Pick a position from a 9-point anchor grid (top-left, center, bottom-right…)
  or type exact `x`/`y`. No coding required.
- **Live preview** — the card renders your page server-side and shows it
  pixel-perfect as you edit, like a Zigbee2MQTT-style editor.
- **Code mode** — power users get the raw page JSON for fine control.
- **Templates everywhere** — any text field accepts Jinja2, e.g.
  `{{ states('sensor.temperature') }}°`.
- **Emoji** — any emoji via Twemoji, auto-downloaded and cached.
- **Page library + playlist** — save named pages and auto-rotate them
  (weather 10 s → clock 5 s → …), all from the UI.

Everything is generic: it is **not** tied to any specific use case. You build
the pages you want.

---

## Installation (HACS)

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/ptitzgeg-on-git/ha-ipixel-enhanced` as **Integration**
3. Install **iPIXEL Enhanced**, then **restart** Home Assistant
4. Settings → Devices & Services → **Add Integration** → search **iPIXEL**

The designer card is registered automatically — no manual resource needed.

---

## Using the page designer

Add the card to any dashboard:

```yaml
type: custom:ipixel-card
```

Then:

1. **Add widget** → choose a type, set its content, position and colour.
2. Watch the **live preview** update.
3. **Send now** to push it to the display, or **Save** it to your library.
4. (Optional) Build a **playlist** and enable it to auto-rotate pages.

See **[WIDGETS.md](WIDGETS.md)** for the full widget reference.

---

## Services

| Service | Purpose |
|---|---|
| `ipixel_color.show_page` | Render a saved page (`name`) or an inline `page` and push it to a device. Great for automations. |
| `ipixel_color.show_text` | Quick scrolling text. |
| `ipixel_color.show_emoji` | Show a single emoji. |

Example automation:

```yaml
- alias: Rain alert on display
  trigger:
    - platform: numeric_state
      entity_id: sensor.rain_probability
      above: 60
  action:
    - service: ipixel_color.show_page
      target:
        device_id: <your_device>
      data:
        page:
          background: "001020"
          widgets:
            - { type: emoji, emoji: "🌧️", anchor: top_center, size: 14 }
            - { type: text, text: "{{ states('sensor.rain_probability') }}%",
                anchor: bottom_center, color: "5aa0ff", font: "5x5" }
```

---

## Requirements

- Home Assistant 2024.7+
- HACS
- An iPIXEL Color LED display (`LED_BLE_*`)
- Bluetooth adapter or an HA Bluetooth proxy

---

## Looking for the ESP32 route?

If you prefer a dedicated ESP32 gateway (better BLE range, GIF/online images),
see [@DonKracho's ESPHome component](https://github.com/DonKracho/ESPHome-component-iPixel-ble).
This project is the **direct Home Assistant** integration — no extra hardware.

---

## Credits

- Original integration: [@cagcoach](https://github.com/cagcoach/ha-ipixel-color)
- ESPHome component: [@DonKracho](https://github.com/DonKracho/ESPHome-component-iPixel-ble)
- Emoji artwork: [Twemoji](https://github.com/twitter/twemoji)
