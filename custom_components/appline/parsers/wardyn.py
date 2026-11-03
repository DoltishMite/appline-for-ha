"""Wardyn's state (0.8.0, 2026-11-03): its networks, nodes, updates, threats and checks -> entities. Pure Python.

Saved data: siteline_wardyn_v1, written into the person's HA link copy by each Wardyn Agent itself (2.10+, the site repo's
agents/NetlineAgent/Home/HaModule.cs), so it is fresh with no page open:
  { v: 1, nodes: { agentId: { name, os, ver, t, nets: [netKey], upd?, sec?, held?, reboot?, failed?, threats?, av?, checks: { n, bad: [names], warn: [names] } } },
    nets:  { netKey: { name, by, t, at?, up?, ms?, out24?, out7?, devs?, on? } } }
A node writes its line at least every 5 minutes, so a line older than CONNECTED_FOR means the node is off or can't reach the server.
Fields a node doesn't have (no 🛡 Patches, no antivirus, a network it doesn't measure) are left out, and so are their entities.
Entities: on the Wardyn device, issues (count, with the list), a problem (anything serious), nodes connected and updates waiting;
a device per network (internet up, latency, outages in 24 hours, devices online) and per node (connected, last check-in, updates
waiting, restart needed, active threats, checks failing). Network and node keys are their own ids (a router's hardware address, the
node's id), so renaming one in Wardyn keeps its entities.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from .common import js
from .model import BINARY, CONNECTIVITY, COUNT, LATENCY, PROBLEM, SENSOR, TIMESTAMP, Device, Parsed, Thing

APP, KEY = "siteline", "siteline_wardyn_v1"
CONNECTED_FOR = timedelta(minutes=15)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())[:40] or "x"


def _num(v) -> int | float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _at(v, tz) -> datetime | None:
    n = _num(v)
    return datetime.fromtimestamp(n / 1000, tz=tz) if n and n > 0 else None


def gather(datas: list[dict[str, str]]) -> tuple[dict, dict]:
    """Every person's copy together (two people with the same Wardyn send the same nodes): the newest line of each node and network."""
    nodes, nets = {}, {}
    for data in datas:
        w = js(data.get(KEY), {})
        if not isinstance(w, dict) or w.get("v") != 1:
            continue
        for src, dst, when in ((w.get("nodes"), nodes, "t"), (w.get("nets"), nets, "at")):
            for k, row in (src or {}).items() if isinstance(src, dict) else ():
                if isinstance(row, dict) and isinstance(k, str) and ((_num(row.get(when)) or _num(row.get("t")) or 0) >= ((_num(dst[k].get(when)) or _num(dst[k].get("t")) or 0) if k in dst else -1)):
                    dst[k] = row
    return nodes, nets


