"""Documents sealed by the kit's own scheme (make-vector.mjs, in Node) must open here."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hpcrypto import SYNC, TOGETHER, SealError, keys_for, norm, open_doc

MAKE = Path(__file__).parent / "js" / "make-vector.mjs"
needs_node = pytest.mark.skipif(not shutil.which("node") or not MAKE.exists(), reason="needs node and make-vector.mjs")


def seal(tmp_path, obj, *flags):
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps(obj), encoding="utf-8")
    subprocess.run(["node", str(MAKE), str(src), str(out), *flags], check=True, capture_output=True)
    return json.loads(out.read_text(encoding="utf-8"))


def test_norm():
    assert norm("k7qf-2m9x io") == "K7QF2M9X10"
    assert norm("abcu") == "ABC"   # U isn't in the alphabet
    assert norm(None) == ""


def test_keys_repr_hides_secrets():
    k = keys_for("ABCD-EFGH-JKMN-PQRS-TVWX")
    assert k.id not in repr(k) and str(k.key) not in repr(k)


@needs_node
@pytest.mark.parametrize("flags,kind", [((), SYNC), (("--plain",), SYNC), (("--share",), TOGETHER), (("--share", "--plain"), TOGETHER)])
def test_open_kit_vectors(tmp_path, flags, kind):
    obj = {"format": 1, "apps": {"petline": {"t": 1, "data": {"petline_pets_v1": "[]"}}}, "text": "émoji 🐶"}
    v = seal(tmp_path, obj, *flags)
    keys = keys_for(v["code"], kind)
    assert keys.id == v["id"]
    assert open_doc(v["doc"], keys) == obj
    assert v["doc"].split(".")[1] == ("p" if "--plain" in flags else "z")


@needs_node
def test_wrong_code_and_newer_version(tmp_path):
    v = seal(tmp_path, {"a": 1})
    with pytest.raises(SealError):
        open_doc(v["doc"], keys_for("ZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZ"))
    with pytest.raises(SealError, match="newer"):
        open_doc("2" + v["doc"][1:], keys_for(v["code"]))
    with pytest.raises(SealError):
        open_doc("rubbish", keys_for(v["code"]))
