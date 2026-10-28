"""Device registry: tracks what the provisioner knows about each device.

Kept free of any HTTP code so the state logic can be unit tested directly.
"""

from __future__ import annotations

import ipaddress
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

VALID_ACTIONS = {"add", "old", "del"}
MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")


class InvalidEvent(ValueError):
    """Raised when a DHCP event is malformed."""


@dataclass
class DhcpEvent:
    action: str
    mac: str
    ip: str
    hostname: str

    @classmethod
    def from_dict(cls, data: dict) -> "DhcpEvent":
        try:
            action = str(data["action"]).lower()
            mac = str(data["mac"]).lower()
            ip = str(data["ip"])
        except KeyError as exc:
            raise InvalidEvent(f"missing field: {exc.args[0]}") from None
        hostname = str(data.get("hostname") or "")

        if action not in VALID_ACTIONS:
            raise InvalidEvent(f"unknown action: {action!r}")
        if not MAC_RE.match(mac):
            raise InvalidEvent(f"invalid MAC: {mac!r}")
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise InvalidEvent(f"invalid IP: {ip!r}") from None
        return cls(action, mac, ip, hostname)


@dataclass
class DeviceState:
    name: str
    role: str
    expected_ip: str
    status: str = "unseen"  # unseen -> discovered -> (provisioned, Day 3) / released
    mac: str | None = None
    ip: str | None = None
    last_event: str | None = None
    last_seen: str | None = None
    warnings: list[str] = field(default_factory=list)


class Registry:
    def __init__(self, inventory: dict):
        self._lock = threading.Lock()
        self.devices: dict[str, DeviceState] = {
            name: DeviceState(name=name, role=d["role"], expected_ip=str(d["mgmt_ip"]))
            for name, d in inventory["devices"].items()
        }
        self.events: list[dict] = []
        self.max_events = 200

    def handle(self, event: DhcpEvent) -> dict:
        """Apply a DHCP event and return a result describing what happened."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            result = self._apply(event, now)
            self.events.append({"time": now, **asdict(event), **result})
            del self.events[: -self.max_events]
            return result

    def _apply(self, event: DhcpEvent, now: str) -> dict:
        device = self.devices.get(event.hostname)
        if device is None:
            # Never provision something we weren't told about.
            return {"result": "ignored", "reason": "hostname not in inventory"}

        device.mac, device.ip = event.mac, event.ip
        device.last_event, device.last_seen = event.action, now

        if event.ip != device.expected_ip:
            msg = f"got {event.ip}, expected {device.expected_ip}"
            device.warnings.append(msg)
            device.status = "ip-mismatch"
            return {"result": "held", "reason": msg}

        if event.action == "del":
            device.status = "released"
            return {"result": "released"}

        if device.status == "provisioned":
            # Lease renewal on an already-configured device: nothing to do.
            return {"result": "noop", "reason": "already provisioned"}

        device.status = "discovered"
        return {"result": "queued", "reason": "ready for provisioning"}

    def snapshot(self) -> dict:
        with self._lock:
            return {name: asdict(d) for name, d in self.devices.items()}

    def recent_events(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self.events[-limit:])
