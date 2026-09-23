"""Streamlit prototype. All analysis results are explicitly fictional examples."""

import hashlib
import math
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# src.config normally loads .env on import; this interface must not read that file.
os.environ["PYTHON_DOTENV_DISABLED"] = "true"
from src import config  # noqa: E402

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".xlsx"}
WARNING = (
    "Заглушка интерфейса: документы не проанализированы. "
    "Показаны учебные примеры. Выводы рекомендательные"
)
TYPE_LABELS = {
    "loss": "Утрата функции",
    "duplicate": "Дублирование",
    "conflict": "Противоречие",
    "reorganization": "Реорганизация",
}
SEVERITY_LABELS = {"high": "Высокая", "medium": "Средняя", "low": "Низкая"}
DECISION_LABELS = {
    "confirmed": "подтверждено",
    "rejected": "отклонено",
}


def run_stub(before: list[Path], after: list[Path], use_llm=True, log=None) -> dict:
    """Return fresh, deterministic teaching data without reading any input files.

    Parameters match the future analyzer interface. use_llm has no effect here.
    No quote is verified, and no example is attributed to the supplied paths.
    """
    steps = [
        ("parse", "Учебный этап чтения: содержимое документов не читалось."),
        ("structure", "Подготовлены вымышленные подразделения."),
        ("functions", "Подготовлены вымышленные функции подразделений."),
        ("match", "Показаны заранее заданные учебные сопоставления."),
        ("findings", "Подготовлены четыре учебных типа находок."),
        ("verify", "Проверка цитат не выполнялась; все verified=False."),
        ("report", "Подготовлено учебное заключение, не анализ документов."),
    ]
    if log is not None:
        for step, message in steps:
            log(step, "Симуляция", message)

    def evidence(clause, quote):
        return [{
            "doc": "Учебный регламент «Модель Альфа» (вымышленный)",
            "clause": clause,
            "quote": quote,
            "verified": False,
        }]

    planning = "Учебная группа планирования"
    control = "Учебный отдел контроля"
    coordination = "Учебное бюро координации"
    return {
        "units": [
            {"name": planning, "abbr": "УГП", "status": "реорганизовано",
             "evidence": evidence("У-1", "Учебная группа планирования передаёт координацию учебному бюро.")},
            {"name": control, "abbr": "УОК", "status": "сохранено",
             "evidence": evidence("У-2", "Учебный отдел контроля ведёт реестр учебных проверок.")},
            {"name": coordination, "abbr": "УБК", "status": "создано",
             "evidence": evidence("У-3", "Учебное бюро координации согласует учебные планы.")},
        ],
        "function_map": [
            {"before_unit": planning, "before_function": "Координация учебных планов",
             "after_unit": coordination, "after_function": "Согласование учебных планов",
             "status": "передано", "similarity": 0.84,
             "evidence": evidence("У-1", "Координация учебных планов передаётся учебному бюро.")},
            {"before_unit": control, "before_function": "Ведение реестра учебных проверок",
             "after_unit": control, "after_function": "Ведение реестра учебных проверок",
             "status": "сохранено", "similarity": 1.0,
             "evidence": evidence("У-2", "Учебный отдел контроля ведёт реестр учебных проверок.")},
            {"before_unit": planning, "before_function": "Хранение учебного архива планов",
             "after_unit": "Не задано в учебном примере", "after_function": "Не задано в учебном примере",
             "status": "не сопоставлено", "similarity": 0.0,
             "evidence": evidence("У-4", "Учебная группа хранит учебный архив планов.")},
        ],
        "findings": [
            {"id": "training-loss", "type": "loss", "severity": "high",
             "title": "Учебный пример: не назначен владелец архива",
             "description": "В вымышленной модели хранение архива не закреплено за новым подразделением. Пример показывает возможную утрату функции.",
             "units": [planning],
             "evidence": evidence("У-4", "Учебная группа хранит учебный архив планов.")},
            {"id": "training-duplicate", "type": "duplicate", "severity": "medium",
             "title": "Учебный пример: два владельца реестра",
             "description": "В вымышленной модели одинаковое ведение реестра поручено двум подразделениям. Пример показывает возможное дублирование.",
             "units": [control, coordination],
             "evidence": evidence("У-5", "Учебные отдел и бюро независимо ведут один учебный реестр.")},
            {"id": "training-conflict", "type": "conflict", "severity": "high",
             "title": "Учебный пример: разные сроки согласования",
             "description": "Два вымышленных пункта задают разные сроки согласования одного плана. Пример показывает возможное противоречие.",
             "units": [planning, coordination],
             "evidence": evidence("У-6а / У-6б", "Учебный срок согласования — три дня. Учебный срок согласования — пять дней.")},
            {"id": "training-reorganization", "type": "reorganization", "severity": "low",
             "title": "Учебный пример: передача координации",
             "description": "В вымышленной модели координация передана от группы новому бюро. Пример показывает изменение ответственности при реорганизации.",
             "units": [planning, coordination],
             "evidence": evidence("У-1", "Координация учебных планов передаётся учебному бюро.")},
        ],
        "conclusion": (
            "Это учебное заключение по вымышленной модели «Альфа». Оно демонстрирует "
            "отображение утраты, дублирования, противоречия и реорганизации функций. "
            "Загруженные документы и тестовый комплект не анализировались. "
            "Названия, цитаты и оценки сходства заданы заранее и не относятся к этим документам. "
            "Для реального заключения потребуется анализ документов и проверка цитат специалистом."
        ),
    }


