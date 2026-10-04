"""The packaged app's start-up: a second launch finds the copy already running (same version: just show it; an older
copy: offer to close it), another program on the port moves Jarvus to a free one, the browser opens only once the
app answers, and start-with-Windows follows the copy the owner runs now."""

import http.server
import os
import sys
import threading

import pytest

import config
import desktop
import server
from engine import launcher, startup


def _serve(handler_cls, srv_cls=http.server.ThreadingHTTPServer):
    httpd = srv_cls(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


@pytest.fixture()
def jarvus(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    server.make_app(str(tmp_path), start_engines=False)
    httpd, port = _serve(server.Handler, server.QuietServer)
    monkeypatch.setattr(config, "PORT", port)
    yield port
    httpd.shutdown()
    httpd.server_close()


def test_probe_tells_this_version_from_nothing_and_from_another_program(jarvus):
    who = launcher.probe(jarvus)
    assert who == {"jarvus": True, "version": config.VERSION, "pid": os.getpid(), "ready": True}
    assert launcher.wait_ready(jarvus, timeout=5)

    class Other(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>some other program</html>")

        def log_message(self, *a):
            pass

    httpd, port = _serve(Other)
    try:
        assert launcher.probe(port)["jarvus"] is False
        assert launcher.free_port(port) != port                       # moves past a port someone else holds
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert launcher.probe(port) is None                               # nothing listens any more


def test_an_older_jarvus_without_the_version_route_is_still_recognised():
    class Old(http.server.BaseHTTPRequestHandler):                    # what a 2026 build before /api/version serves
        def do_GET(self):
            body = b'<html><script src="/js/app.js"></script></html>' if self.path == "/" else b"not found"
            self.send_response(200 if self.path == "/" else 404)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd, port = _serve(Old)
    try:
        assert launcher.probe(port) == {"jarvus": True, "version": None, "pid": None, "ready": True}
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_second_launch_of_the_same_version_opens_the_running_copy(jarvus, monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, "open_browser", lambda url: opened.append(url) or True)
    monkeypatch.setattr(desktop.time, "sleep", lambda s: None)
    who = launcher.probe(jarvus)
    assert desktop._already_running(launcher, config, who, background=False) == 0
    assert opened == [f"http://127.0.0.1:{jarvus}"]
    assert desktop._already_running(launcher, config, who, background=True) == 0 and len(opened) == 1


def test_an_older_copy_is_closed_only_when_the_owner_presses_enter(monkeypatch):
    stopped, state = [], {"up": True}
    fake = type("L", (), {})()
    fake.listening_pids = lambda port: {4242}
    fake.stop_pids = lambda pids: (stopped.append(set(pids)), state.update(up=False))
    fake.listening = lambda port: state["up"]
    monkeypatch.setattr(desktop.time, "sleep", lambda s: None)
    who = {"jarvus": True, "version": None, "pid": None, "ready": True}
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(EOFError()))
    assert desktop._already_running(fake, config, who, background=False) == 1 and not stopped   # window closed
    assert desktop._already_running(fake, config, who, background=True) == 0 and not stopped    # at sign-in: leave it
    monkeypatch.setattr("builtins.input", lambda *a: "")
    assert desktop._already_running(fake, config, who, background=False) == -1                  # go on starting
    assert stopped == [{4242}]


def test_netstat_listening_rows_give_the_process_ids():
    out = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1012
  TCP    127.0.0.1:8787         0.0.0.0:0              LISTENING       5321
  TCP    127.0.0.1:8787         127.0.0.1:51544        ESTABLISHED     5321
  TCP    127.0.0.1:51544        127.0.0.1:8787         ESTABLISHED     9876
  TCP    127.0.0.1:18787        0.0.0.0:0              LISTENING       777
"""
    assert launcher.parse_netstat(out, 8787) == {5321}


def test_start_with_windows_follows_the_copy_run_now(monkeypatch):
    class Reg:
        HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ = 1, 2, 3, 4

        def __init__(self, value=None):
            self.values = {} if value is None else {"Jarvus": value}

        def OpenKey(self, *a):
            class K:
                def __enter__(s): return s
                def __exit__(s, *a): return False
            return K()

        def QueryValueEx(self, key, name):
            if name not in self.values:
                raise OSError
            return self.values[name], 1

        def CreateKeyEx(self, *a):
            return object()

        def SetValueEx(self, key, name, res, typ, val):
            self.values[name] = val

        def CloseKey(self, key):
            pass

    monkeypatch.setattr(startup, "supported", lambda reg=None: True)
    monkeypatch.setattr(sys, "executable", r"C:\Users\abhi\Downloads\JarvusTerminal\JarvusTerminal.exe")
    old = Reg(r'cmd /c start "" /min "C:\Users\abhi\Desktop\Jarvus\JarvusTerminal.exe" --background')
    assert startup.adopt(old) is True and "Downloads" in old.values["Jarvus"]
    assert startup.adopt(old) is False                                  # already this copy
    off = Reg()
    assert startup.adopt(off) is False and off.values == {}              # never switched on by the owner: stays off
