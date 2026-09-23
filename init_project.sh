#!/usr/bin/env bash
# Универсальный старт проекта HackAlem AI (любой трек)
# Streamlit + OpenAI/NVIDIA API + демо-режим + деплой на Railway
# Запуск из корня репозитория команды:  bash init_project.sh
# Существующие файлы не перезаписываются.

set -e
say()  { printf "\n\033[1;32m==> %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m[!] %s\033[0m\n" "$1"; }

make_file() {
  if [ -e "$1" ]; then warn "$1 уже есть, пропускаю"; cat > /dev/null
  else mkdir -p "$(dirname "$1")"; cat > "$1"; echo "  создан $1"; fi
}

say "Папки"
mkdir -p src app tests data
touch src/__init__.py

say ".gitignore"
make_file .gitignore <<'EOF'
.env
.env.*
!.env.example
__pycache__/
*.pyc
.venv/
.pytest_cache/
.DS_Store
.idea/
.vscode/
EOF

say ".env.example и .env"
make_file .env.example <<'EOF'
# Скопируйте в .env. Без ключей проект работает в демо-режиме.
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=
# auto — ключи если есть, иначе демо; true — всегда демо
DEMO_MODE=auto
EOF
[ -e .env ] || cp .env.example .env

say "src/config.py — ключи и демо-режим"
make_file src/config.py <<'EOF'
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
EOF

say "app/main.py — стартовое приложение"
make_file app/main.py <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from src.config import demo_mode, ask_llm

st.set_page_config(page_title="HackAlem AI", page_icon="🚀", layout="wide")
st.title("🚀 HackAlem AI")
st.caption("Режим: " + ("демо (без ключей)" if demo_mode() else "с API"))

q = st.text_input("Проверка LLM", "Ответь одним словом: работает?")
if st.button("Отправить"):
    st.write(ask_llm(q))
EOF

say "tests/test_smoke.py"
make_file tests/test_smoke.py <<'EOF'
from src.config import ask_llm


def test_demo_fallback(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    assert "Демо" in ask_llm("тест")
EOF

say "requirements.txt"
make_file requirements.txt <<'EOF'
streamlit
pandas
numpy
plotly
python-dotenv
openai
requests
pytest
EOF

say "Dockerfile для Railway"
make_file Dockerfile <<'EOF'
FROM python:3.11-slim
RUN apt-get update && apt-get install -y libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "streamlit run app/main.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true"]
EOF

say "AGENTS.md и CLAUDE.md — правила для Codex и Claude Code"
make_file AGENTS.md <<'EOF'
# Проект: <НАЗВАНИЕ>

## Задача и критерии
<Заполнить после выбора кейса>

## Команда
- Бекарыс — <роль>
- Темиран — <роль>

## Стек и запуск
- Python 3.11, Streamlit
- Установка: `pip install -r requirements.txt`
- Запуск: `streamlit run app/main.py`
- Тесты: `pytest -q`

## Правила
1. Проект обязан работать без GPU и без API-ключей (демо-режим через `src/config.py`).
2. Никогда не читай, не выводи и не коммить `.env`. Ключи только через `src/config.py`.
3. Не коммить файлы больше 100 МБ.
4. Новые библиотеки, модели и датасеты добавляй в README, раздел «Данные и внешние сервисы».
5. После изменений запускай `pytest -q`.
6. Не придумывай в README функции, которых нет в коде.

## Формат коммитов
`[data]`, `[model]`, `[app]`, `[test]`, `[docs]`, `[deploy]` + короткое описание
EOF
make_file CLAUDE.md <<'EOF'
@AGENTS.md
EOF

say "README.md — каркас по инструкции организаторов"
make_file README.md <<'EOF'
# <Название проекта>

## Описание
<Какую проблему решает и для кого>

## Что реализовано
- ...

## Как работает
<Сценарий от входных данных до результата>

## Технологии и архитектура
Python 3.11, Streamlit, OpenAI API, ...

## Установка и запуск
```bash
git clone <URL>
cd <папка>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # ключи необязательны
streamlit run app/main.py
```
Или через Docker: `docker build -t app . && docker run -p 8501:8501 app`

## Параметры окружения
См. `.env.example`. Без ключей проект работает в демо-режиме. GPU не требуется.

## Как проверить
1. ...

## Данные и внешние сервисы
- ...

## Ограничения
- ...

## Развёрнутая версия
<Ссылка Railway>

## AI-инструменты при разработке
OpenAI Codex, ChatGPT, Claude Code, NVIDIA Brev

## Команда
Бекарыс, Темиран
EOF

say "Готово. Дальше:"
echo "  1) впишите ключи в .env"
echo "  2) pip install -r requirements.txt && pytest -q"
echo "  3) streamlit run app/main.py"
echo "  4) git add -A && git commit -m '[docs] Стартовая структура проекта' && git push"