def run_analysis(before: list[Path], after: list[Path], log=None) -> dict:
    """Single integration point for a future src.agent call, regardless of config."""
    return run_stub(before, after, use_llm=False, log=log)


def input_fingerprint(before, after):
    """Detect replacements with the same name as well as additions/removals."""
    return tuple(
        tuple(sorted((upload.name, hashlib.sha256(upload.getvalue()).hexdigest())
                     for upload in uploads))
        for uploads in (before, after)
    )


@contextmanager
def materialize_uploads(before, after):
    """Keep isolated temporary files alive throughout the analyzer call."""
    with TemporaryDirectory(prefix="org-structure-") as directory:
        groups = []
        for side, uploads in (("before", before), ("after", after)):
            target = Path(directory) / side
            target.mkdir()
            paths = []
            for upload in uploads:
                suffix = Path(upload.name).suffix.lower()
                if suffix not in SUPPORTED_SUFFIXES:
                    raise ValueError("Unsupported upload extension")
                path = target / f"{uuid4().hex}{suffix}"
                path.write_bytes(upload.getvalue())
                paths.append(path)
            groups.append(paths)
        yield groups[0], groups[1]


def sample_paths():
    return tuple(
        sorted(path for path in (ROOT / "data" / "sample" / side).glob("*")
               if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES)
        for side in ("before", "after")
    )


def clear_run():
    st.session_state.update(result=None, journal=[], run_id=None, decisions={}, error=None)


def log(step, status, message):
    st.session_state.journal.append({
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "step": step,
        "status": status,
        "message": message,
    })


def start_run(before, after, *, uploaded=False):
    clear_run()
    st.session_state.run_id = uuid4().hex
    try:
        if not before or not after:
            st.session_state.error = "Нужен хотя бы один файл с каждой стороны. Проверьте комплект и повторите запуск."
            return
        if uploaded:
            with materialize_uploads(before, after) as (before_paths, after_paths):
                result = run_analysis(before_paths, after_paths, log=log)
        else:
            result = run_analysis(before, after, log=log)
        st.session_state.result = result
    except Exception:
        # Exception text may contain document contents, paths or credentials.
        st.session_state.error = "Не удалось выполнить запуск интерфейса. Проверьте доступность файлов и повторите попытку."


def render_evidence(evidence):
    with st.expander("Источники", expanded=False):
        if not evidence:
            st.caption("Источники не указаны.")
            return
        st.caption("Проверка цитаты не подтверждает истинность всего вывода.")
        for index, source in enumerate(evidence):
            if index:
                st.divider()
            st.text(f"Документ: {source.get('doc') or 'не указан'}")
            st.text(f"Пункт: {source.get('clause') or 'не указан'}")
            st.text(f"Цитата: {source.get('quote') or 'не указана'}")
            if source.get("verified") is True:
                st.success("✓ Цитата проверена")
            else:
                st.warning("✗ Цитата не проверена")


