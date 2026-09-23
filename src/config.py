"""Ключи, демо-режим и вызов LLM. Проект обязан работать без ключей."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env(name, default=""):
    return os.getenv(name, default).strip()


def demo_mode() -> bool:
    flag = _env("DEMO_MODE", "auto").lower()
    if flag in ("true", "false"):
        return flag == "true"
    return not (_env("OPENAI_API_KEY") or _env("NVIDIA_API_KEY"))


def get_llm():
    """(client, model) или (None, None) в демо-режиме."""
    if demo_mode():
        return None, None
    from openai import OpenAI
    if _env("OPENAI_API_KEY"):
        return OpenAI(api_key=_env("OPENAI_API_KEY")), _env("OPENAI_MODEL", "gpt-4o-mini")
    if _env("NVIDIA_API_KEY"):
        return OpenAI(api_key=_env("NVIDIA_API_KEY"), base_url=_env("NVIDIA_BASE_URL")), _env("NVIDIA_MODEL")
    return None, None


def ask_llm(prompt, fallback="Демо-режим: ответ модели недоступен."):
    client, model = get_llm()
    if client is None:
        return fallback
    try:
        r = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}], max_tokens=800)
        return r.choices[0].message.content
    except Exception as e:
        return f"{fallback} (ошибка API: {type(e).__name__})"
