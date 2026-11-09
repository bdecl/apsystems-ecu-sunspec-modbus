"""Print the requirements of the installed Home Assistant's modbus integration.

The integration depends on Home Assistant's modbus integration, whose libraries
(modbus-connection, tmodbus, pymodbus) the test packages do not install. Reading
them from the installed release keeps each tested Home Assistant version on the
library versions it actually ships with.

Home Assistant is located without being imported.
"""
import importlib.util
import json
import pathlib

root = pathlib.Path(importlib.util.find_spec("homeassistant").submodule_search_locations[0])
manifest = json.loads((root / "components" / "modbus" / "manifest.json").read_text())
print("\n".join(manifest["requirements"]))
