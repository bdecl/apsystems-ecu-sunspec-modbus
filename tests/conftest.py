"""Load the pure decoding module without importing Home Assistant.

hub and detect sit on Home Assistant's modbus integration; they are covered by
the end-to-end tests in tests_ha.
"""
import importlib.util
import pathlib
import sys
import types

PKG = "ecusunspec"
ROOT = pathlib.Path(__file__).parents[1] / "custom_components" / "apsystems_ecu_sunspec"

pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = pkg
for name in ("models",):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{PKG}.{name}"] = mod
    spec.loader.exec_module(mod)
sys.path.insert(0, str(pathlib.Path(__file__).parent))
