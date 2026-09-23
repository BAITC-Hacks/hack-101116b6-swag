"""Real offline analysis and the complete reviewed-version workflow."""

from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.acknowledgements import (
    acknowledge_document, acknowledgement_summary, onboarding_progress, publish_version,
)
from app.approvals import approval_status, create_approval, record_decision
from app.workflow import impact_cards, make_version, new_workspace


@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = importlib.import_module("src.config")

    def no_api(*args, **kwargs):
        pytest.fail("The tested workflow must work without an API call")

    monkeypatch.setattr(config, "get_llm", no_api)
    monkeypatch.setattr(config, "ask_llm", no_api)
    return importlib.import_module("app.main")


def _render_app():
    from app.main import main

    main()


def _button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def _page(app, label):
    next(widget for widget in app.radio if widget.label == "Раздел").set_value(label).run()
    assert not app.exception


def _snapshot_args():
    text = "1.1. Проверяет качество работ."
    return {
        "title": "Синтетические изменения", "revision": "1", "reviewed_by": "Ответственный",
        "documents": [{"name": "after.txt", "content": text.encode(), "text": text}],
        "reference_documents": [{"name": "before.txt", "content": b"1.1. Old regulation.",
                                 "text": "1.1. Old regulation."}],
        "changes": [{"id": "change-1", "unit": "Отдел качества", "before": "Не назначено",
                     "after": "Проверяет качество работ.", "recipient_ids": ["person-1"],
                     "evidence": [{"doc": "after.txt", "clause": "1.1",
                                   "quote": "Проверяет качество работ.", "verified": True}]}],
        "recipients": [{"id": "person-1", "name": "Вымышленная Алия", "role": "Отдел качества"}],
    }


def _approve(workspace, version_id):
    create_approval(workspace, version_id, ["Руководитель"])
    record_decision(workspace, version_id, "Руководитель", "approved")


def test_snapshot_is_detached_and_identical_content_is_idempotent():
    workspace = new_workspace()
    args = _snapshot_args()
    version_id = make_version(workspace, **args)
    assert make_version(workspace, **args) == version_id
    assert len(workspace["versions"]) == 1
    saved = deepcopy(workspace["versions"][version_id])
    args["documents"][0]["content"] = b"overwritten caller copy"
    args["changes"][0]["evidence"][0]["quote"] = "Изменённая цитата"
    args["recipients"][0]["name"] = "Другое имя"
    assert workspace["versions"][version_id] == saved


@pytest.mark.parametrize("field,value", [("doc", "unrelated.txt"), ("clause", "8.8"),
                                          ("quote", "Выдуманная функция"), ("verified", False)])
def test_snapshot_rejects_wrong_sources_even_when_marked_verified(field, value):
    workspace = new_workspace()
    args = _snapshot_args()
    args["changes"][0]["evidence"][0][field] = value
    with pytest.raises(ValueError):
        make_version(workspace, **args)
    assert not workspace["versions"]


@pytest.mark.parametrize("mutation", ["no_review", "no_targets", "unknown_target", "no_original"])
def test_snapshot_requires_review_explicit_targets_and_originals(mutation):
    args = _snapshot_args()
    if mutation == "no_review":
        args["reviewed_by"] = " "
    elif mutation == "no_targets":
        args["changes"][0]["recipient_ids"] = []
    elif mutation == "unknown_target":
        args["changes"][0]["recipient_ids"] = ["unknown"]
    else:
        args["documents"][0]["content"] = b""
    with pytest.raises(ValueError):
        make_version(new_workspace(), **args)


def test_new_revision_never_inherits_approval_or_acknowledgement():
    workspace = new_workspace()
    args = _snapshot_args()
    first = make_version(workspace, **args)
    _approve(workspace, first)
    publish_version(workspace, first)
    acknowledge_document(workspace, first, "person-1", 0)
    args["revision"] = "2"
    second = make_version(workspace, **args)
    assert second != first
    assert approval_status(workspace, second) == "not_started"
    assert second not in workspace["acknowledgements"]
    _approve(workspace, second)
    publish_version(workspace, second)
    assert acknowledgement_summary(workspace, first)[0]["acknowledged_at"]
    assert not acknowledgement_summary(workspace, second)[0]["acknowledged_at"]


def test_impact_cards_exclude_unverified_and_unchanged_rows():
    source = _snapshot_args()["changes"][0]["evidence"]
    result = {
        "units": [{"name": "Новый отдел", "status": "created", "evidence": deepcopy(source)},
                  {"name": "Существующий отдел", "status": "kept", "evidence": deepcopy(source)}],
        "function_map": [
            {"before_unit": "Отдел", "after_unit": "Отдел", "after_function": "Новая функция",
             "status": "new", "evidence": deepcopy(source)},
            {"status": "lost", "evidence": [{**source[0], "verified": False}]},
            {"status": "kept", "evidence": deepcopy(source)},
        ],
    }
    cards = impact_cards(result)
    assert {card["id"] for card in cards} == {"unit-0", "function-0"}
    cards[0]["evidence"][0]["quote"] = "Изменение копии"
    assert result["units"][0]["evidence"][0]["quote"] == source[0]["quote"]


