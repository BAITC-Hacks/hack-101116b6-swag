"""Version-bound publication, questions and role-specific onboarding."""

from copy import deepcopy
from pathlib import Path
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import acknowledgements as ack
from app.approvals import create_approval, record_decision


def _version(version_id="v1", documents=2):
    return {
        "id": version_id,
        "title": "Синтетический пакет",
        "created_at": "2026-09-23T09:00:00+00:00",
        "reviewed_by": "Вымышленный ответственный",
        "documents": [
            {"name": f"regulation-{index}.txt", "content": f"Оригинал {index}".encode(),
             "text": f"1. Синтетический текст {index}"}
            for index in range(documents)
        ],
        "changes": [
            {"id": "change-1", "unit": "Монтажник", "before": "Учебная прежняя функция",
             "after": "Учебная новая функция", "evidence": [], "recipient_ids": ["person-1"]},
            {"id": "change-2", "unit": "Кабельщик", "before": "Другая прежняя функция",
             "after": "Другая новая функция", "evidence": [], "recipient_ids": ["person-2"]},
        ],
        "recipients": [
            {"id": "person-1", "name": "Вымышленный Аскар", "role": "Монтажник"},
            {"id": "person-2", "name": "Вымышленная Дана", "role": "Кабельщик"},
        ],
    }


def _workspace():
    return {"versions": {"v1": _version()}, "approvals": {},
            "acknowledgements": {}, "onboarding": {}}


def _approve(workspace, version_id="v1"):
    create_approval(workspace, version_id, ["Руководитель 1", "Руководитель 2"])
    record_decision(workspace, version_id, "Руководитель 1", "approved")
    record_decision(workspace, version_id, "Руководитель 2", "approved")


@pytest.fixture
def published():
    workspace = _workspace()
    _approve(workspace)
    ack.publish_version(workspace, "v1")
    return workspace


def test_publication_requires_complete_approval_and_never_mutates_versions():
    workspace = _workspace()
    versions = deepcopy(workspace["versions"])
    with pytest.raises(ValueError):
        ack.publish_version(workspace, "missing")
    with pytest.raises(ValueError, match="согласованная"):
        ack.publish_version(workspace, "v1")
    create_approval(workspace, "v1", ["Руководитель 1", "Руководитель 2"])
    record_decision(workspace, "v1", "Руководитель 1", "approved")
    with pytest.raises(ValueError, match="согласованная"):
        ack.publish_version(workspace, "v1")
    record_decision(workspace, "v1", "Руководитель 2", "approved")
    with pytest.raises(ValueError, match="ещё не открыл"):
        ack.acknowledge_document(workspace, "v1", "person-1", 0)
    publication = ack.publish_version(workspace, "v1")
    ack.acknowledge_document(workspace, "v1", "person-1", 0)
    assert ack.publish_version(workspace, "v1")["published_at"] == publication["published_at"]
    assert ack.acknowledgement_summary(workspace, "v1")[0]["acknowledged_at"]
    assert workspace["versions"] == versions


def test_publication_requires_originals_and_unique_explicit_recipients():
    workspace = _workspace()
    _approve(workspace)
    workspace["versions"]["v1"]["documents"][0]["content"] = b""
    with pytest.raises(ValueError, match="оригиналы"):
        ack.publish_version(workspace, "v1")
    workspace["versions"]["v1"]["documents"][0]["content"] = b"synthetic"
    workspace["versions"]["v1"]["recipients"].append(
        deepcopy(workspace["versions"]["v1"]["recipients"][0])
    )
    with pytest.raises(ValueError, match="уникальны"):
        ack.publish_version(workspace, "v1")
    assert not workspace["acknowledgements"]


def test_returned_version_cannot_be_published():
    workspace = _workspace()
    create_approval(workspace, "v1", ["Руководитель"])
    record_decision(workspace, "v1", "Руководитель", "returned", "Нужна доработка")
    with pytest.raises(ValueError, match="согласованная"):
        ack.publish_version(workspace, "v1")
    assert not workspace["acknowledgements"]


def test_unknown_recipient_and_document_are_rejected_without_partial_writes(published):
    before = deepcopy(published)
    for recipient_id, index in [("unknown", 0), ("person-1", -1), ("person-1", 2),
                                ("person-1", True), ("person-1", "0")]:
        with pytest.raises(ValueError):
            ack.acknowledge_document(published, "v1", recipient_id, index)
        with pytest.raises(ValueError):
            ack.ask_question(published, "v1", recipient_id, index, "Как выполнить?")
    with pytest.raises(ValueError):
        ack.ask_question(published, "v1", "person-1", 0, "  ")
    assert published == before


def test_question_and_supervisor_answer_do_not_acknowledge_document(published):
    question = ack.ask_question(published, "v1", "person-1", 0, "Какой срок?")
    first = ack.acknowledgement_summary(published, "v1")[0]
    assert not first["acknowledged_at"]
    assert first["open_questions"] == 1
    answer = ack.answer_question(published, "v1", "person-1", 0, question["id"],
                                 "Срок указан в пункте 1.", "Ответственный")
    assert answer["answered_by"] == "Ответственный"
    first = ack.acknowledgement_summary(published, "v1")[0]
    assert not first["acknowledged_at"]
    assert first["open_questions"] == 0
    assert first["question_count"] == 1
    with pytest.raises(ValueError, match="уже сохранён"):
        ack.answer_question(published, "v1", "person-1", 0, question["id"],
                            "Исправленный ответ", "Ответственный")
    record = ack.acknowledge_document(published, "v1", "person-1", 0)
    ack.ask_question(published, "v1", "person-1", 0, "Дополнительный вопрос")
    assert ack.acknowledgement_summary(published, "v1")[0]["acknowledged_at"] == record["acknowledged_at"]
    question["question"] = "Изменено снаружи"
    record["questions"].clear()
    assert published["acknowledgements"]["v1"]["recipients"]["person-1"]["documents"]["0"]["questions"][0]["question"] == "Какой срок?"


