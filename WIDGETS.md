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
Same fields as `text`, plus:
| Field | Default | Notes |
|---|---|---|
| `format` | `%H:%M` | Python `strftime`. |

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
