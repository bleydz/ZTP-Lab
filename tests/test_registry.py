import pytest

from registry import DhcpEvent, InvalidEvent, Registry

INVENTORY = {
    "devices": {
        "leaf1": {"role": "leaf", "mgmt_ip": "10.0.0.11"},
        "spine1": {"role": "spine", "mgmt_ip": "10.0.0.21"},
    }
}
MAC = "aa:c1:ab:00:00:01"


def ev(action="add", hostname="leaf1", ip="10.0.0.11", mac=MAC):
    return DhcpEvent.from_dict(
        {"action": action, "mac": mac, "ip": ip, "hostname": hostname}
    )


@pytest.fixture
def reg():
    return Registry(INVENTORY)


def test_all_devices_start_unseen(reg):
    assert {d["status"] for d in reg.snapshot().values()} == {"unseen"}


def test_new_lease_queues_known_device(reg):
    assert reg.handle(ev())["result"] == "queued"
    assert reg.snapshot()["leaf1"]["status"] == "discovered"


def test_unknown_device_is_ignored(reg):
    assert reg.handle(ev(hostname="rogue"))["result"] == "ignored"
    assert "rogue" not in reg.snapshot()


def test_wrong_ip_is_held_not_provisioned(reg):
    result = reg.handle(ev(ip="10.0.0.120"))
    assert result["result"] == "held"
    assert reg.snapshot()["leaf1"]["status"] == "ip-mismatch"


def test_renewal_of_provisioned_device_is_noop(reg):
    reg.handle(ev())
    reg.devices["leaf1"].status = "provisioned"
    assert reg.handle(ev(action="old"))["result"] == "noop"


def test_release_marks_device_released(reg):
    reg.handle(ev())
    assert reg.handle(ev(action="del"))["result"] == "released"


def test_events_are_capped(reg):
    reg.max_events = 5
    for _ in range(20):
        reg.handle(ev(action="old"))
    assert len(reg.recent_events(100)) == 5


@pytest.mark.parametrize(
    "bad",
    [
        {"action": "add", "mac": MAC},                                  # no ip
        {"action": "boot", "mac": MAC, "ip": "10.0.0.11"},              # bad action
        {"action": "add", "mac": "not-a-mac", "ip": "10.0.0.11"},       # bad mac
        {"action": "add", "mac": MAC, "ip": "10.0.0.999"},              # bad ip
    ],
)
def test_malformed_events_rejected(bad):
    with pytest.raises(InvalidEvent):
        DhcpEvent.from_dict(bad)
