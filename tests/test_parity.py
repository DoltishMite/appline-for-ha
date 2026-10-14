"""The Python port of Petline's status() must agree with the app's own code (pets.html), at many moments across a few days."""
import json
import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import SITE
from fixtures import NOW, ms, pets
from parsers.petline import status

PAGE = SITE / "web" / "petline" / "pets.html"
JS = Path(__file__).parent / "js" / "petline-status.mjs"


@pytest.mark.skipif(not shutil.which("node") or not PAGE.exists(), reason="needs node and the apps' project next to this repo")
def test_status_matches_the_app(tmp_path):
    p = pets()
    p[0]["log"].append({"id": "l5", "task": "t3", "t": ms(NOW - timedelta(days=29)), "by": "Sam"})   # flea: done 29 days ago
    moments = [NOW.replace(hour=0, minute=5) + timedelta(minutes=37 * i) for i in range(0, 5 * 24 * 60 // 37)]
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"pets": p, "at": [ms(m) for m in moments]}), encoding="utf-8")
    env = dict(os.environ, TZ="Europe/London")
    r = subprocess.run(["node", str(JS), str(PAGE), str(cases)], capture_output=True, text=True, env=env, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    js = json.loads(r.stdout)
    bad = []
    for m in moments:
        for pet in p:
            for t in pet["tasks"]:
                want, got = js[f"{ms(m)}|{pet['id']}|{t['id']}"], status(pet, t, m)["state"]
                if want != got:
                    bad.append((m.isoformat(), pet["id"], t["id"], want, got))
    assert not bad, bad[:10]
    assert len(js) > 1000
