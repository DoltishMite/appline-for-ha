"""Petline example data: the app's own tour demo (web/kit/tours.json), with its relative dates filled in for a fixed day."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=TZ)


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def day(n: int) -> str:
    return (NOW.date() + timedelta(days=n)).isoformat()


def pets() -> list[dict]:
    return [
        {"id": "pb", "name": "Biscuit", "icon": "🐶", "notes": "", "tasks": [
            {"id": "t1", "name": "Feeding", "icon": "🍽", "type": "meal", "times": ["07:30", "18:00"], "note": "", "days": 0},
            {"id": "t2", "name": "Walk", "icon": "🚶", "type": "meal", "times": ["08:00", "17:00"], "note": ""},
            {"id": "t3", "name": "Flea treatment", "icon": "🐜", "type": "cycle", "days": 30, "next": day(0), "note": "Back of the neck"},
            {"id": "t4", "name": "Worming", "icon": "🪱", "type": "cycle", "days": 90, "next": day(40), "note": ""},
            {"id": "t5", "name": "Vaccination booster", "icon": "💉", "type": "cycle", "days": 365, "next": day(95), "note": ""},
            {"id": "t6", "name": "Vet check-up", "icon": "🩺", "type": "appt", "next": day(3), "time": "10:30", "done": False, "note": ""},
        ], "log": [
            {"id": "l1", "task": "t1", "t": ms(NOW.replace(hour=7, minute=35)), "by": "Alex"},
            {"id": "l2", "task": "t2", "t": ms(NOW.replace(hour=8) - timedelta(days=1)), "by": "Sam"},
        ]},
        {"id": "pm", "name": "Mittens", "icon": "🐱", "notes": "", "tasks": [
            {"id": "m1", "name": "Litter tray", "icon": "🧹", "type": "meal", "times": ["09:00"], "note": ""},
            {"id": "m2", "name": "Flea treatment", "icon": "🐜", "type": "cycle", "days": 30, "next": day(9), "note": ""},
        ], "log": []},
    ]


def sync_doc(p: list[dict] | None = None, shared: dict | None = None) -> dict:
    data = {"petline_pets_v1": json.dumps(pets() if p is None else p), "petline_options_v1": json.dumps({"remindAt": "09:00"})}
    if shared:
        data["petline_shared_v1"] = json.dumps(shared)
    return {"format": 1, "name": "Home", "apps": {"petline": {"t": 1, "data": data}, "worldline": {"t": 1, "data": {}}}, "shared": None}
