"""Petline's calendars."""
from datetime import date, timedelta

from fixtures import NOW, pets, sync_doc
from parsers import parse_sync
from parsers.petline import events


def cal(parsed, key="petline.calendar"):
    return parsed.things[key].data


def test_calendars_exist():
    p = parse_sync(sync_doc(), {}, NOW)
    assert p.things["petline.calendar"].enabled is True
    assert p.things["petline.pb.calendar"].enabled is False and p.things["petline.pm.calendar"].enabled is False


def test_today_and_tomorrow():
    p = parse_sync(sync_doc(), {}, NOW)
    start = NOW.replace(hour=0)
    ev = events(cal(p), start, start + timedelta(days=2), NOW)
    s = [(e.summary, e.start) for e in ev]
    assert ("✓ Biscuit: Feeding (Alex)", NOW.replace(hour=7, minute=35)) in s           # done, from the log
    assert ("Biscuit: Feeding", NOW.replace(hour=7, minute=30)) not in s               # that slot is ticked: not repeated
    assert ("Biscuit: Feeding", NOW.replace(hour=18)) in s                             # tea still to come
    assert ("Biscuit: Walk", NOW.replace(hour=8)) in s                                 # late, still shown at its time
    assert ("Biscuit: Feeding", NOW.replace(hour=7, minute=30) + timedelta(days=1)) in s
    assert ("Biscuit: Flea treatment", NOW.date()) in s                                # all day, due today
    assert ("Mittens: Litter tray", NOW.replace(hour=9) + timedelta(days=1)) in s
    assert all(ev[i].uid != ev[j].uid for i in range(len(ev)) for j in range(i))


def test_repeats_and_appointments():
    p = parse_sync(sync_doc(), {}, NOW)
    ev = events(cal(p), NOW, NOW + timedelta(days=100), NOW, daily=False)
    flea = [e.start for e in ev if e.summary == "Biscuit: Flea treatment"]
    assert flea == [NOW.date() + timedelta(days=30 * k) for k in (0, 1, 2, 3)]        # today (all day, so it overlaps now), then every 30 days
    vet = [e for e in ev if e.summary == "Biscuit: Vet check-up"]
    assert len(vet) == 1 and vet[0].start == NOW.replace(hour=10, minute=30) + timedelta(days=3)
    assert vet[0].end - vet[0].start == timedelta(hours=1)
    assert not any("Feeding" in e.summary or "Walk" in e.summary for e in ev)          # daily routines left out


def test_overdue_goes_on_today():
    p = pets()
    p[0]["tasks"][2]["next"] = (NOW.date() - timedelta(days=5)).isoformat()
    parsed = parse_sync(sync_doc(p), {}, NOW)
    ev = events(cal(parsed, "petline.pb.calendar"), NOW.replace(hour=0), NOW + timedelta(days=40), NOW, daily=False)
    flea = [(e.summary, e.start) for e in ev if "Flea" in e.summary]
    assert flea[0] == (f"Flea treatment (overdue since {(NOW.date() - timedelta(days=5)).isoformat()})", NOW.date())
    assert flea[1] == ("Flea treatment", NOW.date() + timedelta(days=30))


def test_window_is_respected():
    p = parse_sync(sync_doc(), {}, NOW)
    lo, hi = NOW + timedelta(days=10), NOW + timedelta(days=11)
    for e in events(cal(p), lo, hi, NOW):
        s = e.start if not isinstance(e.start, date) or hasattr(e.start, "hour") else None
        if s is not None:
            assert lo <= s < hi or e.end > lo
