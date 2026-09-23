"""Presentation changes must preserve analysis state and report real progress."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def render_app():
    from app.main import main
    main()


def test_chart_switching_motion_and_decisions_never_repeat_analysis(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    module = importlib.import_module("app.main")
    calls = []

    def analyzer(before, after, log=None):
        calls.append(1)
        return module.run_stub(before, after, log=log)

    monkeypatch.setattr(module, "run_analysis", analyzer)
    app = AppTest.from_function(render_app, default_timeout=20).run()
    next(b for b in app.button if b.label == "Сравнить документы").click().run()
    next(b for b in app.button if b.label == "Демо на тестовом комплекте").click().run()
    assert not app.exception
    run_id = app.session_state["run_id"]
    result = deepcopy(app.session_state["result"])
    journal = deepcopy(app.session_state["journal"])
    app.button(key=f"{run_id}:training-loss:confirm").click().run()
    grouping = f"{run_id}:chart_view"
    for view in ("По типу", "Решения", "По важности"):
        app.segmented_control(key=grouping).set_value(view).run()
        assert not app.exception
        assert app.session_state["decisions"] == {"training-loss": "confirmed"}
        assert app.session_state["result"] == result
        assert app.session_state["journal"] == journal
        assert app.session_state["run_id"] == run_id

    # Browser motion events cause reruns too, never a second analysis.
    for reduced in (False, True):
        app.session_state["ui_motion"] = {"enabled": not reduced, "reduced": reduced}
        app.run()
        charts = app.get("echarts_chart")
        assert len(charts) == 3
        assert all(json.loads(chart.proto.spec)["animation"] is not reduced for chart in charts)
        assert app.session_state["decisions"] == {"training-loss": "confirmed"}
        assert calls == [1]

    app.segmented_control(key=grouping).set_value("Решения").run()
    chart = json.loads(app.get("echarts_chart")[-1].proto.spec)
    assert {item["name"]: item["value"] for item in chart["series"][0]["data"]} == {
        "Подтверждено": 1, "Ожидает решения": 3,
    }
    next(b for b in app.button if b.label == "Мои сравнения").click().run()
    next(b for b in app.button if b.label == "Сравнить документы").click().run()
    next(b for b in app.button if b.label == "Демо на тестовом комплекте").click().run()
    assert not app.exception
    assert calls == [1, 1]
    assert app.session_state["run_id"] != run_id
    assert app.session_state["decisions"] == {}


def test_progress_reflects_log_events_and_does_not_fake_success(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "true")
    module = importlib.import_module("app.main")

    def failing_analyzer(before, after, log=None):
        log("parse", "Локально", "Чтение завершено.")
        log("parse", "Локально", "Повторное событие чтения.")
        raise ValueError("internal diagnostic must not be shown")

    monkeypatch.setattr(module, "run_analysis", failing_analyzer)
    app = AppTest.from_function(render_app, default_timeout=20).run()
    next(b for b in app.button if b.label == "Сравнить документы").click().run()
    next(b for b in app.button if b.label == "Демо на тестовом комплекте").click().run()
    assert not app.exception
    assert app.session_state["result"] is None
    assert len(app.session_state["journal"]) == 2
    assert app.get("progress")[0].proto.value == 14
    assert next(s for s in app.status if s.label == "Обработка остановлена").state == "error"
    assert "internal diagnostic" not in app.error[0].value


def test_upload_feedback_tracks_replacement_without_starting_analysis(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "true")
    module = importlib.import_module("app.main")
    calls = []

    def analyzer(before, after, log=None):
        calls.append(1)
        return module.run_stub(before, after, log=log)

    monkeypatch.setattr(module, "run_analysis", analyzer)
    app = AppTest.from_function(render_app, default_timeout=20).run()
    next(b for b in app.button if b.label == "Сравнить документы").click().run()
    for side in ("before", "after"):
        app.file_uploader(key=f"{side}_uploads").set_value([
            (f"{side}.txt", b"1.1. Department responsibilities.", "text/plain")
        ]).run()
    assert not app.exception
    assert calls == []
    assert sum("получены, ещё не проанализированы" in item.value for item in app.caption) == 2
    next(b for b in app.button if b.label == "Сравнить").click().run()
    assert not app.exception
    assert app.session_state["comparison_view"] == "detail"
    assert app.session_state["result"] is not None
    assert not app.file_uploader
    assert calls == [1]
    next(b for b in app.button if b.label == "Мои сравнения").click().run()
    next(b for b in app.button if b.label == "Сравнить документы").click().run()
    app.file_uploader(key="after_uploads").set_value([
        ("after.txt", b"1.1. Changed department responsibilities.", "text/plain")
    ]).run()
    assert not app.exception
    assert app.session_state["result"] is None
    assert not app.get("echarts_chart")
    assert calls == [1]
