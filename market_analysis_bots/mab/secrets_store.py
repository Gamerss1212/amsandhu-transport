"""Credential storage kept out of source control and out of logs.

* Windows: values are encrypted with DPAPI (CryptProtectData, current-user scope) and stored in
  %APPDATA%\\mab\\secrets.json. Only the same Windows user on the same machine can decrypt them.
* Other systems: the `keyring` package is used when installed (macOS Keychain, Secret Service);
  otherwise values go to ~/.config/mab/secrets.json with owner-only permissions (0600), which
  protects against other users but is NOT encryption. `backend_name()` says which is in use.

Values are entered through a hidden prompt (`python -m mab secret set NAME`), never through
chat, config files or command-line arguments, and are never printed. A logging filter masks
any stored value that would otherwise appear in a log line.

Nothing in this build uses these credentials to place orders: real-money trading is disabled.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from typing import List, Optional


def _dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "mab")
    return os.path.join(os.path.expanduser("~"), ".config", "mab")


PATH = os.path.join(_dir(), "secrets.json")


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out))   # UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def backend_name() -> str:
    if sys.platform == "win32":
        return "Windows DPAPI (encrypted for this Windows user)"
    if _keyring() is not None:
        return "system keyring"
    return f"owner-only file {PATH} (permissions, not encryption)"


def _load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save(d: dict):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, PATH)


def set_secret(name: str, value: str):
    if not name or not value:
        raise ValueError("name and value are required")
    kr = _keyring() if sys.platform != "win32" else None
    if kr is not None:
        kr.set_password("mab", name, value)
        d = _load()
        d[name] = {"backend": "keyring"}
        _save(d)
    else:
        d = _load()
        raw = value.encode("utf-8")
        if sys.platform == "win32":
            d[name] = {"backend": "dpapi", "blob": base64.b64encode(_dpapi(raw, True)).decode()}
        else:
            d[name] = {"backend": "file", "blob": base64.b64encode(raw).decode()}
        _save(d)
    RedactingFilter.register(value)


def get_secret(name: str) -> Optional[str]:
    rec = _load().get(name)
    if not rec:
        return None
    if rec["backend"] == "keyring":
        kr = _keyring()
        v = kr.get_password("mab", name) if kr else None
    elif rec["backend"] == "dpapi":
        v = _dpapi(base64.b64decode(rec["blob"]), False).decode("utf-8")
    else:
        v = base64.b64decode(rec["blob"]).decode("utf-8")
    if v:
        RedactingFilter.register(v)
    return v


def delete_secret(name: str):
    d = _load()
    rec = d.pop(name, None)
    if rec and rec.get("backend") == "keyring" and _keyring():
        try:
            _keyring().delete_password("mab", name)
        except Exception:
            pass
    _save(d)


def list_names() -> List[str]:
    return sorted(_load())


class RedactingFilter(logging.Filter):
    """Masks registered secret values in every log record."""
    values: set = set()

    @classmethod
    def register(cls, v: str):
        if v and len(v) >= 6:
            cls.values.add(v)

    def filter(self, record: logging.LogRecord) -> bool:
        if self.values:
            msg = record.getMessage()
            for v in self.values:
                if v in msg:
                    msg = msg.replace(v, "***")
            record.msg, record.args = msg, ()
        return True


logging.getLogger().addFilter(RedactingFilter())
for _h in logging.getLogger().handlers:
    _h.addFilter(RedactingFilter())
