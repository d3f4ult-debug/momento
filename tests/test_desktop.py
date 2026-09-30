"""
Tests for desktop runtime wrapper components in desktop.py.
"""

import socket
import pytest
from desktop import find_free_port, is_port_available, UvicornServerThread, wait_for_server


def test_find_free_port():
    port = find_free_port(start_port=8100)
    assert isinstance(port, int)
    assert 8100 <= port < 8200
    assert is_port_available("127.0.0.1", port)


def test_is_port_available_on_occupied_port():
    # Bind a temporary socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    occupied_port = sock.getsockname()[1]
    try:
        # Should not be available
        assert not is_port_available("127.0.0.1", occupied_port)
    finally:
        sock.close()


def test_server_thread_lifecycle_and_health_check():
    port = find_free_port(start_port=8200)
    thread = UvicornServerThread(host="127.0.0.1", port=port)
    thread.start()

    try:
        ready = wait_for_server(f"http://127.0.0.1:{port}", timeout=8.0)
        assert ready is True
    finally:
        thread.stop()