def emit(datas: list[dict[str, str]], now: datetime, out: Parsed, app_name: str | None, device_name: str) -> None:
    nodes, nets = gather(datas)
    if not nodes and not nets:
        return
    out.add_device(Device(APP, app_name or device_name, device_name))
    tz = now.tzinfo
    issues: list[dict] = []
    connected = {k: (lambda at: at is not None and now - at <= CONNECTED_FOR)(_at(n.get("t"), tz)) for k, n in nodes.items()}
    names = {k: str(n.get("name") or "A node") for k, n in nodes.items()}

    for k, n in sorted(nets.items()):
        dev, name = f"{APP}.net.{_slug(k)}", str(n.get("name") or "A network")
        out.add_device(Device(dev, name, "Network", via=APP))
        measured = _at(n.get("at"), tz)
        attrs = {"network": k, "measured": measured.isoformat() if measured else None, "by": names.get(n.get("by"), None)}
        if isinstance(n.get("up"), bool):
            # (a measurement over 15 minutes old says nothing about now: the node measuring it has gone quiet)
            up = n["up"] and measured is not None and now - measured <= CONNECTED_FOR
            out.add(Thing(f"{dev}.internet", APP, BINARY, CONNECTIVITY, "net_internet", up, {}, attrs, "mdi:web" if up else "mdi:web-off"))
            if not up:
                issues.append({"level": "serious", "what": "Internet down" if n["up"] is False else "No recent reading", "where": name})
            ms = _num(n.get("ms"))
            out.add(Thing(f"{dev}.latency", APP, SENSOR, LATENCY, "net_latency", ms if up else None, {}, {}, "mdi:timer-outline"))
            o24, o7 = _num(n.get("out24")) or 0, _num(n.get("out7")) or 0
            out.add(Thing(f"{dev}.outages", APP, SENSOR, COUNT, "net_outages", o24, {}, {"last_7_days": o7}, "mdi:lan-disconnect"))
            if o24:
                issues.append({"level": "worth a look", "what": f"{o24} outage{'s' if o24 != 1 else ''} in the last day", "where": name})
        if _num(n.get("devs")) is not None:
            out.add(Thing(f"{dev}.devices", APP, SENSOR, COUNT, "net_devices_online", _num(n.get("on")) or 0, {}, {"known": n["devs"]}, "mdi:devices"))

    waiting = security = 0
    for k, n in sorted(nodes.items()):
        dev, name, on = f"{APP}.node.{_slug(k)}", names[k], connected[k]
        out.add_device(Device(dev, name, "Node" + (f" · {n['os']}" if isinstance(n.get("os"), str) else ""), via=APP))
        seen = _at(n.get("t"), tz)
        out.add(Thing(f"{dev}.connected", APP, BINARY, CONNECTIVITY, "node_connected", on, {}, {"version": n.get("ver"), "last_seen": seen.isoformat() if seen else None},
                      "mdi:lan-connect" if on else "mdi:lan-disconnect"))
        out.add(Thing(f"{dev}.seen", APP, SENSOR, TIMESTAMP, "node_last_seen", seen, {}, {}, "mdi:clock-check-outline", enabled=False))
        if not on:
            issues.append({"level": "worth a look", "what": "Not reporting", "where": name})
        if _num(n.get("upd")) is not None:
            u, s = int(n["upd"]), int(_num(n.get("sec")) or 0)
            waiting += u; security += s
            out.add(Thing(f"{dev}.updates", APP, SENSOR, COUNT, "node_updates", u, {},
                          {"security": s, "held_or_put_off": _num(n.get("held")) or 0, "failed_lately": _num(n.get("failed")) or 0}, "mdi:package-up"))
            out.add(Thing(f"{dev}.restart", APP, BINARY, PROBLEM, "node_restart", bool(n.get("reboot")), {}, {}, "mdi:restart-alert"))
            if s:
                issues.append({"level": "worth a look", "what": f"{s} security update{'s' if s != 1 else ''} waiting", "where": name})
            if n.get("reboot"):
                issues.append({"level": "worth a look", "what": "Restart needed to finish updates", "where": name})
            if _num(n.get("failed")):
                issues.append({"level": "worth a look", "what": f"{n['failed']} update{'s' if n['failed'] != 1 else ''} failed to install", "where": name})
        if _num(n.get("threats")) is not None:
            th = int(n["threats"])
            out.add(Thing(f"{dev}.threats", APP, SENSOR, COUNT, "node_threats", th, {}, {"antivirus_on": n.get("av")}, "mdi:shield-bug-outline" if th else "mdi:shield-check-outline"))
            if th:
                issues.append({"level": "serious", "what": f"{th} active threat{'s' if th != 1 else ''}", "where": name})
        c = n.get("checks") if isinstance(n.get("checks"), dict) else {}
        if _num(c.get("n")):
            bad = [str(x) for x in c.get("bad") or [] if isinstance(x, str)]
            warn = [str(x) for x in c.get("warn") or [] if isinstance(x, str)]
            out.add(Thing(f"{dev}.checks", APP, SENSOR, COUNT, "node_checks_failing", len(bad), {}, {"failing": bad, "warnings": warn, "checks": c["n"]},
                          "mdi:clipboard-alert-outline" if bad else "mdi:clipboard-check-outline"))
            issues.extend({"level": "worth a look", "what": f"Check failing: {b}", "where": name} for b in bad)

    if nodes and not any(connected.values()):
        issues.insert(0, {"level": "serious", "what": "No node is connected", "where": "Wardyn"})
    issues.sort(key=lambda i: i["level"] != "serious")
    out.add(Thing(f"{APP}.issues", APP, SENSOR, COUNT, "wardyn_issues", len(issues), {}, {"issues": issues[:40]}, "mdi:alert-circle-outline" if issues else "mdi:check-circle-outline"))
    serious = [i for i in issues if i["level"] == "serious"]
    out.add(Thing(f"{APP}.problem", APP, BINARY, PROBLEM, "wardyn_problem", bool(serious), {}, {"serious": serious[:20]}, "mdi:shield-alert-outline" if serious else "mdi:shield-check-outline"))
    if nodes:
        out.add(Thing(f"{APP}.nodes", APP, SENSOR, COUNT, "wardyn_nodes_connected", sum(connected.values()), {},
                      {"nodes": len(nodes), "not_connected": [names[k] for k, v in connected.items() if not v]}, "mdi:server-network"))
    if any(_num(n.get("upd")) is not None for n in nodes.values()):
        out.add(Thing(f"{APP}.updates", APP, SENSOR, COUNT, "wardyn_updates", waiting, {}, {"security": security}, "mdi:package-up"))
