"""Fixtures shared by the tests."""

import socket
from typing import Any

import pytest
from helpers import REFERENCE

from owstudio.core import i18n
from owstudio.core.case.model import Case


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def no_warm_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """No background computation of results between tests (see postproc/results.py)."""
    from owstudio.core.postproc import results

    monkeypatch.setattr(results, "WARMING", False)


@pytest.fixture(autouse=True)
def english() -> None:
    """Texts in English unless a test asks for French (the application's default is French)."""
    i18n.set_default("en")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach the internet: a mistake in a simulated engine must not turn into real
    downloads of input data (GFS files are 500 MB each)."""

    connect, connect_ex, create_connection = (
        socket.socket.connect,
        socket.socket.connect_ex,
        socket.create_connection,
    )

    def local(address: Any) -> bool:
        # Event loops talk to themselves through loopback socket pairs (on Windows)
        host = address[0] if isinstance(address, tuple) else address
        return host in ("127.0.0.1", "::1", "localhost") or not isinstance(address, tuple)

    def guarded(original: Any) -> Any:
        def call(self: Any, address: Any, *args: Any, **kwargs: Any) -> Any:
            if not local(address):
                raise NetworkBlocked(f"Network access during a test: {address}")
            return original(self, address, *args, **kwargs)

        return call

    def guarded_create(address: Any, *args: Any, **kwargs: Any) -> Any:
        if not local(address):
            raise NetworkBlocked(f"Network access during a test: {address}")
        return create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded(connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(connect_ex))
    monkeypatch.setattr(socket, "create_connection", guarded_create)


@pytest.fixture
def reference_case() -> Case:
    return Case.from_yaml(REFERENCE)


@pytest.fixture
def reference() -> dict[str, Any]:
    return Case.from_yaml(REFERENCE).model_dump(mode="json")