def similarity_label(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "не указано"
    if not math.isfinite(number) or not 0 <= number <= 1:
        return "не указано"
    return f"{number:.0%}"


def render_units(units):
    if not units:
        st.info("Подразделения отсутствуют.")
    for unit in units:
        with st.container(border=True):
            st.subheader(unit.get("name") or "Название не указано", anchor=False)
            st.text(f"Сокращение: {unit.get('abbr') or 'не указано'}")
            st.text(f"Статус: {unit.get('status') or 'не указан'}")
            render_evidence(unit.get("evidence"))


def render_functions(function_map):
    if not function_map:
        st.info("Сопоставления функций отсутствуют.")
    for item in function_map:
        with st.container(border=True):
            before_column, after_column = st.columns(2)
            for column, side, label in ((before_column, "before", "До"), (after_column, "after", "После")):
                with column:
                    st.caption(label)
                    st.text(item.get(f"{side}_unit") or "Подразделение не указано")
                    st.write(item.get(f"{side}_function") or "Функция не указана")
            st.text(f"Статус: {item.get('status') or 'не указан'} · Сходство: {similarity_label(item.get('similarity'))}")
            render_evidence(item.get("evidence"))


def set_decision(finding_id, decision):
    st.session_state.decisions[finding_id] = decision


def render_findings(findings):
    if not findings:
        st.info("Находки отсутствуют.")
        return
    run_id = st.session_state.run_id
    type_options = list(TYPE_LABELS) + sorted({item.get("type", "не указан") for item in findings} - TYPE_LABELS.keys())
    severity_options = list(SEVERITY_LABELS) + sorted({item.get("severity", "не указана") for item in findings} - SEVERITY_LABELS.keys())
    type_column, severity_column = st.columns(2)
    with type_column:
        types = st.multiselect(
            "Тип находки", type_options, default=type_options,
            format_func=lambda value: f"{TYPE_LABELS.get(value, value)} ({value})",
            key=f"{run_id}:type_filter",
        )
    with severity_column:
        severities = st.multiselect(
            "Важность", severity_options, default=severity_options,
            format_func=lambda value: f"{SEVERITY_LABELS.get(value, value)} ({value})",
            key=f"{run_id}:severity_filter",
        )
    visible = [item for item in findings
               if item.get("type", "не указан") in types
               and item.get("severity", "не указана") in severities]
    st.caption(f"Показано: {len(visible)} из {len(findings)}. Решение пользователя не меняет проверку цитат.")
    if not visible:
        st.info("По выбранным фильтрам находок нет.")
    for finding in visible:
        finding_id = finding["id"]
        with st.container(border=True):
            st.subheader(finding.get("title") or "Без названия", anchor=False)
            kind, severity = finding.get("type", "не указан"), finding.get("severity", "не указана")
            st.caption(f"{TYPE_LABELS.get(kind, kind)} · Важность: {SEVERITY_LABELS.get(severity, severity)}")
            st.write(finding.get("description") or "Описание отсутствует.")
            st.text("Подразделения: " + (", ".join(finding.get("units") or []) or "не указаны"))
            render_evidence(finding.get("evidence"))
            decision = st.session_state.decisions.get(finding_id)
            st.text(f"Решение: {DECISION_LABELS.get(decision, 'не принято')}")
            confirm, reject = st.columns(2)
            confirm.button("Подтвердить", key=f"{run_id}:{finding_id}:confirm",
                           on_click=set_decision, args=(finding_id, "confirmed"), width="stretch")
            reject.button("Отклонить", key=f"{run_id}:{finding_id}:reject",
                          on_click=set_decision, args=(finding_id, "rejected"), width="stretch")


def render_result(result):
    tabs = st.tabs(["Подразделения", "Сопоставление функций", "Находки", "Заключение", "Журнал агента"])
    with tabs[0]:
        render_units(result.get("units") or [])
    with tabs[1]:
        render_functions(result.get("function_map") or [])
    with tabs[2]:
        render_findings(result.get("findings") or [])
    with tabs[3]:
        st.write(result.get("conclusion") or "Заключение отсутствует.")
        st.warning("Выводы рекомендательные. Учебные примеры нельзя использовать для решений по реальной оргструктуре.")
    with tabs[4]:
        st.caption("Все этапы — симуляция. Чтение документов и проверка цитат не выполнялись.")
        if st.session_state.journal:
            st.dataframe(st.session_state.journal, hide_index=True, width="stretch",
                         column_config={"time": "Время", "step": "step", "status": "status", "message": "message"})
        else:
            st.info("Журнал пуст.")


def main():
    st.set_page_config(page_title="Анализ организационной структуры", page_icon="↔", layout="wide")
    st.markdown("""
        <style>
        h1 { font-family: Georgia, serif !important; }
        </style>
    """, unsafe_allow_html=True)
    st.title("Анализ организационной структуры")
    st.warning(WARNING)
    mode_label = "демо (без ключей)" if config.demo_mode() else "демо-режим выключен"
    st.caption(f"Режим конфигурации: {mode_label}. В интерфейсе работает только локальная заглушка.")

    if "result" not in st.session_state:
        clear_run()
    before_column, after_column = st.columns(2)
    with before_column:
        with st.container(border=True):
            st.subheader("До", anchor=False)
            before = st.file_uploader("До", type=["pdf", "docx", "xlsx"], accept_multiple_files=True,
                                      key="before_uploads", label_visibility="collapsed")
    with after_column:
        with st.container(border=True):
            st.subheader("После", anchor=False)
            after = st.file_uploader("После", type=["pdf", "docx", "xlsx"], accept_multiple_files=True,
                                     key="after_uploads", label_visibility="collapsed")

    signature = input_fingerprint(before, after)
    if signature != st.session_state.get("input_signature"):
        clear_run()
        st.session_state.input_signature = signature

    compare_column, demo_column = st.columns(2)
    compare = compare_column.button("Сравнить", disabled=not (before and after), type="primary", width="stretch")
    demo = demo_column.button("Демо на тестовом комплекте", width="stretch")
    if compare:
        start_run(before, after, uploaded=True)
    elif demo:
        start_run(*sample_paths())

    if st.session_state.error:
        st.error(st.session_state.error)
    if st.session_state.result is not None:
        st.divider()
        st.caption("УЧЕБНЫЕ ПРИМЕРЫ · Не связаны с загруженными файлами и тестовым комплектом")
        render_result(st.session_state.result)
    elif not st.session_state.error:
        st.info("Добавьте файлы с обеих сторон или откройте демо на тестовом комплекте.")


if __name__ == "__main__":
    main()
