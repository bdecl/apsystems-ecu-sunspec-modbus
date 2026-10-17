# apsystems-ecu-sunspec-modbus

Reverse-engineered SunSpec Modbus map of the APsystems ECU-C, measured register by
register, with the probe scripts used to obtain it, a Home Assistant integration
built on those findings, and a zero export blueprint.

Everything here was measured on a real installation, not taken from a datasheet.
APsystems publishes a short "SunSpec Modbus" document that lists a handful of
example reads; it does not say which fields are implemented, and it describes at
least one block that is not where the specification says it should be.

## Key findings

**The immediate controls are global, not per-inverter.** Model 123 is read and
written through an individual inverter's unit id, but the ECU applies the command
to the whole array. Writing `Conn = 0` on unit 1 stops every inverter. Writing
`WMaxLimPct = 1 %` on unit 1 curtails the entire installation to 1 % of its rated
power. Every other model is genuinely per-inverter. Confirmed on several unit ids.

**Model 123 is nearly empty.** Of its twenty-four registers, three carry real
commands: `Conn`, `WMaxLimPct` and `WMaxLim_Ena`. No power-factor control, no VAr
control, and none of the window, revert or ramp timing registers are implemented.
Nothing reverts on its own — if your controller stops, the last limit written
stays in force indefinitely.

**There is an undocumented model after the end of the chain.** The SunSpec chain
terminates at register 40210. A model 114 header sits at 40212, with 48 registers
of per-channel DC data behind it. A conforming client that walks the chain will
never see it; it is reachable only by hard-coded address.

**The float model loses status.** `St` and `Evt1` are implemented in model 103
(integer) and unimplemented in model 113 (float). A client that picks the float
model for precision silently loses operating state and event reporting.

**The ECU has no meter on Modbus.** Unit ids 0 to 247 were scanned: only the
configured inverter addresses answer. There is no SunSpec meter model, no reserved
unit for the gateway, and nothing in the out-of-chain block that reports grid
power. The ECU-C's own CT clamps are not reachable over Modbus by any route.

**A silent failure mode breaks zero export entirely.** While the ECU is linked to
an APsystems ELT storage system in EMA, it accepts power-limit writes, echoes the
value back correctly, reports the enable flag as set, and never applies the limit.
No error is returned at any layer, and `Conn` keeps working normally, which makes
it look like anything but a suppressed command. See
[docs/elt-link-issue.md](docs/elt-link-issue.md).

## Tested on

ECU-C, firmware `ECU-C-Z_C1.2.26`, nine QT2-3 three-phase microinverters, Modbus
TCP on port 502. Identifiers in the documentation are masked.

Other ECU models and firmware versions are likely to differ. If you run the probe
scripts on different hardware, a pull request with your output is welcome — that
is the point of this repository.

## Contents

| Path | What it is |
|---|---|
| [docs/register-map.md](docs/register-map.md) | Every register, its type, a measured value and whether the firmware implements it |
| [docs/elt-link-issue.md](docs/elt-link-issue.md) | The silent curtailment failure: symptoms, evidence, diagnosis and fix |
| [docs/official-documentation.md](docs/official-documentation.md) | What the manufacturer's reference covers, where it differs from the device, and links |
| [scripts/sunspec_walk.py](scripts/sunspec_walk.py) | Walks the model chain and prints what the ECU exposes. Start here |
| [scripts/sunspec_dump.py](scripts/sunspec_dump.py) | Full register-by-register dump, emits a markdown table |
| [scripts/ecu_probe.py](scripts/ecu_probe.py) | Scans unit ids and sweeps the address space for undocumented content |
| [custom_components/apsystems_ecu_sunspec](custom_components/apsystems_ecu_sunspec) | Home Assistant integration, installable through HACS |
| [blueprints/automation/apsystems_ecu_sunspec/zero_export.yaml](blueprints/automation/apsystems_ecu_sunspec/zero_export.yaml) | Zero export blueprint for the integration |
| [homeassistant/dashboards/](homeassistant/dashboards/) | Ready-made dashboards, three-phase and single-phase |
| [homeassistant/modbus.yaml](homeassistant/modbus.yaml) | YAML alternative: Modbus hub and sensors, documented and ready to adapt |
| [homeassistant/zero_export_example.yaml](homeassistant/zero_export_example.yaml) | YAML alternative: minimal zero-export controller |

## Home Assistant integration