def test_real_upload_analysis_keeps_originals_after_temporary_files_are_deleted(app_module, monkeypatch):
    paths_seen = []
    original_run = app_module.run_analysis

    def tracked_run(before, after, log=None):
        paths_seen.extend(before + after)
        assert all(path.exists() for path in before + after)
        return original_run(before, after, log=log)

    monkeypatch.setattr(app_module, "run_analysis", tracked_run)
    before = (ROOT / "data/control/before/regulation.txt").read_bytes()
    after = (ROOT / "data/control/after/regulation.txt").read_bytes()
    app = AppTest.from_function(_render_app, default_timeout=30).run()
    app.file_uploader(key="before_uploads").set_value([("same.txt", before, "text/plain")]).run()
    app.file_uploader(key="after_uploads").set_value([("same.txt", after, "text/plain")]).run()
    _button(app, "Сравнить").click().run()
    assert not app.exception
    assert app.session_state["error"] is None
    assert paths_seen and all(not path.exists() for path in paths_seen)
    sources = app.session_state["source_documents"]
    assert sources["before"][0]["content"] == before
    assert sources["after"][0]["content"] == after
    assert sources["before"][0]["name"] != sources["after"][0]["name"]
    result = app.session_state["result"]
    assert {item["type"] for item in result["findings"]} >= {"loss", "duplicate", "reorganization"}
    cards = impact_cards(result)
    assert cards
    card = next(card for card in cards if card["status"] == "new")
    person = {"id": "person-1", "name": "Вымышленный новичок", "role": card["unit"]}
    card["recipient_ids"] = [person["id"]]
    workspace = new_workspace()
    version_id = make_version(workspace, title="Проверенные изменения", revision="1",
                              reviewed_by="Ответственный", documents=sources["after"],
                              reference_documents=sources["before"], changes=[card], recipients=[person])
    assert workspace["versions"][version_id]["documents"][0]["content"] == after
    for source in card["evidence"]:
        assert source["verified"] is True
        assert source["doc"] in {document["name"] for group in sources.values() for document in group}


def test_full_ui_path_from_real_analysis_to_onboarding_without_keys(app_module):
    app = AppTest.from_function(_render_app, default_timeout=30).run()
    _button(app, "Синтетический пример: подключения и кабельные работы").click().run()
    assert not app.exception
    assert app.session_state["error"] is None
    result = app.session_state["result"]
    assert {finding["type"] for finding in result["findings"]} >= {
        "loss", "duplicate", "reorganization", "conflict"
    }
    assert all(event["status"] != "Симуляция" for event in app.session_state["journal"])
    run_id = app.session_state["run_id"]
    cards = impact_cards(result)
    card = next(card for card in cards if card["status"] == "new")
    app.multiselect(key=f"{run_id}:impact_selection").set_value([card["id"]]).run()
    assert app.button(key=f"{run_id}:freeze").disabled
    person_line = f"Вымышленный новичок | {card['unit']}"
    person_id = hashlib.sha256(person_line.encode()).hexdigest()[:16]
    app.text_area(key=f"{run_id}:people").set_value(person_line).run()
    app.multiselect(key=f"{run_id}:targets:{card['id']}").set_value([person_id]).run()
    app.text_input(key=f"{run_id}:reviewed_by").set_value("Вымышленный ответственный").run()
    app.checkbox(key=f"{run_id}:reviewed").check().run()
    app.button(key=f"{run_id}:freeze").click().run()
    assert not app.exception
    assert not app.error
    workspace = app.session_state["workspace"]
    version_id = app.session_state["active_version"]
    snapshot = deepcopy(workspace["versions"][version_id])
    assert snapshot["changes"][0]["recipient_ids"] == [person_id]
    assert snapshot["documents"][0]["content"]
    assert approval_status(workspace, version_id) == "not_started"

    _page(app, "Согласование")
    app.button(key=f"approval:{version_id}:start").click().run()
    assert not app.exception
    assert approval_status(workspace, version_id) == "pending"
    for _ in range(3):
        app.button(key=f"approval:{version_id}:approve").click().run()
        assert not app.exception
    assert approval_status(app.session_state["workspace"], version_id) == "approved"

    _page(app, "Ознакомление")
    app.button(key=f"ack:publish:{version_id}").click().run()
    app.radio(key=f"ack:mode:{version_id}").set_value("Сотрудник (симуляция)").run()
    assert not app.exception
    app.button(key=f"ack:reader:{version_id}:{person_id}:0:ack").click().run()
    assert not app.exception
    assert acknowledgement_summary(app.session_state["workspace"], version_id)[0]["acknowledged_at"]

    _page(app, "Документы новичка")
    app.multiselect(key=f"onboarding:versions:{person_id}:{card['unit']}").set_value([version_id]).run()
    app.button(key="onboarding:assign").click().run()
    app.radio(key="onboarding:mode").set_value("Новичок (симуляция)").run()
    assert not app.exception
    progress = onboarding_progress(app.session_state["workspace"], person_id)
    assert progress["total"] == len(snapshot["documents"])
    assert progress["percent"] == 100
    assert app.session_state["workspace"]["versions"][version_id] == snapshot

    _page(app, "Анализ изменений")
    assert app.session_state["workspace"]["versions"][version_id] == snapshot
