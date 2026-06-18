# Using iPIXEL Enhanced in automations

Everything the card does is also available to automations/scripts through
**services** and **entities**, so you can drive the panel from any HA trigger.

## The building blocks

| You want to… | Use |
|---|---|
| Show a saved page | `ipixel_enhanced.show_page` with `name:` |
| Show an inline page | `ipixel_enhanced.show_page` with `page:` |
| Show scrolling text | `ipixel_enhanced.show_text` with `text:` (templates supported) |
| Show an emoji | `ipixel_enhanced.show_emoji` with `emoji:` |
| Show the native clock | `ipixel_enhanced.show_clock` (style / 24h / date) |
| Refresh a live page (sensors) | call `show_page` on a `time_pattern` trigger, or use the playlist |
| Start a named playlist | `ipixel_enhanced.start_playlist` with `name:` (+ optional `device_id:`, one or more panels) |
| Stop the playlist | `ipixel_enhanced.stop_playlist` (+ optional `device_id:` to stop only some panels) |
| Pick a playlist per panel | each panel's **Playlist** select entity (`select.<panel>_playlist`) |
| Show an image or animated GIF | `ipixel_enhanced.show_image` `source:` |
| Recall something stored on the device | `ipixel_enhanced.show_slot` `slot:` |
| Rotate the screen | `ipixel_enhanced.set_orientation` or the **Orientation** select |
| Brightness / power | the `number`/`switch` entities (e.g. `number.<device>_brightness`) |
| Audio bars | `ipixel_enhanced.set_rhythm_levels` (send repeatedly) |

> **Showing the clock from an automation:** call **`ipixel_enhanced.show_clock`**.
> Changing the *Clock 24h* / *Clock Style* entities alone does **not** refresh
> the panel — those are just settings read the next time the clock is shown.

A page is saved in the card's **library** and persists across restarts. You can
build several **named playlists** in the card; `start_playlist: { name: … }`
starts one (great for day/night scenes), and `stop_playlist` halts it. Each
panel runs its **own** playlist, so add `device_id:` (it accepts several) to
target specific displays — without it, the playlist's saved targets are used,
falling back to every panel. The same playlist can run on multiple panels at
once. `set_playlist` is a legacy shim that only stops playback.

## Examples

### Show a saved page when you get home
```yaml
automation:
  - alias: Welcome page on arrival
    trigger:
      - platform: state
        entity_id: person.me
        to: home
    action:
      - service: ipixel_enhanced.show_page
        target:
          device_id: <your_device>
        data:
          name: welcome        # a page you saved in the card
```

### Show the clock (native, ticks on the device)
```yaml
automation:
  - alias: Clock in the evening
    trigger: { platform: time, at: "20:00:00" }
    action:
      - service: ipixel_enhanced.show_clock
        target:
          device_id: <your_device>
        data:
          style: 1          # face style 0-8
          format_24: true   # 24-hour time
          show_date: true
```
Once shown, the clock keeps ticking on the panel with no Bluetooth traffic.
The optional **Clock Style / Clock 24h / Clock Show Date** entities just set the
defaults used by this service and by the card's clock controls.

### Scrolling text alert
```yaml
automation:
  - alias: Washing machine done
    trigger:
      - platform: state
        entity_id: binary_sensor.washing_machine_done
        to: "on"
    action:
      - service: ipixel_enhanced.show_text
        target: { device_id: <your_device> }
        data:
          text: "Laundry ready 🧺"
          color: "00ccaa"
          animation: 1       # scroll left
          speed: 60
```

### Keep a live page fresh (sensors) every minute
A rendered page is a snapshot, so re-send it to update it:
```yaml
automation:
  - alias: Refresh dashboard page
    trigger:
      - platform: time_pattern
        minutes: "/1"
    action:
      - service: ipixel_enhanced.show_page
        target:
          device_id: <your_device>
        data:
          name: dashboard
```
(Or just put that one page in the **playlist** with a 60 s duration — it
re-renders automatically. For a pure clock, prefer the device's native clock
mode, which ticks with no Bluetooth traffic.)

