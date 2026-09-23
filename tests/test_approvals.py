"""Document approval state transitions and an actual Streamlit interaction."""

from copy import deepcopy
from pathlib import Path
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.approvals import approval_status, create_approval, record_decision


@pytest.fixture
def workspace():
    version = {
        "id": "version-one",
        "title": "Синтетическое положение",
        "created_at": "2026-09-23T10:00:00+00:00",
        "documents": [{"name": "synthetic.txt", "content": b"original bytes", "text": "Учебный текст"}],
        "changes": [{
            "id": "c1", "unit": "Вымышленный отдел", "before": "Ведение архива",
            "after": "Ведение архива и реестра", "evidence": [{
                "doc": "synthetic.txt", "clause": "1", "quote": "Учебный текст", "verified": True,
            }],
        }],
        "recipients": [{"id": "person-1", "name": "Вымышленная Анна", "role": "Инженер"}],
        "reviewed_by": "Учебный ответственный",
    }
    return {"versions": {version["id"]: version}, "approvals": {}, "acknowledgements": {}, "onboarding": {}}


def test_all_reviewers_must_approve_and_versions_are_unchanged(workspace):
    snapshots = deepcopy(workspace["versions"])
    assert approval_status(workspace, "version-one") == "not_started"
    route = create_approval(workspace, "version-one", [" Алия ", "Борис"])
    assert route["reviewers"] == ["Алия", "Борис"]
    assert approval_status(workspace, "version-one") == "pending"
    record_decision(workspace, "version-one", "Алия", "approved", " Проверено ")
    assert approval_status(workspace, "version-one") == "pending"
    final = record_decision(workspace, "version-one", "Борис", "approved")
    assert approval_status(workspace, "version-one") == "approved"
    assert [event["action"] for event in final["events"]] == ["created", "approved", "approved"]
    assert all(event["at"] for event in final["events"])
    assert final["decisions"]["Алия"]["comment"] == "Проверено"
    assert workspace["versions"] == snapshots
    assert workspace["acknowledgements"] == workspace["onboarding"] == {}


@pytest.mark.parametrize("reviewers", [[], [""], ["  "], ["Алия", "алия"], ["Алия", " Алия "], [None], "Алия"])
def test_invalid_route_does_not_change_workspace(workspace, reviewers):
    before = deepcopy(workspace)
    with pytest.raises(ValueError):
        create_approval(workspace, "version-one", reviewers)
    assert workspace == before


def test_return_requires_comment_and_closes_route(workspace):
    create_approval(workspace, "version-one", ["Алия", "Борис"])
    before = deepcopy(workspace)
    with pytest.raises(ValueError, match="комментарий"):
        record_decision(workspace, "version-one", "Алия", "returned", "  ")
    assert workspace == before
    record_decision(workspace, "version-one", "Алия", "returned", "Уточнить владельца реестра")
    assert approval_status(workspace, "version-one") == "returned"
    with pytest.raises(ValueError, match="завершён"):
        record_decision(workspace, "version-one", "Борис", "approved")
    assert "Борис" not in workspace["approvals"]["version-one"]["decisions"]


def test_route_and_completed_answers_cannot_be_replaced(workspace):
    created = create_approval(workspace, "version-one", ["Алия", "Борис"])
    created["reviewers"].append("Посторонний")
    assert workspace["approvals"]["version-one"]["reviewers"] == ["Алия", "Борис"]
    answer = record_decision(workspace, "version-one", "Алия", "approved")
    answer["decisions"]["Алия"]["decision"] = "returned"
    assert workspace["approvals"]["version-one"]["decisions"]["Алия"]["decision"] == "approved"
    with pytest.raises(ValueError, match="уже записано"):
        record_decision(workspace, "version-one", "Алия", "returned", "Передумала")
    with pytest.raises(ValueError, match="уже создан"):
        create_approval(workspace, "version-one", ["Другой руководитель"])


def test_new_version_does_not_inherit_decisions(workspace):
    create_approval(workspace, "version-one", ["Алия"])
    record_decision(workspace, "version-one", "Алия", "approved")
    fresh = deepcopy(workspace["versions"]["version-one"])
    fresh["id"] = "version-two"
    fresh["documents"][0]["content"] = b"revised original"
    workspace["versions"]["version-two"] = fresh
    assert approval_status(workspace, "version-two") == "not_started"
    create_approval(workspace, "version-two", ["Алия"])
    assert approval_status(workspace, "version-two") == "pending"
    assert workspace["approvals"]["version-two"]["decisions"] == {}
    assert approval_status(workspace, "version-one") == "approved"


def test_missing_version_unreviewed_version_unknown_reviewer_and_bad_decision(workspace):
    for operation in (
        lambda: create_approval(workspace, "missing", ["Алия"]),
        lambda: approval_status(workspace, "missing"),
        lambda: record_decision(workspace, "missing", "Алия", "approved"),
        lambda: record_decision(workspace, "version-one", "Алия", "approved"),
    ):
        with pytest.raises(ValueError):
            operation()
    workspace["versions"]["version-one"]["reviewed_by"] = " "
    with pytest.raises(ValueError, match="ответственный"):
        create_approval(workspace, "version-one", ["Алия"])
    workspace["versions"]["version-one"]["reviewed_by"] = "Ответственный"
    create_approval(workspace, "version-one", ["Алия"])
    for reviewer, decision, comment in (
        ("Посторонний", "approved", ""), (None, "approved", ""),
        ("Алия", "rejected", ""), ("Алия", "approved", None),
    ):
        with pytest.raises(ValueError):
            record_decision(workspace, "version-one", reviewer, decision, comment)
    assert workspace["approvals"]["version-one"]["decisions"] == {}


def _render_approvals():
    import streamlit as st
    from app.approvals import render_approvals

    render_approvals(st.session_state["workspace"], "version-one")


def test_ui_can_create_route_validate_return_and_finish(workspace):
    app = AppTest.from_function(_render_approvals)
    app.session_state["workspace"] = workspace
    app.run()
    assert not app.exception
    assert any("версия" in str(item.value).lower() for item in app.text)
    app.button(key="approval:version-one:start").click().run()
    assert not app.exception
    assert approval_status(app.session_state["workspace"], "version-one") == "pending"
    app.button(key="approval:version-one:return").click().run()
    assert not app.exception
    assert any("комментарий" in item.value for item in app.error)
    assert approval_status(app.session_state["workspace"], "version-one") == "pending"
    app.text_area[0].set_value("Уточнить обязанность").run()
    app.button(key="approval:version-one:return").click().run()
    assert not app.exception
    assert approval_status(app.session_state["workspace"], "version-one") == "returned"
    assert not any(button.key == "approval:version-one:approve" for button in app.button)
