TOPO   := topology/ztp-lab.clab.yml
LAB    := ztp-lab
BRIDGE := br-prov
DEVICES := spine1 leaf1 leaf2

.PHONY: up down bridge dhcp leases

bridge:
	@ip link show $(BRIDGE) >/dev/null 2>&1 || \
		(sudo ip link add $(BRIDGE) type bridge && sudo ip link set $(BRIDGE) up)

up: bridge
	sudo containerlab deploy -t $(TOPO)

# Each device requests an address, sending its hostname so dnsmasq
# matches it to a reservation.
dhcp:
	@for d in $(DEVICES); do \
		echo "==> $$d"; \
		sudo docker exec clab-$(LAB)-$$d udhcpc -i eth1 -x hostname:$$d -n -q; \
	done

leases:
	sudo docker exec clab-$(LAB)-dhcp cat /var/lib/misc/dnsmasq.leases

down:
	sudo containerlab destroy -t $(TOPO) --cleanup
	-sudo ip link del $(BRIDGE)
