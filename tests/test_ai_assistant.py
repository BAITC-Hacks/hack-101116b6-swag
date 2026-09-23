"""Grounding, optional API calls and offline fallback for AI features."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import ai_assistant
from src import config
from streamlit.testing.v1 import AppTest


def test_ai_observation_uses_only_real_source_ids(tmp_path, monkeypatch):
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text("1.1. Отдел альфа проверяет завершённые работы.", encoding="utf-8")
    after.write_text("1.1. Отдел бета проверяет завершённые работы.", encoding="utf-8")
    batches, changed = ai_assistant._comparison_batches([before], [after])
    assert changed == 1 and len(batches) == 1
    ids = list(batches[0][1])
    assert len(ids) == 2
    monkeypatch.setattr(config, "openai_available", lambda: True)
    monkeypatch.setattr(config, "get_llm", lambda: (object(), "test-model"))

    def response(*args, **kwargs):
        return {"observations": [
            {"category": "unit_change", "summary": "Кандидат на передачу",
             "explanation": "Проверьте распределение обязанностей.", "source_ids": ids},
            {"category": "loss", "summary": "Выдуманный источник",
             "explanation": "Нет опоры.", "source_ids": ["S999"]},
        ]}

    monkeypatch.setattr(ai_assistant, "_call_json", response)
    baseline = {"units": [], "function_map": [], "findings": [], "conclusion": "Локальный вывод"}
    result = ai_assistant.enrich_analysis(baseline, [before], [after])
    assert baseline.get("ai_insights") is None
    assert result["conclusion"] == "Локальный вывод"
    assert len(result["ai_insights"]) == 1
    assert {e["doc"] for e in result["ai_insights"][0]["evidence"]} == {str(before), str(after)}
    assert all(e["verified"] and e["quote"] in (before.read_text(), after.read_text())
               for e in result["ai_insights"][0]["evidence"])


def test_ai_failure_preserves_offline_analysis(tmp_path, monkeypatch):
    before = tmp_path / "before.txt"
    after = tmp_path / "after.txt"
    before.write_text("1.1. Отдел альфа проверяет работы.", encoding="utf-8")
    after.write_text("1.1. Отдел бета проверяет работы.", encoding="utf-8")
    monkeypatch.setattr(config, "openai_available", lambda: True)
    monkeypatch.setattr(config, "get_llm", lambda: (object(), "test-model"))
    monkeypatch.setattr(ai_assistant, "_call_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("failure")))
    baseline = {"units": [], "function_map": [], "findings": [], "conclusion": "Локальный вывод"}
    result = ai_assistant.enrich_analysis(baseline, [before], [after])
    assert result["conclusion"] == "Локальный вывод"
    assert result["ai_insights"] == []
    assert "ошибок вызова 1" in result["ai_status"]


def test_chat_rejects_forged_citation_and_falls_back_to_real_text(monkeypatch):
    documents = {"before": [], "after": [{"name": "После/положение.txt",
                                          "text": "1.1. Отдел бета проверяет завершённые работы."}]}
    result = {"units": [], "function_map": [], "findings": []}
    monkeypatch.setattr(config, "openai_available", lambda: True)
    monkeypatch.setattr(config, "get_llm", lambda: (object(), "test-model"))
    monkeypatch.setattr(ai_assistant, "_call_json", lambda *a, **k: {
        "answer": "Не подтверждённое утверждение", "source_ids": ["S999"], "insufficient": False,
    })
    answer = ai_assistant.answer_question("Кто проверяет работы?", documents, result)
    assert answer["mode"] == "local"
    assert "Не подтверждённое" not in answer["answer"]
    assert answer["evidence"][0]["doc"] == "После/положение.txt"
    assert answer["evidence"][0]["clause"] == "1.1"


def test_chat_uses_verified_retrieved_citation(monkeypatch):
    documents = {"before": [], "after": [{"name": "После/положение.txt",
                                          "text": "1.1. Отдел бета проверяет завершённые работы."}]}
    result = {"units": [], "function_map": [], "findings": []}
    monkeypatch.setattr(config, "openai_available", lambda: True)
    monkeypatch.setattr(config, "get_llm", lambda: (object(), "test-model"))
    monkeypatch.setattr(ai_assistant, "_call_json", lambda *a, **k: {
        "answer": "По пункту 1.1 проверку выполняет отдел бета.",
        "source_ids": ["S1"], "insufficient": False,
    })
    answer = ai_assistant.answer_question("Кто проверяет работы?", documents, result)
    assert answer["mode"] == "openai"
    assert answer["evidence"][0]["quote"] == documents["after"][0]["text"]
    assert answer["evidence"][0]["verified"] is True


def test_no_key_chat_returns_local_sources_without_api(monkeypatch):
    documents = {"before": [], "after": [{"name": "После/положение.txt",
                                          "text": "1.1. Отдел бета проверяет завершённые работы."}]}
    monkeypatch.setattr(config, "openai_available", lambda: False)
    monkeypatch.setattr(config, "get_llm", lambda: (_ for _ in ()).throw(AssertionError("API called")))
    answer = ai_assistant.answer_question("Кто проверяет работы?", documents,
                                           {"units": [], "function_map": [], "findings": []})
    assert answer["mode"] == "local"
    assert answer["evidence"][0]["verified"] is True


def test_chat_page_works_after_real_offline_analysis(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=30).run()
    next(button for button in app.button if button.label == "Синтетический пример: подключения и кабельные работы").click().run()
    next(widget for widget in app.radio if widget.label == "Раздел").set_value("ИИ-чат").run()
    assert not app.exception
    app.chat_input[0].set_value("Кто проверяет работы?").run()
    assert not app.exception
    assert app.session_state["chat_history"][-1]["mode"] == "local"
    assert app.session_state["chat_history"][-1]["evidence"]


def test_openai_mode_renders_candidates_and_chat_without_network(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    monkeypatch.setattr(config, "get_llm", lambda: (object(), "gpt-5.4-mini"))

    def fake_response(client, model, instructions, payload, schema, name, **kwargs):
        if name == "document_observations":
            ids = [item["id"] for item in payload["fragments"][:2]]
            return {"observations": [{"category": "unit_change", "summary": "Кандидат на изменение",
                                       "explanation": "Проверить по двум редакциям.", "source_ids": ids}]}
        return {"answer": "Проверьте обязанности по указанному пункту.",
                "source_ids": [payload["sources"][0]["id"]], "insufficient": False}

    monkeypatch.setattr(ai_assistant, "_call_json", fake_response)
    app = AppTest.from_file(str(ROOT / "app" / "main.py"), default_timeout=30).run()
    assert app.toggle[0].value is True
    next(button for button in app.button if button.label == "Синтетический пример: подключения и кабельные работы").click().run()
    assert not app.exception
    assert app.session_state["result"]["ai_insights"]
    assert all(e["doc"].startswith(("До/", "После/"))
               for item in app.session_state["result"]["ai_insights"] for e in item["evidence"])
    next(widget for widget in app.radio if widget.label == "Раздел").set_value("ИИ-чат").run()
    app.chat_input[0].set_value("Какие обязанности изменились?").run()
    assert not app.exception
    assert app.session_state["chat_history"][-1]["mode"] == "openai"
    assert app.session_state["chat_history"][-1]["evidence"]
