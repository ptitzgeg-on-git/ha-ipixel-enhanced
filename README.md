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

## Using the iPIXEL Studio

After install, an **iPIXEL** entry appears in the Home Assistant **sidebar** —
open it for the full studio. (You can also add it to any dashboard with
`type: custom:ipixel-card`.) Pick your device top-right (multiple panels
supported), then use the tabs:

- **🎨 Designer** — build a page from widgets with a live 32×32 preview; bind HA
  entities with the *＋ HA entity* picker; **Send now**, save to your library, or
  load a starter example. Visual editor + a Code (JSON) mode.
- **✏️ Draw** — a clickable 32×32 grid: pick a colour and paint. **Send drawing**
  pushes the whole picture; **Live draw** lights each pixel on the panel as you
  click (enables the device's DIY mode). No service calls needed.
- **🔁 Playlist** — auto-rotate saved pages (also keeps dynamic data refreshed).
- **💾 Slots** — save pages into the panel's own memory and make it **cycle them
  by itself** (native animation, works with HA off). Show/delete slots too.
- **⚙️ Device** — power, brightness, orientation, DIY mode, clock style and the
  rhythm/visualizer animation, all in one place.

So `set_pixel`, `set_program`, etc. are driven from the UI — no need to call
those services by hand. See **[WIDGETS.md](WIDGETS.md)** for the widget
reference and **[AUTOMATIONS.md](AUTOMATIONS.md)** for automation recipes.

## Wrong size / cropped display?

Some panels — notably the **32×32 B.K. Light sold at Action** — report wrong
dimensions over Bluetooth. Go to **Settings → Devices & Services → iPIXEL →
Configure** and enable **Override panel dimensions**, then set the real width
and height (e.g. 32 × 32).

## Multiple displays

Add each display as a separate integration entry (they're auto-discovered).
The designer's device dropdown, the `show_page` service target, and the
playlist target all let you address a specific panel.

---

## Services

| Service | Purpose |
|---|---|
| `ipixel_color.show_page` | Render a saved page (`name`) or an inline `page` and push it to a device. Optional `save_slot` stores it on the device. |
| `ipixel_color.show_text` | Quick scrolling text. |
| `ipixel_color.show_emoji` | Show a single emoji. |
| `ipixel_color.show_image` | Send an image or **animated GIF** (URL or `/local/...`). GIFs play natively. |
| `ipixel_color.set_orientation` | Rotate the display (0/90/180/270°). Also an **Orientation** select entity. |
| `ipixel_color.set_fun_mode` | Toggle the panel's built-in effect mode. Also a **Fun Mode** switch. |
| `ipixel_color.show_slot` / `delete_slot` | Recall / delete a program stored in device memory. |
| `ipixel_color.set_playlist` | Start/stop the auto-rotating playlist from an automation. |
| `ipixel_color.set_rhythm_animation` | Self-contained visualizer animation (no audio feed). |
| `ipixel_color.set_rhythm_levels` | Audio bars from levels you supply (send repeatedly). |

See **[AUTOMATIONS.md](AUTOMATIONS.md)** for ready-to-use automation examples
(arrival page, day/night playlist, doorbell alert, GIFs, device slots…).

### Extra entities

Each display also exposes an **Orientation** select and a **Fun Mode** switch,
on top of power, brightness, clock style, font, etc.

### Fonts

Bundled pixel fonts render crisp on the matrix: **Tiny5** (default, most
readable), WP7xn, PixelifySans, 7x5, 5x5, PressStart2P (retro, wide), plus
OpenSans-Light. Color emoji are drawn with the `emoji` widget.

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
