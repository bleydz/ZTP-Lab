# ztp-lab

A self-contained lab for **zero-touch provisioning (ZTP) of network devices** using DHCP and Ansible.

When a device boots on the provisioning network it requests an address over DHCP. The DHCP server hands out a fixed address per device and fires an event; a provisioning service picks that up and runs Ansible to push the device's intended configuration, then verifies it. No manual console setup.

This mirrors a workflow I run on real datacentre switches, rebuilt here on open tooling so anyone can run it on a laptop.

## Topology

```
                 provisioning network 10.0.0.0/24 (br-prov)
   ┌──────────┬──────────────┬──────────┬──────────┬──────────┐
   │          │              │          │          │          │
 dhcp     provisioner      spine1     leaf1      leaf2
10.0.0.1   10.0.0.2       .21 (DHCP) .11 (DHCP) .12 (DHCP)
(dnsmasq)  (Ansible)
                          spine1 ── leaf1   (fabric links, configured by Ansible)
                          spine1 ── leaf2
```

- **Devices:** [FRRouting](https://frrouting.org/) containers acting as switches/routers
- **DHCP:** dnsmasq with per-device reservations
- **Lab orchestration:** [containerlab](https://containerlab.dev/)

## Requirements

- Linux host with Docker
- containerlab (`bash -c "$(curl -sL https://get.containerlab.dev)"`)
- `make`, `sudo` (to create the provisioning bridge)

## Quick start

```bash
make up        # create bridge + deploy lab
make dhcp      # devices request addresses on the provisioning network
make leases    # show what the DHCP server handed out
make devices   # provisioner's view of each device
make events    # recent lease events and what the provisioner did with them
make down      # tear everything down
```

## How a device is discovered

```
device boots ──DHCPDISCOVER──▶ dnsmasq ──lease change──▶ lease-hook.sh ──POST /dhcp-event──▶ provisioner
                                (fixed IP per hostname)    (add/old/del)                       (checks inventory)
```

The provisioner only acts on devices listed in `inventory/devices.yml`:

| Lease event | Device state | Result |
|---|---|---|
| Hostname not in inventory | - | `ignored` - never configure unknown kit |
| Known device, wrong IP | `ip-mismatch` | `held` - reservation is broken, needs a human |
| Known device, new lease | `discovered` | `queued` for provisioning |
| Renewal on a provisioned device | unchanged | `noop` |
| Lease released/expired | `released` | `released` |

The hook always exits 0, so a provisioner outage can never stop dnsmasq handing out leases.

## Development

```bash
pip install -r requirements-dev.txt
make test      # unit tests + hook-to-server end-to-end test
make lint      # shellcheck
```

## Roadmap

- [x] Lab topology, provisioning network, DHCP reservations
- [x] Provisioning service reacting to DHCP lease events
- [ ] Ansible roles generating FRR config from YAML intent
- [ ] Post-provisioning verification (interfaces, OSPF adjacencies, routes)
- [ ] CI: lint + full lab test in GitHub Actions
- [ ] Failure scenarios and write-ups (DHCP exhaustion, wrong config, unreachable device)

## License

MIT