def test_new_version_requires_fresh_acknowledgement_even_for_identical_documents(published):
    first = ack.acknowledge_document(published, "v1", "person-1", 0)
    published["versions"]["v2"] = _version("v2")
    _approve(published, "v2")
    ack.publish_version(published, "v2")
    v1_rows = ack.acknowledgement_summary(published, "v1")
    v2_rows = ack.acknowledgement_summary(published, "v2")
    assert v1_rows[0]["acknowledged_at"] == first["acknowledged_at"]
    assert all(row["acknowledged_at"] is None for row in v2_rows)
    assert all(row["version_id"] == "v2" for row in v2_rows)


def test_onboarding_requires_assigned_recipient_with_same_role_and_publication(published):
    person = published["versions"]["v1"]["recipients"][0]
    for invalid in [{**person, "id": "unknown"}, {**person, "role": "Другая роль"},
                    {**person, "name": "Другое имя"}]:
        with pytest.raises(ValueError):
            ack.assign_onboarding(published, invalid, ["v1"])
    published["versions"]["v2"] = _version("v2")
    _approve(published, "v2")
    with pytest.raises(ValueError, match="ещё не открыл"):
        ack.assign_onboarding(published, person, ["v1", "v2"])
    assert not published["onboarding"]
    with pytest.raises(ValueError):
        ack.assign_onboarding(published, person, [])


def test_onboarding_counts_every_document_and_preserves_assignment_history(published):
    person = published["versions"]["v1"]["recipients"][0]
    published["versions"]["v2"] = _version("v2", documents=1)
    _approve(published, "v2")
    ack.publish_version(published, "v2")
    versions = deepcopy(published["versions"])
    approvals = deepcopy(published["approvals"])
    package = ack.assign_onboarding(published, person, ["v1"])
    ack.assign_onboarding(published, person, ["v1"])
    assert len(published["onboarding"][person["id"]]["history"]) == 1
    ack.acknowledge_document(published, "v1", person["id"], 0)
    ack.ask_question(published, "v1", person["id"], 1, "Что делать?")
    progress = ack.onboarding_progress(published, person["id"])
    assert (progress["total"], progress["acknowledged"], progress["pending"]) == (2, 1, 1)
    ack.assign_onboarding(published, person, ["v1", "v2", "v2"])
    progress = ack.onboarding_progress(published, person["id"])
    assert (progress["total"], progress["acknowledged"], progress["pending"]) == (3, 1, 2)
    ack.acknowledge_document(published, "v1", person["id"], 1)
    ack.acknowledge_document(published, "v2", person["id"], 0)
    progress = ack.onboarding_progress(published, person["id"])
    assert progress["percent"] == 100
    assert progress["pending"] == 0
    assert len(published["onboarding"][person["id"]]["history"]) == 2
    assert published["onboarding"][person["id"]]["history"][0]["version_ids"] == ["v1"]
    package["recipient"]["role"] = "Неверная роль"
    assert published["versions"] == versions
    assert published["approvals"] == approvals
    assert published["onboarding"][person["id"]]["recipient"]["role"] == person["role"]


def _render_ack_test_app():
    import streamlit as st
    from app.acknowledgements import render_acknowledgements

    render_acknowledgements(st.session_state["workspace"], "v1")


def _render_onboarding_test_app():
    import streamlit as st
    from app.acknowledgements import render_onboarding

    render_onboarding(st.session_state["workspace"])


def test_acknowledgement_ui_questions_and_reader_filter(published):
    # Fresh Python 3.11 environments may spend several seconds importing tables.
    app = AppTest.from_function(_render_ack_test_app, default_timeout=30)
    app.session_state["workspace"] = published
    app.run()
    assert not app.exception
    app.radio(key="ack:mode:v1").set_value("Сотрудник (симуляция)").run()
    assert not app.exception
    assert any("Учебная новая функция" in item.value for item in app.text)
    assert not any("Другая новая функция" in item.value for item in app.text)
    app.text_area(key="ack:reader:v1:person-1:0:question").set_value("Вопрос из интерфейса")
    next(button for button in app.button if button.label == "Задать вопрос").click().run()
    assert not app.exception
    row = ack.acknowledgement_summary(app.session_state["workspace"], "v1")[0]
    assert not row["acknowledged_at"] and row["open_questions"] == 1
    app.button(key="ack:reader:v1:person-1:0:ack").click().run()
    assert not app.exception
    assert app.button(key="ack:reader:v1:person-1:0:ack").disabled
    app.selectbox(key="ack:person:v1").set_value("person-2").run()
    assert not app.exception
    assert not app.button(key="ack:reader:v1:person-2:0:ack").disabled
    assert any("Другая новая функция" in item.value for item in app.text)
    assert not any("Учебная новая функция" in item.value for item in app.text)


def test_onboarding_ui_role_assignment_and_document_progress(published):
    app = AppTest.from_function(_render_onboarding_test_app, default_timeout=30)
    app.session_state["workspace"] = published
    app.run()
    assert not app.exception
    app.multiselect(key="onboarding:versions:person-1:Монтажник").set_value(["v1"]).run()
    app.button(key="onboarding:assign").click().run()
    assert not app.exception
    app.radio(key="onboarding:mode").set_value("Новичок (симуляция)").run()
    assert not app.exception
    app.button(key="onboarding:reader:v1:person-1:0:ack").click().run()
    assert not app.exception
    progress = ack.onboarding_progress(app.session_state["workspace"], "person-1")
    assert progress["percent"] == 50
