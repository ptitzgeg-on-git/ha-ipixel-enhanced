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
| showImage | Image/GIF transfer (chunked, CRC) | ✅ images via designer `image` widget / engine |
| showClock | Native clock styles, calendar, 12/24h | ✅ `select` clock style |
| showPixel | Set individual pixels (RGB) | ⚙️ via rendered pages (engine draws pixels) |
| setRotation | Display orientation (0/90/180/270) | ⏳ not yet exposed |
| setSpeed | Animation speed | ✅ in `show_text` |
| setFunMode | Built-in effect mode | ⏳ not yet exposed |
| showRhythmLevels / showRhythmAnimation | Audio-reactive visualizations | ⏳ not yet exposed |
| setProgramList / delProgramList / deleteSlot | Save/recall stored programs | ⏳ not yet exposed |
| clear | Blank the display | ⚙️ (send an all-black page) |

✅ available · ⚙️ achievable via the page engine · ⏳ candidate for a future
service/entity.

## Ideas to "use 100%" of the panel

- **Rotation** entity (`select`: 0/90/180/270) — small addition.
- **Fun mode** select to trigger the firmware's built-in effects.
- **Native GIF**: `showImage` already supports GIF frames over BLE; the engine
  currently sends a single rendered frame. Multi-frame upload could animate.
- **Program slots**: store pages on the device so they persist without HA.

If you want any of these wired up, open an issue — the protocol hooks above map
directly onto pypixelcolor's command builders.
