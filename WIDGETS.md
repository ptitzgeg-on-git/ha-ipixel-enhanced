# Widget reference

A **page** is a background colour plus a list of **widgets** drawn on top, in
order (later widgets draw over earlier ones), onto the display resolution
(32×32 by default).

```yaml
background: "000000"        # hex, #rrggbb, a name (red/blue/…), or [r,g,b]
widgets:
  - type: text
    text: "Hi"
    anchor: center
    color: "ffaa00"
```

## Positioning

Every widget (except `line`, which uses explicit coordinates) can be placed in
one of two ways:

- **Anchor** — `anchor:` one of:
  `top_left`, `top_center`, `top_right`,
  `center_left`, `center`, `center_right`,
  `bottom_left`, `bottom_center`, `bottom_right`.
  Optionally nudge with `dx:` / `dy:` (pixels).
- **Absolute** — give `x:` and `y:` (top-left of the widget).

## Common fields

| Field | Meaning |
|---|---|
| `type` | Widget type (see below). |
| `anchor` / `x` `y` / `dx` `dy` | Position (above). |
| `color` | Hex, `#rrggbb`, colour name, or `[r,g,b]`. |
| `if` | Optional. If it evaluates falsy (`0`, `false`, empty, `unavailable`…), the widget is skipped. Templates allowed. |

**Templates:** any string field may contain Jinja2, e.g.
`text: "{{ states('sensor.temp') }}°"` or even
`color: "{{ 'ff0000' if is_state('binary_sensor.alarm','on') else '00cc33' }}"`.

---

## Live Home Assistant data (dynamic content)

This is the key to custom dashboards: **every field is a Jinja2 template**, so
you bind any entity, attribute or API-backed sensor directly. A few patterns:

**Progress bar driven by a sensor:**
```yaml
- type: progress
  anchor: bottom_center
  width: 30
  height: 5
  value: "{{ states('sensor.battery') }}"
  color: "{{ '00cc33' if states('sensor.battery')|int(0) > 30 else 'ff3333' }}"
```

**Text from any sensor (incl. REST/API sensors you create in HA):**
```yaml
- type: text
  text: "{{ states('sensor.my_rest_api') }}"
  anchor: center
  font: WP7xn
```

**Show/hide a widget on a condition** (`if`):
```yaml
- type: emoji
  emoji: "🔔"
  anchor: center
  if: "{{ is_state('binary_sensor.doorbell', 'on') }}"
```

**Attributes & math:**
```yaml
- type: text
  text: "{{ state_attr('weather.home','temperature')|round }}°"
```

