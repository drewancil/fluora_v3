# fluora-v3

Python controls for Fluora LED plants running firmware 3.x.

The library implements the plant's local CoAP protocol, OSC discovery, state
observation, and an MQTT bridge. The protocol was reverse-engineered from local
network captures and is not an official Fluora API.

## Install

```console
python -m pip install fluora-v3
```

Python 3.14 or newer is currently required.

## Python API

```python
from fluora import FluoraMode, FluoraPlant

with FluoraPlant("192.168.4.169") as plant:
    plant.turn_on()
    plant.set_brightness(0.5)
    plant.set_mode(FluoraMode.MANUAL)
    plant.set_hue(0.75)
    plant.set_saturation(1.0)
```

State changes are available through `FluoraStateObserver`:

```python
from fluora import FluoraStateObserver

with FluoraStateObserver("192.168.4.169") as observer:
    for delta in observer.deltas():
        print(delta)
```

## MQTT Bridge

Run one bridge process for each plant:

```console
fluora-mqtt 192.168.4.169 mqtt.example.net \
  --base-topic fluora/bedroom \
  --username mqtt-user \
  --password mqtt-password
```

Known controls have paired state and set topics:

```text
fluora/bedroom/light/state
fluora/bedroom/light/set
fluora/bedroom/power/state
fluora/bedroom/power/set
fluora/bedroom/brightness/state
fluora/bedroom/brightness/set
fluora/bedroom/hue/state
fluora/bedroom/hue/set
fluora/bedroom/saturation/state
fluora/bedroom/saturation/set
fluora/bedroom/effect/state
fluora/bedroom/effect/set
fluora/bedroom/mode/state
fluora/bedroom/mode/set
fluora/bedroom/scene/state
fluora/bedroom/scene/set
```

State messages are retained. Every parameter discovered in plant state is also
available at `<base>/parameter/<parameter-id>/{state,set}`. Active animation
sliders use `<base>/animation/<label>/{state,set}`.

The `light` topics use Home Assistant's MQTT JSON light schema and combine power,
brightness, hue, and saturation into one control. Brightness is `0..255` and is
scaled over the plant firmware's persistent `0.2..1.0` range. Color is an HS object
with hue in degrees and saturation as a percentage:

```json
{
  "state": "ON",
  "brightness": 128,
  "color": {"h": 270.0, "s": 90.0}
}
```

Home Assistant discovery publishes this as a native light entity with on/off,
brightness, and HS color controls. The individual normalized `0.0..1.0` topics
remain available for direct MQTT use.

Effect topics accept either captured names or integer indices:

```console
mosquitto_pub -h mqtt.example.net \
  -t fluora/bedroom/effect/set \
  -m "Rainbow Bloom"
```

Friendly effect state topics publish the display name. Raw parameter topics keep
the plant's integer value. Home Assistant discovery presents manual and scene
effects as dropdown selectors.

See [`setup/protocol.md`](setup/protocol.md) for the observed plant protocol and
complete MQTT topic contract.
