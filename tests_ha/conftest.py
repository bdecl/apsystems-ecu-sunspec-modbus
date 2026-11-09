import importlib.util
import pathlib
import sys

import pytest
import pytest_socket

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "tests"))

# Home Assistant 2026.11 and newer: pytest-homeassistant, published by Home
# Assistant core, loads itself. Home Assistant 2026.10 only exists for the
# retired pytest-homeassistant-custom-component, which must be named here.
if importlib.util.find_spec("pytest_homeassistant") is None:
    pytest_plugins = ["pytest_homeassistant_custom_component"]
else:
    # Its default configuration directory is tests/testing_config in the
    # repository, where Home Assistant would write its default blueprints.
    @pytest.fixture
    def hass_config_dir(hass_tmp_config_dir):
        return hass_tmp_config_dir


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def allow_local_sockets():
    """The simulated ECU is a real TCP server on 127.0.0.1."""
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(["127.0.0.1"], allow_unix_socket=True)
    yield