### Day / night: a different named playlist per moment
Build the playlists once in the card (e.g. **Morning**, **Night**), then switch
between them by name:
```yaml
automation:
  - alias: Morning playlist
    trigger: { platform: time, at: "07:00:00" }
    action:
      - service: ipixel_enhanced.start_playlist
        data: { name: "Morning" }
  - alias: Night playlist
    trigger: { platform: time, at: "19:00:00" }
    action:
      - service: ipixel_enhanced.start_playlist
        data: { name: "Night" }
  # Target specific panels (and run the same playlist on several at once):
  - alias: Night playlist on the two living-room panels
    trigger: { platform: time, at: "19:00:00" }
    action:
      - service: ipixel_enhanced.start_playlist
        data:
          name: "Night"
          device_id: [<panel_a>, <panel_b>]
  - alias: Off late
    trigger: { platform: time, at: "23:00:00" }
    action:
      - service: ipixel_enhanced.stop_playlist
      - service: switch.turn_off
        target: { entity_id: switch.<your_device> }   # power off the panel
```

### Alert overlay, then back to normal
```yaml
automation:
  - alias: Doorbell alert
    trigger:
      - platform: state
        entity_id: binary_sensor.doorbell
        to: "on"
    action:
      - service: ipixel_enhanced.show_page
        target: { device_id: <your_device> }
        data:
          page:
            background: "200000"
            widgets:
              - { type: emoji, emoji: "🔔", anchor: center, size: 18 }
      - delay: "00:00:10"
      - service: ipixel_enhanced.show_page          # restore your usual page
        target: { device_id: <your_device> }
        data: { name: dashboard }
```

### Show an animated GIF
```yaml
- service: ipixel_enhanced.show_image
  target: { device_id: <your_device> }
  data:
    source: /local/party.gif     # file in config/www/, or an http(s) URL
```

### Store a page on the device, recall it later (works even if HA is off)
```yaml
# Save once:
- service: ipixel_enhanced.show_page
  target: { device_id: <your_device> }
  data: { name: dashboard, save_slot: 1 }
# Recall any time (no rendering, instant):
- service: ipixel_enhanced.show_slot
  target: { device_id: <your_device> }
  data: { slot: 1 }
```

### Native animation: let the panel cycle slots by itself
This is the box's "animation" feature. Save a few pages/images to device slots,
then start the device-side rotation — it keeps running with **no Home Assistant
and no Bluetooth**:
```yaml
# 1) store a few screens (once)
- service: ipixel_enhanced.show_page
  target: { device_id: <your_device> }
  data: { name: weather, save_slot: 1 }
- service: ipixel_enhanced.show_image
  target: { device_id: <your_device> }
  data: { source: /local/cat.gif, save_slot: 2 }
# 2) tell the panel to auto-cycle them
- service: ipixel_enhanced.set_program
  target: { device_id: <your_device> }
  data: { slots: [1, 2] }
```

### A note on the rhythm/visualizer
The panel has **no microphone** and Home Assistant does not expose a real-time
audio stream from media players (Spotify, radio…) or the phone, so there's no
lightweight way to make the bars truly react to sound — the rhythm mode is not
surfaced in the UI. The protocol-level service `ipixel_enhanced.set_rhythm_levels`
(feed 11 levels, 0-15) still exists for advanced setups that already produce an
audio-spectrum sensor.

## Tips

- Find `<your_device>` in **Settings → Devices & Services → iPIXEL → the device**
  (or use the device picker in the visual service editor).
- Multiple panels: every service takes a `device_id` target. Playlists are
  per-panel — pass `device_id:` (one or several) to `start_playlist`/`stop_playlist`,
  or use each panel's `select.<panel>_playlist` entity.
- Long actions: BLE writes take a moment; avoid firing `show_*` many times per
  second (rhythm levels excepted).
