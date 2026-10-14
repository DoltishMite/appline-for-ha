"""Opening the apps' sealed documents (pure Python: no Home Assistant imports, so it is tested on its own).

The same scheme as the apps' kit (kit.js HPCloudSync and tools/together.js):
  code  Crockford base 32, normalised (upper case, I/L -> 1, O -> 0, other characters dropped)
  id    sha256_hex("<kind>-id:" + code)      what the server stores it under
  key   sha256("<kind>-key:" + code)         AES-256-GCM
  doc   "1.<z|p>.<iv base64>.<ciphertext+tag base64>"   z: gzipped before sealing
kind is "sync" (a personal sync code) or "together" (one shared thing's code).
Never log a code, key, id or document.
"""
from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ALPHA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
SYNC, TOGETHER = "sync", "together"


class SealError(Exception):
    """A document that can't be opened (wrong code, damaged, or made by a newer version)."""


def norm(code: str | None) -> str:
    c = str(code or "").upper().replace("I", "1").replace("L", "1").replace("O", "0")
    return "".join(ch for ch in c if ch in ALPHA)


@dataclass(frozen=True)
class Keys:
    id: str = field(repr=False)
    key: bytes = field(repr=False)
    kind: str = SYNC


def keys_for(code: str, kind: str = SYNC) -> Keys:
    c = norm(code)
    return Keys(
        id=hashlib.sha256(f"{kind}-id:{c}".encode()).hexdigest(),
        key=hashlib.sha256(f"{kind}-key:{c}".encode()).digest(),
        kind=kind,
    )


def open_doc(doc: str, keys: Keys) -> Any:
    parts = str(doc).split(".")
    if len(parts) != 4:
        raise SealError("not a sealed document")
    ver, z, iv, ct = parts
    if ver != "1":
        raise SealError("made by a newer version of the apps: update the integration")
    try:
        raw = AESGCM(keys.key).decrypt(base64.b64decode(iv), base64.b64decode(ct), None)
    except (InvalidTag, binascii.Error, ValueError) as err:
        raise SealError("can't be opened with this code") from err
    try:
        if z == "z":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as err:
        raise SealError("damaged document") from err
