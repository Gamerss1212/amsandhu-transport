"""Credential vault: kept out of source control, out of logs, out of the browser, and encrypted at rest.

* Every value is encrypted with mab.crypto_box (authenticated encryption) under a 32-byte master key, with
  the value's name as associated data, and stored in `vault.json`.
* The master key never sits in plain text where the platform can protect it:
    Windows      DPAPI (CryptProtectData, current-user scope): only this Windows user on this computer can
                 unwrap it;
    macOS/Linux  the system keyring when the `keyring` package is installed;
    otherwise    an owner-only file (0600) next to the vault. The vault is still encrypted, but anyone who can
                 read your files can read that key too: `backend_name()` says so, and the app shows it.
* Names are namespaced by workspace and connection ("ws:<workspace>:conn:<id>:<field>"), so one workspace's
  credentials are never handed to another's processes.
* Values are never printed. A logging filter masks any value this process has read, and audit payloads are
  sanitised separately (mab.storage.sanitize).
* Records written by earlier versions (one DPAPI blob, keyring entry or file entry per value) are still read,
  and re-encrypted into the vault the first time they are read.

The directory is %APPDATA%\\mab (Windows) or ~/.config/mab, or $MAB_SECRETS_DIR when set.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import threading
from typing import List, Optional

from mab import crypto_box

_lock = threading.RLock()
_master_cache: dict = {}                  # vault directory -> master key (read once per process)


def _dir() -> str:
    if os.environ.get("MAB_SECRETS_DIR"):
        return os.environ["MAB_SECRETS_DIR"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "mab")
    return os.path.join(os.path.expanduser("~"), ".config", "mab")


def _path(name: str) -> str:
    return os.path.join(_dir(), name)


PATH = _path("secrets.json")          # the earlier per-value store (read for migration)


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
    if os.environ.get("MAB_SECRETS_NO_KEYRING"):
        return None
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def backend_name() -> str:
    if sys.platform == "win32":
        return "encrypted vault; key protected by Windows DPAPI (this Windows user only)"
    if _keyring() is not None:
        return "encrypted vault; key in the system keyring"
    return (f"encrypted vault; key in an owner-only file in {_dir()} (protects against other users of this computer, "
            "not against anyone who can read your files)")


def _write_private(path: str, data: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _master() -> bytes:
    with _lock:
        if _dir() in _master_cache:
            return _master_cache[_dir()]
        kp = _path("master.key")
        key = None
        kr = _keyring() if sys.platform != "win32" else None
        if os.path.exists(kp):
            with open(kp, encoding="utf-8") as fh:
                rec = json.load(fh)
            raw = base64.b64decode(rec["blob"]) if rec.get("blob") else b""
            if rec["backend"] == "dpapi":
                key = _dpapi(raw, False)
            elif rec["backend"] == "keyring":
                v = kr.get_password("mab", "__master__") if kr else None
                if not v:
                    raise RuntimeError("the vault key is in the system keyring, which is not available now")
                key = base64.b64decode(v)
            else:
                key = raw
        else:
            key = os.urandom(32)
            if sys.platform == "win32":
                rec = {"backend": "dpapi", "blob": base64.b64encode(_dpapi(key, True)).decode()}
            elif kr is not None:
                kr.set_password("mab", "__master__", base64.b64encode(key).decode())
                rec = {"backend": "keyring"}
            else:
                rec = {"backend": "file", "blob": base64.b64encode(key).decode()}
            _write_private(kp, json.dumps(rec))
        _master_cache[_dir()] = key
        return key


def _load(name: str) -> dict:
    try:
        with open(_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def set_secret(name: str, value: str):
    if not name or not value:
        raise ValueError("name and value are required")
    with _lock:
        v = _load("vault.json")
        v[name] = {"v": 1, "blob": crypto_box.seal(_master(), value.encode("utf-8"), name.encode())}
        _write_private(_path("vault.json"), json.dumps(v))
    RedactingFilter.register(value)


def _legacy_get(name: str) -> Optional[str]:
    rec = _load("secrets.json").get(name)
    if not rec:
        return None
    if rec["backend"] == "keyring":
        kr = _keyring()
        return kr.get_password("mab", name) if kr else None
    if rec["backend"] == "dpapi":
        return _dpapi(base64.b64decode(rec["blob"]), False).decode("utf-8")
    return base64.b64decode(rec["blob"]).decode("utf-8")


def get_secret(name: str) -> Optional[str]:
    with _lock:
        rec = _load("vault.json").get(name)
        if rec:
            val = crypto_box.open_(_master(), rec["blob"], name.encode()).decode("utf-8")
        else:
            val = _legacy_get(name)
            if val:                                    # move an earlier-version record into the vault
                set_secret(name, val)
                _delete_legacy(name)
    if val:
        RedactingFilter.register(val)
    return val


def _delete_legacy(name: str):
    d = _load("secrets.json")
    rec = d.pop(name, None)
    if rec is None:
        return
    if rec.get("backend") == "keyring" and _keyring():
        try:
            _keyring().delete_password("mab", name)
        except Exception:
            pass
    _write_private(_path("secrets.json"), json.dumps(d))


def delete_secret(name: str):
    with _lock:
        v = _load("vault.json")
        if v.pop(name, None) is not None:
            _write_private(_path("vault.json"), json.dumps(v))
        _delete_legacy(name)


def delete_prefix(prefix: str) -> int:
    with _lock:
        v = _load("vault.json")
        gone = [k for k in v if k.startswith(prefix)]
        for k in gone:
            v.pop(k)
        if gone:
            _write_private(_path("vault.json"), json.dumps(v))
        return len(gone)


def list_names(prefix: str = "") -> List[str]:
    return sorted(k for k in set(_load("vault.json")) | set(_load("secrets.json")) if k.startswith(prefix))


def has(name: str) -> bool:
    return name in _load("vault.json") or name in _load("secrets.json")


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
