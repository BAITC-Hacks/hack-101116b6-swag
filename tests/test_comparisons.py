"""Comparison context must survive switching, repeated inputs and employee views."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from docx import Document
from streamlit.testing.v1 import AppTest

from src.report import build_docx

ROOT = Path(__file__).resolve().parents[1]


def click(app, label):
    next(b for b in app.button if b.label == label).click().run()
    assert not app.exception


def test_two_comparisons_keep_their_own_chat_decisions_and_sources(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "true")
    app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=30).run()
    assert app.radio(key="active_page").options == ["Мои сравнения", "Мои документы"]
    assert not app.file_uploader
    click(app, "Сравнить документы")
    click(app, "Синтетический пример: подключения и кабельные работы")
    first = app.session_state["run_id"]
    assert not app.file_uploader
    assert not any(b.label == "Ознакомление" for b in app.button)
    finding_id = app.session_state["result"]["findings"][0]["id"]
    app.button(key=f"{first}:{finding_id}:confirm").click().run()
    click(app, "Задать вопрос")
    app.chat_input[0].set_value("Кто проверяет работы?").run()
    original = {key: deepcopy(app.session_state[key]) for key in ("result", "source_documents", "decisions", "chat_history", "journal")}
    click(app, "Мои сравнения")
    click(app, "Сравнить документы")
    click(app, "Синтетический пример: подключения и кабельные работы")
    second = app.session_state["run_id"]
    assert first != second
    assert app.session_state["decisions"] == {}
    assert app.session_state["chat_history"] == []
    assert app.session_state["active_version"] is None
    click(app, "Мои сравнения")
    assert len([b for b in app.button if b.label == "Открыть сравнение"]) == 2
    app.button(key=f"open:{first}").click().run()
    assert not app.exception
    for key, value in original.items():
        assert app.session_state[key] == value
    app.radio(key="active_page").set_value("Мои документы").run()
    assert not app.exception
    assert not app.file_uploader
    app.radio(key="active_page").set_value("Мои сравнения").run()
    assert app.session_state["run_id"] == first
    assert app.session_state["chat_history"] == original["chat_history"]


def test_report_excludes_unverified_claims_and_keeps_exact_sources():
    source = {"doc": "after.txt", "clause": "1.1", "quote": "Проверяет качество работ.", "verified": True}
    result = {"conclusion": "Unsupported conclusion", "findings": [
        {"title": "Признаки изменения", "description": "Требует проверки", "evidence": [source]},
        {"title": "Unsupported claim", "evidence": [{**source, "verified": False}]},
    ]}
    document = Document(BytesIO(build_docx(result)))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Unsupported" not in text
    assert source["quote"] in text
    assert "after.txt · пункт 1.1" in text
