"""Computer temperature and throttling: readings, the plain-language assessment, the load test with its 95 C stop, the
report, and the master pausing training while the computer runs hot. Sensors are faked: no real heat is needed."""

import threading
import time
from pathlib import Path

import pytest

from tradingai import hardware as H
from tradingai.app import App


def loaded() -> bool:
    return any(t.name.startswith("thermal-load-") and t.is_alive() for t in threading.enumerate())


class FakeSensors:
    kind = "fake"
    error = None

    def __init__(self, idle=40.0, hot=70.0, passive=None, perf=None, temps=True):
        self.idle, self.hot, self.passive, self.perf, self.temps = idle, hot, passive, perf, temps

    def missing(self):
        return {}

    def read(self):
        busy = loaded()
        t = (self.hot if busy else self.idle) if self.temps else None
        return {"ts": int(time.time() * 1000), "source": "fake", "sensors": [] if t is None else
                [{"name": "cpu", "source": "fake", "temp_c": t}], "max_temp_c": t,
                "passive_limit_pct": (self.passive if busy else 100.0) if self.passive is not None else None,
                "throttle_reasons": None, "cpu_load_pct": 100.0 if busy else 3.0,
                "cpu_perf_pct": (self.perf if busy else 100.0) if self.perf is not None else None,
                "cpu_mhz": None, "perf_limit_flags": None, "invalid_readings": [], "error": None}


def quick(sensors, minutes=0.02, **kw):
    return H.run_check(sensors, minutes, baseline_s=0.3, cooldown_s=0.3, sample_s=0.1, threads=2, **kw)


def test_a_cool_computer_passes_with_its_measured_peak():
    res = quick(FakeSensors(idle=38, hot=71))
    assert res["verdict"] == "PASS" and res["peak_load_c"] == 71 and res["baseline_c"] == 38
    assert res["mean_load_pct"] > 90 and any(s["work_rate"] for s in res["samples"])
    assert not loaded()                                              # the load threads stopped


def test_the_load_stops_at_95c_and_the_check_fails():
    t0 = time.time()
    res = quick(FakeSensors(hot=96.0), minutes=0.5)                  # would run 30 s without the stop
    assert res["verdict"] == "FAIL" and res["aborted"] and "96" in res["aborted"]
    assert time.time() - t0 < 5 and not loaded()
    assert [s["phase"] for s in res["samples"]][-1] == "cooldown"    # it still measured the cool-down


def test_a_warm_computer_or_windows_throttling_is_a_warning():
    assert quick(FakeSensors(hot=88))["verdict"] == "WARNING"
    res = quick(FakeSensors(hot=70, passive=80.0))
    assert res["verdict"] == "WARNING" and any("passive limit" in r for r in res["reasons"])
    res = quick(FakeSensors(hot=70, perf=45.0))
    assert res["verdict"] == "WARNING" and any("speed" in r for r in res["reasons"])


def test_no_temperature_sensor_is_reported_as_such_never_invented():
    res = quick(FakeSensors(temps=False))
    assert res["verdict"] == "PASS (no temperature sensor)" and res["peak_load_c"] is None
    assert res["temperature"] == "not reported by this PC"
    txt = H.report_text(res)
    assert "not reported" in txt and "°C" not in txt.split("Samples")[1].split("\n")[1]


def test_a_stopped_check_gives_no_conclusion():
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    res = H.run_check(FakeSensors(), 0.5, baseline_s=0.2, cooldown_s=0.2, sample_s=0.1, threads=1, stop=stop)
    assert res["verdict"] == "STOPPED" and res["stopped"] and not loaded()


def test_assess_thresholds_and_reasons():
    base = {"max_temp_c": None, "passive_limit_pct": None, "throttle_reasons": None, "cpu_load_pct": None,
            "cpu_perf_pct": None}
    assert H.assess(base)["status"] == "unknown"
    assert H.assess(dict(base, max_temp_c=60))["status"] == "ok"
    a = H.assess(dict(base, max_temp_c=90))
    assert a["status"] == "warning" and a["thermal"]
    assert H.assess(dict(base, max_temp_c=97))["status"] == "critical"
    assert H.assess(dict(base, passive_limit_pct=70))["thermal"]
    a = H.assess(dict(base, cpu_load_pct=90, cpu_perf_pct=40))
    assert a["status"] == "warning" and not a["thermal"]              # slow, but not shown to be heat


