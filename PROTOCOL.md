# iPIXEL / LED_BLE protocol notes

Reverse-engineering reference for the iPIXEL Color panels (e.g. the **32×32
B.K. Light sold at Action**, device type `0x81` = 129, LED type 2). Compiled
from [pypixelcolor](https://pypi.org/project/pypixelcolor/), the
[ESPHome component](https://github.com/DonKracho/ESPHome-component-iPixel-ble)
and live captures from a real panel.

## BLE characteristics

| Role | UUID |
|---|---|
| Service | `0000fa01-0000-1000-8000-00805f9b34fb` |
| Write | `0000fa02-0000-1000-8000-00805f9b34fb` |
| Notify | `0000fa03-0000-1000-8000-00805f9b34fb` |

Frames are length-prefixed little-endian: `LL LL <cmd_hi> <cmd_lo> <payload…>`.
MTU is often 20 (no negotiation), so large payloads (images) are chunked;
images use Write-Without-Response for speed, short commands Write-With-Response.

## Device info (what your panel reports)

Send the device-info/firmware query; the panel answers on the notify channel.
Captured from a real B.K. Light 32×32:

```
response: 0c 00 01 80 81 26 05 00 00 01 00 01
          └len─┘ └cmd─┘ └type   firmware bytes ──┘
```

- `0c 00` → length 12
- `01 80` → reply id
- `81` → device type 129 → resolved to 32×32, LED type 2
- remaining bytes → firmware/version data (MCU/BLE)

This integration reads this automatically on connect (logged at INFO as
`Device info raw BLE response:`) and adopts the reported dimensions when valid.
If your panel reports the wrong size, override it in
**Settings → Devices & Services → iPIXEL → Configure**.

## Full command set (capabilities of the hardware)

| Command | What it does | Exposed here? |
|---|---|---|
| setPower | On/off | ✅ `switch` |
| setBrightness | Brightness | ✅ `number` |
| setTime / device info | Sync clock, read params | ✅ (auto on connect) |
| getFirmwareVersions | Firmware query | ✅ (logged) |
| showText | Text + animation/color/rainbow/font | ✅ `show_text`, designer |
| showImage | Image/GIF transfer (chunked, CRC) | ✅ `show_image` service (animated GIF native) + designer `image` widget |
| showClock | Native clock styles, calendar, 12/24h | ✅ `select` clock style |
| showPixel | Set individual pixels (RGB) | ⚙️ via rendered pages (engine draws pixels) |
| setRotation | Display orientation (0/90/180/270) | ✅ `Orientation` select + `set_orientation` service |
| setSpeed | Animation speed | ✅ in `show_text` |
| setFunMode | Built-in effect mode | ✅ `Fun Mode` switch + `set_fun_mode` service |
| showRhythmLevels / showRhythmAnimation | Audio-reactive visualizations | ⏳ not yet exposed |
| setProgramList / showSlot / deleteSlot | Save/recall stored programs | ✅ `save_slot` on show_page/show_image + `show_slot`/`delete_slot` services |
| clear | Blank the display | ⚙️ (send an all-black page) |

✅ available · ⚙️ achievable via the page engine · ⏳ candidate for a future
service/entity.

## What the box's advertised features map to

Confirmed against the
[official protocol doc](https://github.com/cagcoach/ha-ipixel-color/blob/main/iPIXEL-Protocol-Documentation.md),
[ipixel-ctrl](https://github.com/sdolphin-JP/ipixel-ctrl) and
[go-ipxl](https://github.com/yyewolf/go-ipxl):

- **"Animation"** = *program mode* (`0x8008`): the panel auto-cycles content you
  stored in slots, by itself. Save pages/GIFs with `save_slot`, then
  `set_program: [1,2,3]`. Also covers animated GIF upload (`0x0003`).
- **"Clock"** = clock mode (`0x0106` + time `0x8001`) → the **clock style**
  select; ticks on the device.
- **"Rhythm"** = `0x0201` (levels) / `0x0200` (animation). The panel has **no
  microphone** — feed levels with `set_rhythm_levels`, or use the self-running
  `set_rhythm_animation`.
- **"Fun mode" = DIY / draw mode** (`0x0104` enable, then `0x0105` per pixel).
  **Enabling it blanks the screen on purpose** — it's an empty canvas waiting
  for `set_pixel`. This is why the screen went black: it was working, just empty.

## Program slots (persist without Home Assistant)

`show_page`/`show_image` accept `save_slot: 1-255`, which both displays the
content **and** stores it in the panel's memory. Later, `show_slot: N` recalls
it directly on the device — useful so the panel keeps showing something even if
Home Assistant is off. `delete_slot: N` clears a slot.

## Still on the table

- **Rhythm / audio-reactive** modes (`set_rhythm_mode`) — pypixelcolor exposes
  the builders; would need an audio level source in HA.
- **Native multi-frame animations** authored frame-by-frame (beyond GIF upload).

The protocol hooks above map directly onto pypixelcolor's command builders
(`set_orientation`, `set_fun_mode`, `show_slot`, `delete`, `send_image_hex`).
