"""Provisioner HTTP service.

Receives DHCP lease events from the dnsmasq hook and tracks device state.

  POST /dhcp-event   lease event from lease-hook.sh
  GET  /devices      current state of every device in the inventory
  GET  /events       recent events (?limit=N)
  GET  /healthz      liveness check

Day 3 hooks Ansible onto the "queued" result.
"""

from __future__ import annotations

import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import yaml

from registry import DhcpEvent, InvalidEvent, Registry

log = logging.getLogger("provisioner")
MAX_BODY = 4096


def make_handler(registry: Registry):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body) -> None:
            data = json.dumps(body, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/healthz":
                self._send(200, {"status": "ok"})
            elif url.path == "/devices":
                self._send(200, registry.snapshot())
            elif url.path == "/events":
                try:
                    limit = int(parse_qs(url.query).get("limit", ["50"])[0])
                except ValueError:
                    return self._send(400, {"error": "limit must be an integer"})
                self._send(200, registry.recent_events(limit))
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/dhcp-event":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_BODY:
                return self._send(400, {"error": "bad body length"})
            try:
                event = DhcpEvent.from_dict(json.loads(self.rfile.read(length)))
            except (json.JSONDecodeError, InvalidEvent, TypeError) as exc:
                log.warning("rejected event: %s", exc)
                return self._send(400, {"error": str(exc)})

            result = registry.handle(event)
            log.info("%s %s %s %s -> %s", event.action, event.hostname or "-",
                     event.ip, event.mac, result)
            self._send(200, result)

        def log_message(self, fmt, *args) -> None:  # route access logs via logging
            log.debug("%s - %s", self.address_string(), fmt % args)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inventory", default="/inventory/devices.yml")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    with open(args.inventory) as f:
        registry = Registry(yaml.safe_load(f))

    server = ThreadingHTTPServer((args.host, args.port), make_handler(registry))
    log.info("listening on %s:%d with %d devices", args.host, args.port,
             len(registry.devices))
    server.serve_forever()


if __name__ == "__main__":
    main()
