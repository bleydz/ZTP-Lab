#!/bin/sh
# Called by dnsmasq (dhcp-script) whenever a lease changes:
#   lease-hook.sh <add|old|del> <mac> <ip> [hostname]
#
#   add - new lease
#   old - existing lease renewed or seen again (e.g. after dnsmasq restart)
#   del - lease released or expired
#
# Forwards the event to the provisioner. It must never block or fail
# dnsmasq, so errors are logged and the script always exits 0.

PROVISIONER_URL="${PROVISIONER_URL:-http://10.0.0.2:8080/dhcp-event}"

action="$1"
mac="$2"
ip="$3"
hostname="${4:-}"

case "$action" in
  add|old|del) ;;
  *) exit 0 ;;  # ignore init/tftp/other actions
esac

payload=$(printf '{"action":"%s","mac":"%s","ip":"%s","hostname":"%s"}' \
  "$action" "$mac" "$ip" "$hostname")

if ! curl -fsS --max-time 3 -H 'Content-Type: application/json' \
     -d "$payload" "$PROVISIONER_URL" >/dev/null 2>&1; then
  logger -t lease-hook "failed to notify provisioner: $payload" 2>/dev/null \
    || echo "lease-hook: failed to notify provisioner: $payload" >&2
fi

exit 0
