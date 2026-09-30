"""Sign-in and account isolation for the local app.

* Accounts: username + password, hashed with scrypt (n=2^14, r=8, p=1, 16-byte random salt); PBKDF2-SHA256 with
  600,000 iterations where scrypt is unavailable. Passwords are never stored or logged.
* The first account is created on first run (the owner). The owner can add more accounts; every account has its own
  workspaces (a main one for paper and live trading, and a DEMO one with synthetic markets), its own database, its own
  bot process and its own credentials namespace. One account never sees another's data.
* Sessions: a random 256-bit token in an HttpOnly, SameSite=Strict cookie (only its hash is stored), 12 hours idle /
  14 days at most; a separate random CSRF token must accompany every change (sent by the page in a header, never
  stored in the browser).
* Repeated wrong passwords lock that username for a while (5 failures -> 1 minute, doubling to 30 minutes).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from typing import Optional

IDLE_S = 12 * 3600
MAX_S = 14 * 86400
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, pw TEXT NOT NULL,
    role TEXT NOT NULL, created INTEGER, last_login INTEGER);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, csrf TEXT NOT NULL,
    workspace TEXT NOT NULL, created INTEGER, last_seen INTEGER);
CREATE TABLE IF NOT EXISTS workspaces (workspace_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL,
    path TEXT NOT NULL, created INTEGER, autostart INTEGER NOT NULL DEFAULT 0, label TEXT);
CREATE TABLE IF NOT EXISTS login_failures (username TEXT PRIMARY KEY, count INTEGER, until INTEGER);
"""