def test_linux_sensors_read_sysfs_and_drop_impossible_values(tmp_path):
    z = tmp_path / "sys/class/thermal/thermal_zone0"
    z.mkdir(parents=True)
    (z / "temp").write_text("54000\n")
    (z / "type").write_text("x86_pkg_temp\n")
    bad = tmp_path / "sys/class/thermal/thermal_zone1"
    bad.mkdir(parents=True)
    (bad / "temp").write_text("-273000\n")                           # a broken sensor
    (bad / "type").write_text("acpitz\n")
    hw = tmp_path / "sys/class/hwmon/hwmon0"
    hw.mkdir(parents=True)
    (hw / "name").write_text("coretemp\n")
    (hw / "temp1_input").write_text("61000\n")
    (hw / "temp1_label").write_text("Package id 0\n")
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc/stat").write_text("cpu  100 0 100 800 0 0 0 0 0 0\n")
    s = H.Sensors.__new__(H.Sensors)
    s.kind, s.error, s._pdh, s._sys, s._lock = "linux-sysfs", None, None, H._Sysfs(str(tmp_path)), threading.Lock()
    r = s.read()
    assert [x["temp_c"] for x in r["sensors"]] == [54.0, 61.0] and r["max_temp_c"] == 61.0
    assert len(r["invalid_readings"]) == 1
    (tmp_path / "proc/stat").write_text("cpu  200 0 200 900 0 0 0 0 0 0\n")
    assert s.read()["cpu_load_pct"] == pytest.approx(66.7, abs=0.1)


def test_the_report_is_saved_as_text_and_json(tmp_path):
    res = quick(FakeSensors())
    path = H.save_report(res, tmp_path / "thermal-reports")
    assert path.exists() and path.with_suffix(".json").exists()
    txt = path.read_text(encoding="utf-8")
    assert "Result:  PASS" in txt and "peak under load" in txt and "nothing in it is estimated" in txt


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    yield a
    a.shutdown()


def test_training_pauses_while_the_computer_is_hot(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app, "submit_research", lambda *a, **k: calls.append(a) or {"job_id": f"J{len(calls)}"})
    monkeypatch.setattr(app.jobs, "view", lambda jid, with_result=False: {"state": "running"})
    app.hardware.sensors = FakeSensors(idle=91)                       # hot while idle
    app.hardware.sample()
    assert app.hardware.hot()
    app.fleet.operate()
    assert calls == [] and app.fleet.doing.startswith("training paused: the computer is running hot")
    ev = app.db.one("SELECT message FROM audit WHERE kind='hardware' ORDER BY id DESC LIMIT 1")
    assert "running hot" in ev["message"]
    app.hardware.sensors = FakeSensors(idle=45)
    app.hardware.sample()
    assert not app.hardware.hot()
    app.fleet.operate()
    assert calls                                                      # cooled down: training resumes


def test_the_thermal_check_runs_from_the_api_and_pauses_training(app, monkeypatch):
    from fastapi.testclient import TestClient

    from tradingai.api.server import create_app
    monkeypatch.setattr(H, "run_check", lambda sensors, minutes, stop=None, progress=None: (
        stop.wait(0.5), H.summarise([], 2, None, stop.is_set(), minutes))[1])
    app.hardware.sensors = FakeSensors()
    c = TestClient(create_app(app, token="T0K"), base_url="http://127.0.0.1:8000")
    h = {"X-TA-Token": "T0K", "Origin": "http://127.0.0.1:8000"}
    v = c.get("/api/system/thermal", headers=h).json()
    assert v["thresholds"] == {"warning_c": 85.0, "stop_c": 95.0} and "machine" in v
    assert c.post("/api/system/thermal-check", json={"minutes": 1}, headers=h).json()["check"]["state"] == "running"
    assert app.hardware.hot()                                         # training waits during the check
    assert c.post("/api/system/thermal-check", json={"minutes": 1}, headers=h).status_code == 400   # one at a time
    c.post("/api/system/thermal-check/stop", headers=h)
    t0 = time.time()
    while app.hardware.check["state"] == "running" and time.time() - t0 < 5:
        time.sleep(0.05)
    chk = app.hardware.check
    assert chk["state"] == "done" and Path(chk["report"]).exists() and chk["result"]["verdict"] == "STOPPED"


def test_the_assistant_answers_temperature_questions_from_the_sensors(app):
    app.hardware.sensors = FakeSensors(idle=52)
    app.hardware.sample()
    out = app.assistant.ask("Is my computer too hot?")
    assert out["intent"] == "thermal" and "52 degrees" in out["answer"] and "Nothing shows overheating" in out["answer"]
    app.hardware.sensors = FakeSensors(temps=False)
    app.hardware.sample()
    assert "does not report a temperature" in app.assistant.ask("what's the cpu temperature")["answer"]
