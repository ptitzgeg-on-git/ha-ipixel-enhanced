# Using iPIXEL Enhanced in automations

Everything the card does is also available to automations/scripts through
**services** and **entities**, so you can drive the panel from any HA trigger.

## The building blocks

| You want to… | Use |
|---|---|
| Show a saved page | `ipixel_color.show_page` with `name:` |
| Show an inline page | `ipixel_color.show_page` with `page:` |
| Refresh a live page (clock/sensors) | call `show_page` on a `time_pattern` trigger, or use the playlist |
| Start / stop the auto-rotating playlist | `ipixel_color.set_playlist` `enable: true/false` |
| Show an image or animated GIF | `ipixel_color.show_image` `source:` |
| Recall something stored on the device | `ipixel_color.show_slot` `slot:` |
| Rotate the screen | `ipixel_color.set_orientation` or the **Orientation** select |
| Brightness / power | the `number`/`switch` entities (e.g. `number.<device>_brightness`) |
| Audio bars | `ipixel_color.set_rhythm_levels` (send repeatedly) |

A page is saved in the card's **library** and persists across restarts. The
**playlist** is stored too and keeps running on its own; `set_playlist` just
turns that rotation on/off from automations.

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
      - service: ipixel_color.show_page
        target:
          device_id: <your_device>
        data:
          name: welcome        # a page you saved in the card
```

### Keep a live page fresh (clock + sensors) every minute
A rendered page is a snapshot, so re-send it to update it:
```yaml
automation:
  - alias: Refresh dashboard page
    trigger:
      - platform: time_pattern
        minutes: "/1"
    action:
      - service: ipixel_color.show_page
        target:
          device_id: <your_device>
        data:
          name: dashboard
```
(Or just put that one page in the **playlist** with a 60 s duration — it
re-renders automatically. For a pure clock, prefer the device's native clock
mode, which ticks with no Bluetooth traffic.)

### Day / night: playlist by schedule
```yaml
automation:
  - alias: Playlist on in the morning
    trigger: { platform: time, at: "07:00:00" }
    action:
      - service: ipixel_color.set_playlist
        data: { enable: true }
  - alias: Playlist off at night
    trigger: { platform: time, at: "23:00:00" }
    action:
      - service: ipixel_color.set_playlist
        data: { enable: false }
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
      - service: ipixel_color.show_page
        target: { device_id: <your_device> }
        data:
          page:
            background: "200000"
            widgets:
              - { type: emoji, emoji: "🔔", anchor: center, size: 18 }
      - delay: "00:00:10"
      - service: ipixel_color.show_page          # restore your usual page
        target: { device_id: <your_device> }
        data: { name: dashboard }
```

### Show an animated GIF
```yaml
- service: ipixel_color.show_image
  target: { device_id: <your_device> }
  data:
    source: /local/party.gif     # file in config/www/, or an http(s) URL
```

### Store a page on the device, recall it later (works even if HA is off)
```yaml
# Save once:
- service: ipixel_color.show_page
  target: { device_id: <your_device> }
  data: { name: dashboard, save_slot: 1 }
# Recall any time (no rendering, instant):
- service: ipixel_color.show_slot
  target: { device_id: <your_device> }
  data: { slot: 1 }
```

### Native animation: let the panel cycle slots by itself
This is the box's "animation" feature. Save a few pages/images to device slots,
then start the device-side rotation — it keeps running with **no Home Assistant
and no Bluetooth**:
```yaml
# 1) store a few screens (once)
- service: ipixel_color.show_page
  target: { device_id: <your_device> }
  data: { name: weather, save_slot: 1 }
- service: ipixel_color.show_image
  target: { device_id: <your_device> }
  data: { source: /local/cat.gif, save_slot: 2 }
# 2) tell the panel to auto-cycle them
- service: ipixel_color.set_program
  target: { device_id: <your_device> }
  data: { slots: [1, 2] }
```

### Audio-reactive bars (advanced)
The panel does **not** analyse audio itself — you feed it 11 levels (0-15),
typically from an audio-analysis sensor, and call the service repeatedly:
```yaml
- service: ipixel_color.set_rhythm_levels
  target: { device_id: <your_device> }
  data:
    style: 2
    levels: "{{ state_attr('sensor.audio_spectrum','bands') }}"  # list of 11 ints
```
For a self-contained visualizer that needs no audio source, use
`ipixel_color.set_rhythm_animation` instead.

## Tips

- Find `<your_device>` in **Settings → Devices & Services → iPIXEL → the device**
  (or use the device picker in the visual service editor).
- Multiple panels: every service has a device target; the playlist has a target
  too (`set_playlist` `device_id:`).
- Long actions: BLE writes take a moment; avoid firing `show_*` many times per
  second (rhythm levels excepted).