def _now() -> int:
    return int(time.time())


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    try:
        dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
        return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()
    except (AttributeError, ValueError):
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600_000)
        return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        kind, s, d = stored.split("$")
        salt, want = base64.b64decode(s), base64.b64decode(d)
        if kind == "scrypt":
            got = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
        else:
            got = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600_000)
        return hmac.compare_digest(got, want)
    except (ValueError, TypeError):
        return False


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, path: str, data_dir: str, legacy_home: Optional[str] = None):
        self.path = path
        self.data_dir = data_dir
        self.legacy_home = legacy_home
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.lock = threading.Lock()
        with self._c() as c:
            c.executescript(SCHEMA)

    def _c(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        return c

    def _q(self, sql, args=()):
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def _w(self, sql, args=()):
        with self.lock, self._c() as c:
            c.execute(sql, args)

    # ------------------------------------------------------------------ accounts
    def needs_setup(self) -> bool:
        return not self._q("SELECT 1 FROM users LIMIT 1")

    @staticmethod
    def _validate(username: str, password: str):
        u = (username or "").strip()
        if not 2 <= len(u) <= 40 or not all(ch.isalnum() or ch in "._-@" for ch in u):
            raise ValueError("choose a username of 2-40 letters, digits or . _ - @")
        if len(password or "") < 8:
            raise ValueError("use a password of at least 8 characters")
        if len(password) > 200:
            raise ValueError("that password is too long")
        return u

    def create_user(self, username: str, password: str, role: str = "member") -> dict:
        u = self._validate(username, password)
        if self._q("SELECT 1 FROM users WHERE lower(username)=lower(?)", (u,)):
            raise ValueError("that username is taken")
        uid = "u" + secrets.token_hex(4)
        self._w("INSERT INTO users VALUES (?,?,?,?,?,?)", (uid, u, hash_password(password), role, _now(), None))
        self._make_workspaces(uid, first=role == "owner")
        return self.user(uid)

    def setup_owner(self, username: str, password: str) -> dict:
        if not self.needs_setup():
            raise ValueError("this app already has an owner; sign in")
        return self.create_user(username, password, "owner")

    def user(self, uid: str) -> Optional[dict]:
        r = self._q("SELECT user_id, username, role, created, last_login FROM users WHERE user_id=?", (uid,))
        return r[0] if r else None

    def users(self) -> list:
        return self._q("SELECT user_id, username, role, created, last_login FROM users ORDER BY created")

    def change_password(self, uid: str, old: str, new: str):
        r = self._q("SELECT pw, username FROM users WHERE user_id=?", (uid,))
        if not r or not verify_password(old, r[0]["pw"]):
            raise ValueError("the current password is not right")
        self._validate(r[0]["username"], new)
        self._w("UPDATE users SET pw=? WHERE user_id=?", (hash_password(new), uid))
        self._w("DELETE FROM sessions WHERE user_id=?", (uid,))

    # ------------------------------------------------------------------ workspaces
    def _make_workspaces(self, uid: str, first: bool):
        base = os.path.join(self.data_dir, "workspaces", uid)
        main = os.path.join(base, "main")
        # the first account adopts the bots' data from earlier versions, so nothing is lost on upgrade
        if first and self.legacy_home and os.path.isdir(os.path.join(self.legacy_home, "data")):
            main = self.legacy_home
        for kind, path, label, auto in (("main", main, "Main (paper and live)", 1),
                                        ("demo", os.path.join(base, "demo"), "Demo (synthetic markets)", 0)):
            os.makedirs(path, exist_ok=True)
            self._w("INSERT OR IGNORE INTO workspaces VALUES (?,?,?,?,?,?,?)",
                    (f"{uid}-{kind}", uid, kind, path, _now(), auto, label))

    def workspaces(self, uid: Optional[str] = None) -> list:
        if uid:
            return self._q("SELECT * FROM workspaces WHERE user_id=? ORDER BY kind DESC", (uid,))
        return self._q("SELECT * FROM workspaces ORDER BY created")

    def workspace(self, wid: str) -> Optional[dict]:
        r = self._q("SELECT * FROM workspaces WHERE workspace_id=?", (wid,))
        return r[0] if r else None

    def set_autostart(self, wid: str, on: bool):
        self._w("UPDATE workspaces SET autostart=? WHERE workspace_id=?", (int(bool(on)), wid))

    # ------------------------------------------------------------------ sessions
    def login(self, username: str, password: str) -> tuple:
        u = (username or "").strip()
        f = self._q("SELECT * FROM login_failures WHERE lower(username)=lower(?)", (u,))
        if f and f[0]["until"] and f[0]["until"] > _now():
            raise PermissionError(f"too many wrong passwords; try again in {f[0]['until'] - _now()} seconds")
        r = self._q("SELECT * FROM users WHERE lower(username)=lower(?)", (u,))
        ok = bool(r) and verify_password(password or "", r[0]["pw"])
        if not r:
            verify_password(password or "", hash_password("timing-equaliser"))
        if not ok:
            n = (f[0]["count"] if f else 0) + 1
            until = _now() + min(1800, 60 * 2 ** (n - 5)) if n >= 5 else None
            self._w("INSERT OR REPLACE INTO login_failures VALUES (?,?,?)", (u.lower(), n, until))
            raise PermissionError("wrong username or password")
        self._w("DELETE FROM login_failures WHERE username=?", (u.lower(),))
        uid = r[0]["user_id"]
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        ws = f"{uid}-main"
        self._w("INSERT INTO sessions VALUES (?,?,?,?,?,?)", (_th(token), uid, csrf, ws, _now(), _now()))
        self._w("UPDATE users SET last_login=? WHERE user_id=?", (_now(), uid))
        return token, self.session(token)

    def open_session(self) -> tuple:
        """No sign-in page: Jarvus is a local app on 127.0.0.1, so the page is opened straight into the owner's
        workspace. The first run creates the owner account by itself (random password nobody needs)."""
        if self.needs_setup():
            self.setup_owner("owner", secrets.token_urlsafe(24))
        r = self._q("SELECT user_id FROM users WHERE role='owner' ORDER BY created LIMIT 1")
        uid = r[0]["user_id"]
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        self._w("INSERT INTO sessions VALUES (?,?,?,?,?,?)", (_th(token), uid, csrf, f"{uid}-main", _now(), _now()))
        return token, self.session(token)

    def session(self, token: Optional[str]) -> Optional[dict]:
        if not token or len(token) > 200:
            return None
        r = self._q("SELECT s.*, u.username, u.role FROM sessions s JOIN users u ON u.user_id = s.user_id WHERE token_hash=?",
                    (_th(token),))
        if not r:
            return None
        s = r[0]
        now = _now()
        if now - s["last_seen"] > IDLE_S or now - s["created"] > MAX_S:
            self._w("DELETE FROM sessions WHERE token_hash=?", (_th(token),))
            return None
        if now - s["last_seen"] > 60:
            self._w("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, _th(token)))
        s.pop("token_hash", None)
        return s

    def switch_workspace(self, token: str, wid: str) -> dict:
        s = self.session(token)
        w = self.workspace(wid)
        if s is None or w is None or w["user_id"] != s["user_id"]:
            raise PermissionError("that workspace is not yours")
        self._w("UPDATE sessions SET workspace=? WHERE token_hash=?", (wid, _th(token)))
        return self.session(token)

    def logout(self, token: str):
        self._w("DELETE FROM sessions WHERE token_hash=?", (_th(token or ""),))

    @staticmethod
    def check_csrf(session: dict, header: Optional[str]) -> bool:
        return bool(session and header and hmac.compare_digest(session["csrf"], header))
