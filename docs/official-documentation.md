# Official documentation, and where it differs from the device

The manufacturer's reference for this interface is a PDF titled **"SunSpec Modbus",
revision 3.3**, published by APsystems in their document library. It is copyrighted
and is therefore not redistributed here, only linked. The register addresses, model
numbers and frame formats it contains are facts and are reproduced throughout this
repository, in more complete and more accurate form.

- Document library: https://emea.apsystems.com/document-library/
- SunSpec Modbus, rev. 3.3 (PDF):
  https://global.apsystems.com/wp-content/uploads/2025/01/SunSpec-Modbus.pdf
- SunSpec Modbus, rev. 3.2 (PDF), the previous revision:
  https://global.apsystems.com/wp-content/uploads/2024/03/SunSpec-Modbus.pdf

## What the official document covers

- How to enable the interface: EMA Manager, ECU app, Workspace, Modbus
  Configuration. Switch to On, a baud rate for RTU, and an address per inverter.
- That both Modbus RTU (RS485) and Modbus TCP are supported, that TCP needs no
  RS485 wiring, and that port 502 is fixed.
- Worked example frames for reading the Common model, the single-phase and
  three-phase inverter models in both integer and float form, the operating state
  and event registers, and for writing the connect/disconnect control.
- The compatibility table below.

## Which ECUs are supported, per the manufacturer

| Model | ID prefix | Minimum firmware |
|---|---|---|
| ECU-R | 2160XXXXXXXX | 1.3.7 |
| ECU-R | 2162XXXXXXXX | 2.0.2 |
| ECU-B | 2163XXXXXXXX | not supported |
| ECU-C | 215XXXXXXXXX | C1.1.3 |

## Where it falls short

| Subject | Official document | Measured |
|---|---|---|
| Implementation status | Not stated for any field | Roughly half the fields of the inverter models return a not-implemented sentinel, and twenty-one of the twenty-four control registers are inert |
| DC data block | Given as an address, with no context | It is a model 114 header at 40212, placed *after* the end-of-chain marker at 40210, so a conforming client never reaches it |
| Scope of the controls | Implied per-inverter, since they are addressed by inverter unit id | Global: any write curtails or disconnects the whole array |
| Status in the float model | Example frames shown for the integer model only | `St` and `Evt1` are unimplemented in model 113, so the float model has no status at all |
| Meter data | Not mentioned | There is none. No meter model, no reserved unit id, no grid measurement anywhere on Modbus |
| Error behaviour | Not mentioned | An out-of-range address returns silence, not a Modbus exception |
| Address space | Not mentioned | Readable from 40000 to 40300 inclusive; nothing responds above |

None of this is exotic. It is the ordinary gap between a document written to show
that a feature exists and what you need to actually build against it.

## Links

### Manufacturer

- Document library, worldwide: https://global.apsystems.com/
- EMEA site: https://emea.apsystems.com/
- ECU-C product page: https://usa.apsystems.com/product/ecu-c/
- ECU-C quick installation guide (PDF):
  https://global.apsystems.com/wp-content/uploads/2023/12/4271803041_APsystems-Energy-Communication-Unit-ECU-C-quick-installation-guide_rev4.0_2023-10-19.pdf
- EMA app user manual, PV version (PDF):
  https://global.apsystems.com/wp-content/uploads/2024/03/EMA-APP-User-Manual-PV-Version-_V8.9.1_20240221_EN.pdf

- SunSpec Modbus, rev. 3.3 (PDF):
  https://global.apsystems.com/wp-content/uploads/2025/01/SunSpec-Modbus.pdf

### Support

- EMEA: info.emea@APsystems.com, +31 (0)85 3018499, Karspeldreef 8, 1101 CJ
  Amsterdam, Netherlands
- 24/7 line: +86 573 83986967

### Community

These projects use the ECU's proprietary port 8899 protocol, not SunSpec. They are
the right tool for per-panel monitoring; this repository is about the control path.

- APsystems ECU Reader for Home Assistant, actively maintained, with a wiki that
  documents the 8899 protocol: https://github.com/HAEdwin/homeassistant-apsystems_ecu_reader
- The older integration it descends from, whose README carries a useful warning
  about ECU outages on ECU-C and later ECU-R firmware:
  https://github.com/ksheumaker/homeassistant-apsystems_ecur
- A SunSpec bridge that runs a small server on the ECU itself, serving port 1502:
  https://github.com/bolkedebruin/apsystems-sunspec
- Direct radio decoding of YC600, QS1 and DS3 inverters, bypassing the ECU:
  https://github.com/patience4711/read-APSystems-YC600-QS1-DS3
- The Dutch forum thread where much of the original protocol work was done:
  https://gathering.tweakers.net/forum/list_messages/2032302

### Specification

- SunSpec Alliance: https://sunspec.org/ — for the standard definitions of models
  1, 103, 113 and 123. Model 114 is not a SunSpec model.
