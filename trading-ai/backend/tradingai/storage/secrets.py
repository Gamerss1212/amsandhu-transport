"""Credential vault (section 182). Keys never go into source files, logs, API responses or the browser after saving.

* Windows (the target): each secret is encrypted with DPAPI (CryptProtectData), bound to the Windows user account,
  with an extra per-vault entropy value. Another Windows user, or a copy of the file on another PC, cannot decrypt it.
* Elsewhere (development): stored in an owner-only file (chmod 600) and reported honestly as NOT encrypted.

Only the public part (for example the first and last 4 characters of a key id) is ever shown again.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Optional


class VaultError(RuntimeError):
    pass


def _dpapi(data: bytes, entropy: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(b: bytes) -> BLOB:
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    src, ent, out = _blob(data), _blob(entropy), BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out))  # UI_FORBIDDEN
    if not ok:
        raise VaultError("Windows DPAPI refused the operation (another Windows user, or a copied vault?)")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


class Vault:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.windows = sys.platform == "win32"
        ent = self.folder / ".entropy"
        if not ent.exists():
            ent.write_bytes(os.urandom(32))
            self._private(ent)
        self._entropy = ent.read_bytes()

    @property
    def backend(self) -> str:
        return ("encrypted with Windows DPAPI (this Windows user only)" if self.windows else
                "owner-only file, NOT encrypted (development on a non-Windows system)")

    def _path(self, name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
        return self.folder / f"{safe}.secret"

    @staticmethod
    def _private(p: Path) -> None:
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass

    def put(self, name: str, values: dict[str, str]) -> dict:
        if not values or not all(isinstance(v, str) and v for v in values.values()):
            raise VaultError("every credential field needs a value")
        raw = json.dumps(values).encode()
        blob = _dpapi(raw, self._entropy, True) if self.windows else raw
        p = self._path(name)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"v": 1, "dpapi": self.windows, "data": base64.b64encode(blob).decode()}))
        self._private(tmp)
        os.replace(tmp, p)
        return {"name": name, "fields": sorted(values), "masked": {k: mask(v) for k, v in values.items()},
                "backend": self.backend}

    def get(self, name: str) -> Optional[dict[str, str]]:
        p = self._path(name)
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        blob = base64.b64decode(d["data"])
        if d.get("dpapi"):
            if not self.windows:
                raise VaultError("this vault entry was encrypted on Windows and can only be read there")
            blob = _dpapi(blob, self._entropy, False)
        return json.loads(blob)

    def has(self, name: str) -> bool:
        return self._path(name).exists()

    def delete(self, name: str) -> bool:
        p = self._path(name)
        if p.exists():
            p.unlink()
            return True
        return False

    def describe(self, name: str) -> Optional[dict]:
        v = self.get(name)
        return None if v is None else {"fields": sorted(v), "masked": {k: mask(x) for k, x in v.items()}}


def mask(value: str) -> str:
    """Only enough to recognise which key it is: first and last 4 characters of long values."""
    return "****" if len(value) < 12 else f"{value[:4]}…{value[-4:]}"
