from src.config import ask_llm


def test_demo_fallback(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    assert "Демо" in ask_llm("тест")
