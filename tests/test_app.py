"""Legacy rendering regressions and the current offline analysis adapter.

Legacy UI fixtures intentionally return run_stub. Real analysis and the complete
workflow are exercised without that substitution in test_workflow.py.
"""

from copy import deepcopy
from dataclasses import dataclass
import importlib
import json
from pathlib import Path
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class Upload:
    name: str
    content: bytes

    def getvalue(self) -> bytes:
        return self.content


@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    config = importlib.import_module("src.config")

    def no_api(*args, **kwargs):
        pytest.fail("Offline interface tests must never call an LLM")

    monkeypatch.setattr(config, "get_llm", no_api)
    monkeypatch.setattr(config, "ask_llm", no_api)
    return importlib.import_module("app.main")


def _render_app():
    from app.main import main

    main()


@pytest.fixture
def app_runtime(app_module, monkeypatch):
    calls = []
    # Isolate pre-existing filters/reset behavior from extraction changes.
    original = app_module.run_stub

    def tracked_run(before, after, log=None):
        calls.append((list(before), list(after)))
        assert all(isinstance(path, Path) and path.is_file() for path in before + after)
        return original(before, after, log=log)

    monkeypatch.setattr(app_module, "run_analysis", tracked_run)
    app = AppTest.from_function(_render_app, default_timeout=30).run()
    assert not app.exception
    return app, calls


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def _filter(app, label):
    return next(widget for widget in app.multiselect if widget.label == label)


def _visible_text(app):
    """Assert product copy independently of its typographic Streamlit element."""
    return "\n".join(
        str(element.value)
        for kind in ("text", "markdown", "caption", "info", "success", "warning", "subheader", "header")
        for element in getattr(app, kind)
    )


def _start_demo(app):
    _button(app, "Демо на тестовом комплекте").click().run()
    assert not app.exception
    assert app.session_state["result"]


def _evidence_records(result):
    for section in ("units", "function_map", "findings"):
        for item in result[section]:
            yield from item["evidence"]


def test_stub_contract_is_deterministic_and_never_attributes_examples(app_module):
    events = []
    before = [Path("private-before-input.docx")]
    after = [Path("private-after-input.xlsx")]
    result = app_module.run_stub(before, after, log=lambda *event: events.append(event))

    assert result == app_module.run_stub([Path("different.pdf")], [], use_llm=False)
    assert set(result) == {"units", "function_map", "findings", "conclusion"}
    assert {unit["status"] for unit in result["units"]} == {
        "создано", "сохранено", "реорганизовано"
    }
    for unit in result["units"]:
        assert {"name", "abbr", "status", "evidence"} <= unit.keys()
        assert "учеб" in unit["name"].lower()
    for mapping in result["function_map"]:
        assert {
            "before_unit", "before_function", "after_unit", "after_function",
            "status", "similarity", "evidence"
        } <= mapping.keys()
        assert isinstance(mapping["similarity"], float)
        assert 0 <= mapping["similarity"] <= 1
    assert {finding["type"] for finding in result["findings"]} == {
        "loss", "duplicate", "conflict", "reorganization"
    }
    assert {finding["severity"] for finding in result["findings"]} == {
        "high", "medium", "low"
    }
    assert len({finding["id"] for finding in result["findings"]}) == len(result["findings"])
    for finding in result["findings"]:
        assert {"id", "type", "severity", "title", "description", "units", "evidence"} <= finding.keys()
        assert isinstance(finding["units"], list)
    evidence = list(_evidence_records(result))
    assert evidence
    for source in evidence:
        assert set(source) == {"doc", "clause", "quote", "verified"}
        assert all(isinstance(source[field], str) for field in ("doc", "clause", "quote"))
        assert "учеб" in source["doc"].lower()
        assert source["verified"] is False
    encoded = json.dumps(result, ensure_ascii=False)
    assert all(path.name not in encoded for path in before + after)
    assert "редакция №8" not in encoded and "редакция №9" not in encoded
    assert isinstance(result["conclusion"], str) and result["conclusion"]
    assert [event[0] for event in events] == [
        "parse", "structure", "functions", "match", "findings", "verify", "report"
    ]
    assert all("симуляция" in " ".join(event[1:]).lower() for event in events)