For data from an external API: create a [REST sensor](https://www.home-assistant.io/integrations/rest/)
(or any integration) in Home Assistant, then reference `states('sensor.xxx')`
here. The display refreshes when you press **Send now**, when the **playlist**
re-renders the page, or when you call the `ipixel_color.show_page` service from
an automation (e.g. on a `time_pattern` trigger every minute).

> The card ships **starter examples** (Battery bar, Temperature, Two sensors,
> Alert) — pick one from the *Examples* dropdown and swap in your entity names.

> **No typing needed:** in the visual editor, `text` and `progress` widgets have
> a **＋ HA entity** box — start typing an entity name, pick it, and the
> `{{ states('…') }}` template is filled in for you.

### Clock & live refresh

A `clock` widget (and any template) is rendered to a **still image** and sent
once — it does not tick on its own. To keep it live, add the page to a
**playlist** (even a single page): each page re-renders on its interval, so
sensors and the clock update. For a **clock-only** display, prefer the panel's
**native clock mode** (the device's `select` mode → clock) — it ticks by itself
with no Bluetooth traffic.

### Fonts

Pixel fonts render crisp 1-bit by default. Readable native sizes:
`WP7xn`→7, `7x5`→7, `5x5`→10, `3x5-de`→8. Add `antialias: true` only for large
text where smooth edges help. (Color emoji are drawn with the `emoji` widget,
not by selecting a font.)

---

## Widget types

### `text`
| Field | Default | Notes |
|---|---|---|
| `text` | — | Content (template-friendly). `\n` for multiple lines. |
| `font` | `5x5` | One of the bundled pixel fonts: `5x5`, `7x5`, `3x5-de`, `WP7xn`, `OpenSans-Light`. |
| `size` | `5` | Font size in px. |
| `align` | `left` | `left`/`center`/`right` for multi-line. |
| `spacing` | `1` | Extra px between lines. |
| `color` | `ffffff` | |

### `emoji`
| Field | Default | Notes |
|---|---|---|
| `emoji` | — | The emoji character, e.g. `☀️`. |
| `size` | `12` | Square size in px. |

### `clock`
A clock **rendered** as text (composites with other widgets, previews live).
Same fields as `text`, plus:
| Field | Default | Notes |
|---|---|---|
| `format` | `%H:%M` | Python `strftime`. |

> A rendered `clock` is a still image and only updates when the page is re-sent
> (e.g. via a playlist). For a clock that ticks on its own, use `native_clock`.

### `native_clock`
Switches the panel to its **built-in clock mode** — it ticks by itself on the
device, with no Bluetooth traffic afterwards. This is an **exclusive** mode: it
takes over the whole panel, so any other widgets on the page are ignored when
it's sent, and there is **no live preview** (the designer shows the current time
as a stand-in only — the firmware draws the real face).

| Field | Default | Notes |
|---|---|---|
| `style` | `1` | Built-in clock style, `0`–`8`. |
| `format_24` | `true` | 24-hour vs 12-hour. |
| `show_date` | `true` | Show the date alongside the time. |

### `line`
| Field | Default | Notes |
|---|---|---|
| `x` `y` | `0,0` | Start point. |
| `x2` `y2` | `width-1`, `y` | End point. |
| `width` | `1` | Thickness. |
| `color` | `888888` | |

### `rect` (aliases: `rectangle`, `box`)
| Field | Default | Notes |
|---|---|---|
| `width` `height` | `4,4` | |
| `fill` | `true` | `false` = outline only. |
| `radius` | `0` | Rounded corners. |
| `color` | `ffffff` | |

### `progress` (alias: `bar`)
| Field | Default | Notes |
|---|---|---|
| `value` | `0` | 0–100 (template-friendly). |
| `width` | full | Bar width. |
| `height` | `4` | Bar height. |
| `color` | `00cc33` | Filled part. |
| `bg` | `303030` | Track. |

### `image`
| Field | Default | Notes |
|---|---|---|
| `src` | — | `http(s)://…`, `/local/…` (your `config/www`), or an absolute path. |
| `width` `height` | image size | Target box. |
| `fit` | `contain` | `contain` / `cover` / `stretch`. |

### `gif`
Same fields as `image` (`src`, `width`, `height`, `fit`) and the same
positioning — but an **animated** GIF source plays on the panel. When a page
contains an animated GIF, the whole page is rendered as a multi-frame GIF (every
other widget stays as drawn) and uploaded so the device plays it natively. A
single-frame source behaves like a still `image`. Heavy GIFs are capped to keep
the Bluetooth upload reasonable, so the playback may be resampled.

| Field | Default | Notes |
|---|---|---|
| `src` | — | `http(s)://…`, `/local/…` (your `config/www`), or an absolute path. Animated GIF for motion. |
| `width` `height` | gif size | Target box. |
| `fit` | `contain` | `contain` / `cover` / `stretch`. |

---

## Example: weather page

```yaml
background: "000000"
widgets:
  - type: emoji
    emoji: "☀️"
    anchor: top_left
    size: 14
  - type: text
    text: "{{ states('sensor.outdoor_temperature') }}°"
    anchor: top_right
    color: "ffaa00"
    font: "5x5"
  - type: line
    x: 0
    y: 17
    x2: 31
    y2: 17
    color: "2d2d2d"
  - type: clock
    format: "%H:%M"
    anchor: bottom_center
    color: "bebebe"
```
