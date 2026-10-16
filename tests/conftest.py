"""Load the pure modules (models, hub, detect) without importing Home Assistant."""
import importlib.util
import pathlib
import sys
import types

PKG = "ecusunspec"
ROOT = pathlib.Path(__file__).parents[1] / "custom_components" / "apsystems_ecu_sunspec"

pkg = types.ModuleType(PKG)
pkg.__path__ = [str(ROOT)]
sys.modules[PKG] = pkg
for name in ("models", "hub", "detect"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{PKG}.{name}"] = mod
    spec.loader.exec_module(mod)
sys.path.insert(0, str(pathlib.Path(__file__).parent))
