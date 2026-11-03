"""Wardyn's state from its agents (siteline_wardyn_v1): networks, nodes, updates, threats, checks and the issues they add up to.
wardyn_agent.json is what Wardyn Agent 2.10 itself makes of Wardyn's tour demo data (NetlineAgent --wardyn-ha, at AGENT_NOW), put
into the link copy here the way the agent does (HaModule.Tick)."""
import json
from datetime import datetime, timezone
from pathlib import Path

from parsers import parse_household, siteline
from parsers.model import BINARY, CONNECTIVITY, COUNT, LATENCY, PROBLEM, SENSOR, Parsed

AGENT = json.loads((Path(__file__).parent / "wardyn_agent.json").read_text(encoding="utf-8"))
AGENT_NOW = 1793700000000
NOW = datetime.fromtimestamp(AGENT_NOW / 1000, tz=timezone.utc)
NET = "b0:19:21:c9:02:68"


def line(nodes=None, nets=None, t=AGENT_NOW):
    """The link copy's siteline_wardyn_v1, as the agent writes it (each line with when it was written, a network's with who wrote it)."""
    n = nodes if nodes is not None else {"demo": dict(AGENT["me"], t=t)}
    w = nets if nets is not None else {k: dict(v, by="demo", t=t) for k, v in AGENT["nets"].items()}
    return {"siteline_wardyn_v1": json.dumps({"v": 1, "nodes": n, "nets": w})}


def test_from_the_agent():
    out = Parsed()
    siteline.parse(line(), {}, NOW, out)
    t = out.things
    node, net = "siteline.node.demo", "siteline.net.b01921c90268"
    assert out.devices[node].name == "Office PC" and out.devices[node].via == "siteline" and out.devices[node].model == "Node · Windows"
    assert out.devices[net].name == "The network via 192.168.1.1"
    assert (t[f"{node}.connected"].platform, t[f"{node}.connected"].kind, t[f"{node}.connected"].state) == (BINARY, CONNECTIVITY, True)
    assert t[f"{node}.updates"].state == 4 and t[f"{node}.updates"].attrs["held_or_put_off"] == 1 and t[f"{node}.updates"].attrs["failed_lately"] == 1
    assert t[f"{node}.restart"].kind == PROBLEM and t[f"{node}.restart"].state is False
    assert t[f"{node}.threats"].state == 0 and t[f"{node}.threats"].attrs["antivirus_on"] is True
    assert t[f"{node}.checks"].state == 1 and t[f"{node}.checks"].attrs["failing"] == ["Disk space"] and t[f"{node}.checks"].attrs["warnings"] == ["Restart pending"]
    assert t[f"{net}.internet"].state is True
    assert (t[f"{net}.latency"].platform, t[f"{net}.latency"].kind, t[f"{net}.latency"].state) == (SENSOR, LATENCY, 9)
    assert t[f"{net}.outages"].state == 2 and t[f"{net}.devices"].state == 2 and t[f"{net}.devices"].attrs["known"] == 3
    assert t["siteline.nodes"].state == 1 and t["siteline.updates"].state == 4
    whats = [i["what"] for i in t["siteline.issues"].attrs["issues"]]
    assert "2 outages in the last day" in whats and "Check failing: Disk space" in whats and "1 update failed to install" in whats
    assert t["siteline.issues"].kind == COUNT and t["siteline.issues"].state == len(whats)
    assert t["siteline.problem"].state is False   # nothing serious


def test_quiet_node_and_old_reading():
    out = Parsed()
    old = AGENT_NOW - 20 * 60000   # 20 minutes without a word
    siteline.parse(line(nets={k: dict(v, by="demo", t=old, at=old) for k, v in AGENT["nets"].items()}, t=old), {}, NOW, out)
    t = out.things
    assert t["siteline.node.demo.connected"].state is False
    assert t["siteline.net.b01921c90268.internet"].state is False and t["siteline.net.b01921c90268.latency"].state is None
    serious = [i["what"] for i in t["siteline.problem"].attrs["serious"]]
    assert t["siteline.problem"].state is True and "No node is connected" in serious and "No recent reading" in serious


def test_down_threats_and_restart():
    me = dict(AGENT["me"], t=AGENT_NOW, threats=2, reboot=True, sec=3)
    net = dict(AGENT["nets"][NET], by="demo", t=AGENT_NOW, up=False)
    out = Parsed()
    siteline.parse(line({"demo": me}, {NET: net}), {}, NOW, out)
    t = out.things
    assert t["siteline.net.b01921c90268.internet"].state is False
    assert t["siteline.node.demo.restart"].state is True and t["siteline.node.demo.threats"].state == 2
    serious = [i["what"] for i in t["siteline.problem"].attrs["serious"]]
    assert serious == ["Internet down", "2 active threats"]
    assert t["siteline.issues"].attrs["issues"][0]["level"] == "serious"


def test_parts_a_node_doesnt_have():
    me = {"name": "Pi", "os": "Linux", "ver": "2.10.0", "nets": [], "checks": {"n": 0, "bad": [], "warn": []}, "t": AGENT_NOW}
    out = Parsed()
    siteline.parse(line({"pi-1": me}, {}), {}, NOW, out)
    keys = set(out.things)
    assert "siteline.node.pi1.connected" in keys
    assert not {"siteline.node.pi1.updates", "siteline.node.pi1.threats", "siteline.node.pi1.checks", "siteline.updates"} & keys


def test_household_newest_line_wins():
    a = line({"demo": dict(AGENT["me"], t=AGENT_NOW - 60000, upd=9)})
    b = line({"demo": dict(AGENT["me"], t=AGENT_NOW, upd=4)})
    out = parse_household([("p1", {"name": "Sam", "apps": {"siteline": {"t": 1, "data": a}}}), ("p2", {"name": "Alex", "apps": {"siteline": {"t": 1, "data": b}}})], {}, {}, NOW)
    assert out.things["siteline.node.demo.updates"].state == 4
    assert len([k for k in out.things if k.endswith(".connected")]) == 1


def test_nothing_or_newer_format():
    for data in ({}, {"siteline_wardyn_v1": "not json"}, {"siteline_wardyn_v1": json.dumps({"v": 2, "nodes": {"x": {"t": AGENT_NOW}}})}):
        out = Parsed()
        siteline.parse(data, {}, NOW, out)
        assert not out.things
