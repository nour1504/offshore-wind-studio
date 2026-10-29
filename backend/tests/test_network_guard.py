"""The test suite cannot reach the internet (see conftest.no_network)."""

import socket

import pytest
from conftest import NetworkBlocked


def test_remote_connections_are_refused() -> None:
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("noaa-gfs-bdp-pds.s3.amazonaws.com", 443), timeout=1)
