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
    assert app.radio(key="active_page").options == ["Мои сравнения", "Мои документы", "Документы новичка"]
    assert not app.file_uploader
    click(app, "Сравнить документы")
    click(app, "Синтетический пример: подключения и кабельные работы")
    first = app.session_state["run_id"]
    assert not app.file_uploader
    assert not any(b.label == "Ознакомление" for b in app.button)
    finding_id = app.session_state["result"]["findings"][0]["id"]
    app.button(key=f"{first}:{finding_id}:confirm").click().run()
    click(app, "Спросить ИИ")
    app.chat_input[0].set_value("Кто проверяет работы?").run()
    assert not app.exception
    assert app.session_state["chat_dialog_run_id"] == first
    assert app.session_state["comparison_section"] == "Результат"
    click(app, "Вернуться к результату")
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


def test_newcomer_mock_draft_survives_navigation_without_assigning_real_documents(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(ROOT / "app/main.py"), default_timeout=30).run()
    app.radio(key="active_page").set_value("Документы новичка").run()
    assert not app.exception
    workspace = deepcopy(app.session_state["workspace"])
    assert app.button(key="newcomer:build").disabled
    app.text_input(key="newcomer:first_name").set_value("Алексей").run()
    app.text_input(key="newcomer:last_name").set_value("Иванов").run()
    app.text_input(key="newcomer:role").set_value("Специалист").run()
    for widget in list(app.checkbox):
        if widget.key.startswith("newcomer:doc:"):
            app.checkbox(key=widget.key).uncheck().run()
    assert app.button(key="newcomer:build").disabled
    app.checkbox(key="newcomer:doc:security").check().run()
    app.button(key="newcomer:build").click().run()
    assert not app.exception
    package = deepcopy(app.session_state["newcomer_mock_package"])
    assert package == {"first_name": "Алексей", "last_name": "Иванов", "role": "Специалист",
                       "documents": ["Информационная безопасность"]}
    assert app.session_state["workspace"] == workspace
    app.radio(key="active_page").set_value("Мои документы").run()
    app.radio(key="active_page").set_value("Документы новичка").run()
    assert app.text_input(key="newcomer:first_name").value == "Алексей"
    assert app.checkbox(key="newcomer:doc:security").value is True
    assert app.checkbox(key="newcomer:doc:job").value is False
    assert app.session_state["newcomer_mock_package"] == package
    app.text_input(key="newcomer:role").set_value("Руководитель").run()
    assert "newcomer_mock_package" not in app.session_state
    assert app.session_state["workspace"] == workspace
