"""End-to-end: run the real hook script against a real provisioner server."""

import json
import os
import subprocess
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from registry import Registry
from server import make_handler

HOOK = Path(__file__).resolve().parents[1] / "dhcp" / "lease-hook.sh"
INVENTORY = {"devices": {"leaf1": {"role": "leaf", "mgmt_ip": "10.0.0.11"}}}


@pytest.fixture
def server():
    registry = Registry(INVENTORY)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(registry))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", registry
    httpd.shutdown()


def run_hook(url, *args):
    env = {**os.environ, "PROVISIONER_URL": f"{url}/dhcp-event"}
    return subprocess.run(["sh", str(HOOK), *args], env=env, timeout=10)


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.load(r)


def test_hook_delivers_lease_to_provisioner(server):
    url, registry = server
    assert run_hook(url, "add", "aa:c1:ab:00:00:01", "10.0.0.11", "leaf1").returncode == 0
    assert get(f"{url}/devices")["leaf1"]["status"] == "discovered"
    assert get(f"{url}/events")[-1]["result"] == "queued"


def test_hook_ignores_non_lease_actions(server):
    url, registry = server
    run_hook(url, "tftp", "aa:c1:ab:00:00:01", "10.0.0.11")
    assert registry.recent_events() == []


def test_hook_never_fails_dnsmasq_when_provisioner_down():
    result = run_hook("http://127.0.0.1:9", "add", "aa:c1:ab:00:00:01", "10.0.0.11", "leaf1")
    assert result.returncode == 0