def test_adapter_calls_agent_without_llm_even_outside_demo(app_module, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    received = {}
    sentinel = {"local": True}

    def stub(before, after, use_llm=True, log=None):
        received.update(before=before, after=after, use_llm=use_llm, log=log)
        return sentinel

    monkeypatch.setattr(app_module, "agent_run", stub)
    before, after = [Path("before.docx")], [Path("after.xlsx")]
    callback = lambda *args: None
    assert app_module.run_analysis(before, after, log=callback) is sentinel
    assert received == {"before": before, "after": after, "use_llm": False, "log": callback}


def test_uploads_have_safe_unique_names_and_live_until_context_exit(app_module):
    before = [Upload("../../same.txt", b"first"), Upload("../../same.txt", b"second")]
    after = [Upload("C:\\private\\same.txt", b"third"), Upload("table.txt", b"fourth")]
    with app_module.materialize_uploads(before, after) as (before_paths, after_paths):
        paths = before_paths + after_paths
        assert isinstance(before_paths, list) and isinstance(after_paths, list)
        assert len(set(paths)) == 4
        assert all(isinstance(path, Path) and path.is_file() for path in paths)
        assert all(path.parent.name == "before" for path in before_paths)
        assert all(path.parent.name == "after" for path in after_paths)
        assert before_paths[0].parent.parent == after_paths[0].parent.parent
        assert all(".." not in path.name and "\\" not in path.name for path in paths)
        assert [path.suffix for path in paths] == [".txt", ".txt", ".txt", ".txt"]
        assert [path.read_bytes() for path in paths] == [b"first", b"second", b"third", b"fourth"]
        assert not any(path.is_relative_to(Path(app_module.__file__).resolve().parents[1]) for path in paths)
    assert all(not path.exists() for path in paths)


def test_input_fingerprint_detects_names_contents_and_sides(app_module):
    first, second = Upload("document.docx", b"first"), Upload("document.docx", b"second")
    signature = app_module.input_fingerprint([first], [second])
    assert signature == app_module.input_fingerprint([Upload(first.name, first.content)], [second])
    assert signature != app_module.input_fingerprint([Upload("renamed.docx", first.content)], [second])
    assert signature != app_module.input_fingerprint([second], [second])
    assert signature != app_module.input_fingerprint([second], [first])


def test_demo_filters_decisions_and_fresh_run_are_stateful(app_runtime):
    app, calls = app_runtime
    assert _button(app, "Сравнить").disabled
    assert len(calls) == 0
    _start_demo(app)
    assert len(calls) == 1
    assert [tab.label for tab in app.tabs] == [
        "Подразделения", "Сопоставление функций", "Находки", "Заключение", "Журнал агента", "Структура и пункты"
    ]
    assert any("Выводы рекомендательные" in warning.value for warning in app.warning)
    run_id = app.session_state["run_id"]
    snapshot = deepcopy(app.session_state["result"])
    journal = deepcopy(app.session_state["journal"])
    assert len(journal) == 7
    assert all(entry["time"] and entry["step"] and entry["status"] and entry["message"] for entry in journal)
    assert all("симуляция" in f'{entry["status"]} {entry["message"]}'.lower() for entry in journal)
    finding = snapshot["findings"][0]
    finding_id = finding["id"]
    app.button(key=f"{run_id}:{finding_id}:confirm").click().run()
    assert not app.exception
    assert app.session_state["decisions"][finding_id] == "confirmed"

    excluded_types = sorted({item["type"] for item in snapshot["findings"]} - {finding["type"]})
    _filter(app, "Тип находки").set_value(excluded_types).run()
    assert not app.exception
    assert not any(button.key == f"{run_id}:{finding_id}:reject" for button in app.button)
    assert app.session_state["decisions"][finding_id] == "confirmed"
    _filter(app, "Тип находки").set_value([finding["type"]]).run()
    _filter(app, "Важность").set_value([finding["severity"]]).run()
    assert not app.exception
    assert app.button(key=f"{run_id}:{finding_id}:reject")
    assert "Решение: подтверждено" in _visible_text(app)
    app.button(key=f"{run_id}:{finding_id}:reject").click().run()
    assert not app.exception
    assert app.session_state["decisions"][finding_id] == "rejected"

    _filter(app, "Важность").set_value([]).run()
    assert not app.exception
    assert not any(button.label in ("Подтвердить", "Отклонить") for button in app.button)
    _filter(app, "Важность").set_value([finding["severity"]]).run()
    assert app.session_state["decisions"][finding_id] == "rejected"
    assert "Решение: отклонено" in _visible_text(app)
    assert len(calls) == 1
    assert app.session_state["run_id"] == run_id
    assert app.session_state["result"] == snapshot
    assert app.session_state["journal"] == journal
    assert all(source["verified"] is False for source in _evidence_records(app.session_state["result"]))

    _start_demo(app)
    assert len(calls) == 2
    assert app.session_state["run_id"] != run_id
    assert app.session_state["decisions"] == {}
    assert len(app.session_state["journal"]) == 7


@pytest.mark.parametrize("source", ["demo", "uploads"])
def test_sidebar_round_trip_preserves_result_decisions_and_documents(app_runtime, source):
    app, calls = app_runtime
    if source == "demo":
        _start_demo(app)
    else:
        app.file_uploader(key="before_uploads").set_value([
            ("before.txt", b"1.1. Before regulation.", "text/plain")
        ]).run()
        app.file_uploader(key="after_uploads").set_value([
            ("after.txt", b"1.1. After regulation.", "text/plain")
        ]).run()
        _button(app, "Сравнить").click().run()
        assert not app.exception

    run_id = app.session_state["run_id"]
    finding_id = app.session_state["result"]["findings"][0]["id"]
    app.button(key=f"{run_id}:{finding_id}:confirm").click().run()
    assert not app.exception
    state = {
        key: deepcopy(app.session_state[key])
        for key in ("result", "decisions", "journal", "run_id", "source_documents", "input_signature", "chat_history")
    }

    for page in ("ИИ-чат", "Согласование", "Ознакомление", "Документы новичка", "Анализ изменений"):
        next(widget for widget in app.radio if widget.label == "Раздел").set_value(page).run()
        assert not app.exception
        for key, value in state.items():
            assert app.session_state[key] == value, f"Navigation to {page} reset {key}"
        assert len(calls) == 1

    assert len(app.tabs) == 6
    assert "Решение: подтверждено" in _visible_text(app)
    if source == "uploads":
        # Hidden upload widgets may reset, but returning must not erase the
        # completed analysis. The next intentional change starts a fresh input.
        app.file_uploader(key="before_uploads").set_value([
            ("new-before.txt", b"1.1. Replacement regulation.", "text/plain")
        ]).run()
        assert not app.exception
        assert app.session_state["result"] is None
        assert app.session_state["decisions"] == {}
        assert len(calls) == 1
        app.file_uploader(key="after_uploads").set_value([
            ("new-after.txt", b"1.1. New comparison.", "text/plain")
        ]).run()
        _button(app, "Сравнить").click().run()
        assert not app.exception
        assert app.session_state["result"]
        assert app.session_state["run_id"] != run_id
        assert len(calls) == 2


def test_pagination_preserves_decisions_and_bounds_pages_after_filtering(app_module, monkeypatch):
    calls = []
    template = app_module.run_stub([], [])

    def many_results(before, after, log=None):
        calls.append(True)
        result = app_module.run_stub(before, after, log=log)
        result["units"] = [
            {**deepcopy(template["units"][0]), "name": f"Учебное подразделение [unit-{index:03d}]"}
            for index in range(17)
        ]
        result["function_map"] = [
            {**deepcopy(template["function_map"][0]),
             "before_function": f"Учебная функция [function-{index:03d}]"}
            for index in range(17)
        ]
        result["findings"] = [
            {**deepcopy(template["findings"][index % 4]),
             "id": f"page-finding-{index}", "title": f"Учебная находка {index + 1}"}
            for index in range(19)
        ]
        return result

    monkeypatch.setattr(app_module, "run_analysis", many_results)
    app = AppTest.from_function(_render_app, default_timeout=30).run()
    _start_demo(app)
    run_id = app.session_state["run_id"]
    snapshot = deepcopy(app.session_state["result"])
    page_key = f"{run_id}:findings_page"

    for tab_index, section, token in ((0, "units", "unit"), (1, "functions", "function")):
        assert app.selectbox(key=f"{run_id}:{section}_page").value == 1
        assert f"[{token}-000]" in _visible_text(app.tabs[tab_index])
        assert f"[{token}-008]" not in _visible_text(app.tabs[tab_index])
        app.selectbox(key=f"{run_id}:{section}_page").set_value(3).run()
        assert not app.exception
        assert f"[{token}-016]" in _visible_text(app.tabs[tab_index])
        assert f"[{token}-000]" not in _visible_text(app.tabs[tab_index])

    def visible_ids():
        return {button.key.split(":")[-2] for button in app.button if button.label == "Подтвердить"}

    assert app.selectbox(key=page_key).value == 1
    assert visible_ids() == {f"page-finding-{index}" for index in range(6)}
    app.button(key=f"{run_id}:page-finding-0:confirm").click().run()
    app.selectbox(key=page_key).set_value(2).run()
    assert not app.exception
    assert visible_ids() == {f"page-finding-{index}" for index in range(6, 12)}
    app.button(key=f"{run_id}:page-finding-6:reject").click().run()
    app.selectbox(key=page_key).set_value(1).run()
    assert not app.exception
    assert "Решение: подтверждено" in _visible_text(app)
    assert app.session_state["decisions"] == {
        "page-finding-0": "confirmed", "page-finding-6": "rejected"
    }

    # Reducing the result set from four pages to two must not leave an empty
    # phantom fourth page or discard decisions for temporarily hidden cards.
    app.selectbox(key=page_key).set_value(4).run()
    _filter(app, "Тип находки").set_value(["loss", "conflict"]).run()
    assert not app.exception
    assert 1 <= app.selectbox(key=page_key).value <= 2
    filtered_ids = {item["id"] for item in snapshot["findings"] if item["type"] in {"loss", "conflict"}}
    assert visible_ids() and visible_ids() <= filtered_ids
    assert len(visible_ids()) <= 6
    _filter(app, "Важность").set_value([]).run()
    assert not app.exception
    assert visible_ids() == set()
    assert app.session_state["result"] == snapshot
    assert app.session_state["decisions"]["page-finding-6"] == "rejected"
    assert len(calls) == 1

    _start_demo(app)
    new_run_id = app.session_state["run_id"]
    assert new_run_id != run_id
    assert app.session_state["decisions"] == {}
    assert app.selectbox(key=f"{new_run_id}:findings_page").value == 1
    assert len(visible_ids()) == 6
    assert len(calls) == 2


def test_changed_upload_content_hides_old_result_and_compare_uses_live_files(app_module, monkeypatch):
    calls = []
    # Isolate pre-existing filters/reset behavior from extraction changes.
    original = app_module.run_stub

    def tracked_run(before, after, log=None):
        assert all(path.is_file() for path in before + after)
        calls.append((before + after, [path.read_bytes() for path in before + after]))
        return original(before, after, log=log)

    monkeypatch.setattr(app_module, "run_analysis", tracked_run)
    app = AppTest.from_function(_render_app, default_timeout=30).run()
    assert not app.exception
    assert all(uploader.accept_multiple_files for uploader in app.file_uploader)
    assert all(set(uploader.allowed_type) == {".pdf", ".docx", ".xlsx", ".txt"} for uploader in app.file_uploader)
    app.file_uploader(key="before_uploads").set_value([
        ("before.txt", b"version one", "text/plain")
    ]).run()
    assert _button(app, "Сравнить").disabled
    app.file_uploader(key="after_uploads").set_value([
        ("after.txt", b"comparison", "text/plain")
    ]).run()
    assert not _button(app, "Сравнить").disabled
    _button(app, "Сравнить").click().run()
    assert not app.exception and app.session_state["result"]
    assert len(calls) == 1
    assert calls[0][1] == [b"version one", b"comparison"]
    assert all(not path.exists() for path in calls[0][0])
    run_id = app.session_state["run_id"]
    finding_id = app.session_state["result"]["findings"][0]["id"]
    app.button(key=f"{run_id}:{finding_id}:confirm").click().run()
    app.file_uploader(key="before_uploads").set_value([
        ("before.txt", b"version two", "text/plain")
    ]).run()
    assert not app.exception
    assert not app.session_state["result"]
    assert not app.session_state["journal"]
    assert app.session_state["decisions"] == {}
    assert len(calls) == 1
    assert not app.tabs


def test_failure_clears_previous_result_and_redacts_exception(app_module, app_runtime, monkeypatch):
    app, _ = app_runtime
    _start_demo(app)
    run_id = app.session_state["run_id"]
    finding_id = app.session_state["result"]["findings"][0]["id"]
    app.button(key=f"{run_id}:{finding_id}:confirm").click().run()
    sensitive_marker = "sensitive-test-marker"

    def broken_run(*args, **kwargs):
        raise RuntimeError(sensitive_marker)

    monkeypatch.setattr(app_module, "run_analysis", broken_run)
    _button(app, "Демо на тестовом комплекте").click().run()
    assert not app.exception
    assert app.error
    assert not app.session_state["result"]
    assert app.session_state["decisions"] == {}
    assert sensitive_marker not in " ".join(error.value for error in app.error)
    assert sensitive_marker not in repr(app.session_state["journal"])
    assert not app.tabs


@pytest.mark.parametrize("empty", [False, True])
def test_empty_results_missing_sources_and_unknown_statuses_render(app_module, monkeypatch, empty):
    result = app_module.run_stub([], [])
    if empty:
        result.update(units=[], function_map=[], findings=[], conclusion="")
    else:
        for section in ("units", "function_map", "findings"):
            for item in result[section]:
                item["evidence"] = []
                if "status" in item:
                    item["status"] = "неизвестный статус"
        result["findings"][0]["type"] = "unrecognized"
        result["findings"][0]["severity"] = "unrecognized"
    monkeypatch.setattr(app_module, "run_analysis", lambda *args, **kwargs: result)
    app = AppTest.from_function(_render_app, default_timeout=30).run()
    _start_demo(app)
    assert len(app.tabs) == 6
    assert not app.exception
    if empty:
        assert {item.value for item in app.info} >= {
            "Подразделения отсутствуют.", "Сопоставления функций отсутствуют.",
            "Находки отсутствуют.", "Журнал пуст."
        }
    else:
        assert any(item.value == "Источники не указаны." for item in app.caption)
        assert "неизвестный статус" in _visible_text(app)
        assert "unrecognized" in _filter(app, "Тип находки").value
        assert "unrecognized" in _filter(app, "Важность").value
