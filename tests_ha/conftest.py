import pathlib
import sys

import pytest
import pytest_socket

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "tests"))

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def allow_local_sockets():
    """The simulated ECU is a real TCP server on 127.0.0.1."""
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(["127.0.0.1"], allow_unix_socket=True)
    yield