`apsystems_ecu_sunspec` talks to the ECU's own SunSpec server on port 502. Nothing
is installed on the ECU. It knows the quirks documented above, so you do not have
to.

### Install

HACS, three dots, Custom repositories, add this repository as an *Integration*,
then install **APsystems ECU SunSpec (Modbus)** and restart Home Assistant. Or copy
`custom_components/apsystems_ecu_sunspec` into your configuration folder.

Then Settings, Devices & services, Add integration, *APsystems ECU SunSpec*. Enter
the ECU's address. The integration scans the Modbus addresses and shows what it
found before creating anything:

- the inverters that answer, at whatever addresses you gave them in EMA, gaps
  included;
- their model and AC topology, single-, split- or three-phase (models 101/102/103
  and 111/112/113), per inverter, so a mixed fleet works;
- the out-of-chain DC block, and how many DC channels each inverter has;
- which controls of model 123 actually work.

If you add inverters later, use *Reconfigure* on the integration to scan again.

### What you get

One device for the array, one per inverter.

| Device | Entities |
|---|---|
| APsystems ECU | Total AC power, total energy, total DC power, inverters producing and online, active events, **power limit** (number), **production** and **power limit enabled** (switches) |
| APsystems inverter *n* | AC power, current and voltages per phase, frequency, energy, temperature, operating state, events, DC voltage, current and power per channel |

Points the firmware does not implement are not created. Each inverter is read
from the integer model (it carries state and events, and its energy counter keeps
full precision), with the float model filling any point the integer one leaves
empty.

The controls act on **the whole array**, whichever inverter address they are
written through, and are therefore on the ECU device, not on the inverters.
Setting a power limit also sets `WMaxLim_Ena` if it was off, since a limit is
otherwise stored and silently ignored. The integration does not run a control
loop itself: that is what the blueprint is for.

### Zero export blueprint

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fbdecl%2Fapsystems-ecu-sunspec-modbus%2Fmain%2Fblueprints%2Fautomation%2Fapsystems_ecu_sunspec%2Fzero_export.yaml)

Or, in Home Assistant: Settings, Automations & scenes, Blueprints, Import
blueprint, and paste the raw file address:

```
https://raw.githubusercontent.com/bdecl/apsystems-ecu-sunspec-modbus/main/blueprints/automation/apsystems_ecu_sunspec/zero_export.yaml
```

Inputs: a grid power sensor (either sign convention), the power limit entity,
the array's rated power, a target grid power, a deadband, separate gains for
cutting and releasing, a floor, the control period and an optional enable entity
(a tariff or battery-full condition, for instance). It is incremental, holds the
last limit when the grid measurement disappears, and puts the array back to
100 % when the enable entity turns off. Keep the period at 30 s or more: dispatch
to the inverters takes about 20 s.

### Dashboards

[homeassistant/dashboards/](homeassistant/dashboards/) has a three-phase and a
single-phase dashboard built from native cards only. Paste one into a dashboard's
raw configuration editor and copy the per-inverter blocks for each of your
inverters.

### Limits

- The ECU itself is not visible over Modbus: no ECU serial, no ECU model, and its
  CT clamps cannot be read. A grid meter has to come from elsewhere.
- The [bolkedebruin/apsystems-sunspec](https://github.com/bolkedebruin/apsystems-sunspec)
  adapter (port 1502, installed on the ECU) is detected but not supported yet.
- Tested against an ECU-C with QT2 inverters and against a simulator built from
  the register map. Reports from other ECUs and inverters are welcome.

## Getting started with the scripts

Enable SunSpec on the ECU first: EMA Manager, ECU app, Workspace, Modbus
Configuration. Set Switch to On and give each inverter an address. Those addresses
become the Modbus unit ids. Port 502 is fixed.

```bash
pip install pymodbus
python3 scripts/sunspec_walk.py <ecu-ip> 1
```

All three scripts are read-only. They never write to the device.

## Before you write anything

Read back what you write, but do not trust the readback. The ECU echoes a stored
value whether or not it intends to act on it. The only proof that a command took
effect is measured AC power.

`WMaxLimPct_SF` reads -1, so the setpoint is in tenths of a percent: 1000 is
100.0 %. `WMaxLim_Ena` at 40193 must be 1 or the limit is stored and ignored.
Dispatch to the inverters takes about 20 seconds for a large step, so do not run a
control loop faster than the array can respond.

And remember that any write into 40186–40209 affects the complete installation,
whichever unit id you address.

## License

MIT.
