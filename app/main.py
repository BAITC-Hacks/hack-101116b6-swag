"""Document analysis and human review workflows; no identities or e-signatures."""

import hashlib
import math
import sys
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.agent import run as agent_run  # noqa: E402
from src.parse import read_text  # noqa: E402
from app.workflow import DEMO_PEOPLE, impact_cards, make_version, new_workspace  # noqa: E402
from app.approvals import render_approvals, approval_status  # noqa: E402
from app.acknowledgements import render_acknowledgements, render_onboarding  # noqa: E402
from app.ai_assistant import answer_question, enrich_analysis  # noqa: E402
from app.source_explorer import render_sources  # noqa: E402
from app.presentation import (  # noqa: E402
    install_design, render_brand, render_hero, render_notice,
    render_empty, render_footer, render_section_intro,
)
from app.interactive_ui import (  # noqa: E402
    RunProgress, install_transitions, motion_control, render_animated_chart,
    render_findings_overview, upload_summary,
)

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".txt"}
WARNING = (
    "Выводы рекомендательные. Цитата подтверждает источник, а интерпретацию "
    "и получателей изменений проверяет ответственный человек."
)
STATUS_LABELS = {
    "created": "Выявлено только после · кандидат на создание", "removed": "Не найдено после · кандидат на упразднение",
    "reorganized": "Признаки реорганизации", "kept": "Сопоставлено в обеих редакциях",
    "moved": "Кандидат на передачу", "changed": "Кандидат на изменение",
    "lost": "Пара не найдена · кандидат на потерю", "new": "Новая извлечённая функция",
}
TYPE_LABELS = {
    "loss": "Утрата функции",
    "duplicate": "Дублирование",
    "conflict": "Противоречие",
    "reorganization": "Реорганизация",
}
SEVERITY_LABELS = {"high": "Высокая", "medium": "Средняя", "low": "Низкая"}
# One colour per meaning across badges and charts: green appears, red disappears,
# orange moves or changes, gray stays the same.
STATUS_COLORS = {
    "created": "green", "new": "green", "создано": "green",
    "kept": "gray", "сохранено": "gray",
    "reorganized": "orange", "moved": "orange", "changed": "orange",
    "реорганизовано": "orange", "передано": "orange",
    "removed": "red", "lost": "red", "не сопоставлено": "red",
}
STATUS_ICONS = {"green": ":material/add_circle:", "gray": ":material/check_circle:",
                "orange": ":material/swap_horiz:", "red": ":material/remove_circle:"}
SHORT_STATUS = {
    "created": "Кандидат на создание", "removed": "Кандидат на упразднение",
    "reorganized": "Признаки реорганизации", "kept": "Найдено до и после",
    "moved": "Кандидат на передачу", "changed": "Кандидат на изменение",
    "lost": "Пара не найдена", "new": "Новая извлечённая функция",
}
CHART_COLORS = {"green": "#5B8A6E", "gray": "#8C9BA3", "orange": "#B9854A", "red": "#B06565", "blue": "#4F7F86"}
SEVERITY_COLORS = {"high": "red", "medium": "orange", "low": "gray"}
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
    """Keep the verified local result and optionally add separate AI candidates."""
    result = agent_run(before, after, use_llm=False, log=log)
    if st.session_state.get("ai_enabled", False) and config.openai_available():
        return enrich_analysis(result, before, after, log=log)
    return result


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
    st.session_state.update(result=None, journal=[], run_id=None, decisions={}, error=None,
                            source_documents=None, chat_history=[], active_version=None)


def uploads_changed():
    """Invalidate only real uploader edits, not widget cleanup during navigation."""
    clear_run()
    st.session_state.input_signature = input_fingerprint(
        st.session_state.get("before_uploads") or [],
        st.session_state.get("after_uploads") or [],
    )


def paginate_items(items, *, key, page_size=8):
    """Keep long result lists readable without recomputing the analysis."""
    if len(items) <= page_size:
        return items
    pages = math.ceil(len(items) / page_size)
    if not 1 <= st.session_state.get(key, 1) <= pages:
        st.session_state[key] = 1
    page = st.selectbox(
        "Страница", range(1, pages + 1), key=key, width=230,
        format_func=lambda number: f"{number} из {pages}",
        help="Переключение страницы сохраняет решения и не запускает анализ повторно.",
    )
    start = (page - 1) * page_size
    st.caption(f"Записи {start + 1}–{min(start + page_size, len(items))} из {len(items)}")
    return items[start:start + page_size]


def log(step, status, message):
    st.session_state.journal.append({
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "step": step,
        "status": status,
        "message": message,
    })


def start_run(before, after, *, uploaded=False, on_event=None):
    clear_run()
    st.session_state.run_id = uuid4().hex
    try:
        if not before or not after:
            st.session_state.error = "Нужен хотя бы один файл с каждой стороны. Проверьте комплект и повторите запуск."
            return
        def record_event(step, status, message):
            log(step, status, message)
            if on_event is not None:
                on_event(step, status, message)

        def analyze(paths_before, paths_after, names_before, names_after):
            documents = {}
            labels = {}
            for side, paths, names in (("before", paths_before, names_before), ("after", paths_after, names_after)):
                documents[side] = []
                for i, (path, name) in enumerate(zip(paths, names)):
                    name = Path(name.replace("\\", "/")).name
                    label = f"{'До' if side == 'before' else 'После'}/{i + 1}_{name}"
                    documents[side].append({"name": label, "content": path.read_bytes(), "text": read_text(path)})
                    labels[str(path)] = label
            result = run_analysis(paths_before, paths_after, log=record_event)
            # Resolve source labels while temporary files still exist; keep originals in memory.
            for group in ("units", "function_map", "findings", "ambiguous_matches", "ai_insights"):
                for item in result.get(group, []):
                    for source in item.get("evidence", []):
                        source["doc"] = labels.get(source.get("doc"), source.get("doc", ""))
            st.session_state.source_documents = documents
            return result

        if uploaded:
            if sum(len(upload.getvalue()) for upload in before + after) > 50 * 1024 * 1024:
                raise ValueError("The session document limit is 50 MiB")
            with materialize_uploads(before, after) as (before_paths, after_paths):
                result = analyze(before_paths, after_paths, [u.name for u in before], [u.name for u in after])
        else:
            result = analyze(before, after, [p.name for p in before], [p.name for p in after])
        st.session_state.result = result
        save_comparison()
        st.session_state.comparison_view = "detail"
    except Exception:
        # Exception text may contain document contents, paths or credentials.
        st.session_state.error = "Не удалось проанализировать комплект. Проверьте формат, наличие текста и общий размер файлов (до 50 МБ)."


def status_badge(status):
    """Badge whose colour means the same thing on every tab."""
    status = status or "не указан"
    color = STATUS_COLORS.get(status, "gray")
    st.badge(STATUS_LABELS.get(status, status), color=color, icon=STATUS_ICONS.get(color))


def evidence_label(evidence):
    if not evidence:
        return "Источники"
    verified = sum(source.get("verified") is True for source in evidence)
    return f"Источники · {len(evidence)} · проверено {verified}"


def render_evidence(evidence):
    with st.expander(evidence_label(evidence), expanded=False, icon=":material/format_quote:"):
        if not evidence:
            st.caption("Источники не указаны.")
            return
        st.caption("Проверка цитаты не подтверждает истинность всего вывода.")
        for index, source in enumerate(evidence):
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                if source.get("verified") is True:
                    st.badge("Цитата проверена", color="green", icon=":material/check:")
                else:
                    st.badge("Цитата не проверена", color="yellow", icon=":material/help:")
                st.caption(f"{source.get('doc') or 'Документ не указан'} · п. {source.get('clause') or 'не указан'}")
            with st.container(border=True):
                st.text(source.get("quote") or "Цитата не указана")


def similarity_label(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "не указано"
    if not math.isfinite(number) or not 0 <= number <= 1:
        return "не указано"
    return f"{number:.0%}"


def view_switch(key):
    """Cards for checking sources, a table for scanning the whole list."""
    return st.segmented_control(
        "Вид", ["Карточки", "Таблица"], default="Карточки", required=True,
        key=key, label_visibility="collapsed",
    ) or "Карточки"


def verified_share(evidence):
    evidence = evidence or []
    return f"{sum(source.get('verified') is True for source in evidence)} из {len(evidence)}"


def render_units(units):
    if not units:
        st.info("Подразделения отсутствуют.")
        return
    run_id = st.session_state.run_id
    if view_switch(f"{run_id}:units_view") == "Таблица":
        st.dataframe(
            [{"Подразделение": unit.get("name") or "", "Сокращение": unit.get("abbr") or "",
              "Статус": STATUS_LABELS.get(unit.get("status"), unit.get("status") or ""),
              "Проверено цитат": verified_share(unit.get("evidence"))} for unit in units],
            hide_index=True, width="stretch",
        )
        return
    for unit in paginate_items(units, key=f"{run_id}:units_page"):
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"**{unit.get('name') or 'Название не указано'}**")
                st.space("stretch")
                status_badge(unit.get("status"))
            st.caption(f"Сокращение: {unit.get('abbr') or 'не указано'}")
            render_evidence(unit.get("evidence"))


def similarity_value(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 1 else None


def render_functions(function_map):
    if not function_map:
        st.info("Сопоставления функций отсутствуют.")
        return
    run_id = st.session_state.run_id
    if view_switch(f"{run_id}:functions_view") == "Таблица":
        st.dataframe(
            [{"До: подразделение": item.get("before_unit") or "", "До: функция": item.get("before_function") or "",
              "После: подразделение": item.get("after_unit") or "", "После: функция": item.get("after_function") or "",
              "Статус": STATUS_LABELS.get(item.get("status"), item.get("status") or ""),
              "Сходство": similarity_value(item.get("similarity"))} for item in function_map],
            hide_index=True, width="stretch",
            column_config={"Сходство": st.column_config.ProgressColumn(
                "Сходство", format="percent", min_value=0, max_value=1,
                help="Сходство формулировок, а не достоверность вывода")},
        )
        return
    for item in paginate_items(function_map, key=f"{run_id}:functions_page"):
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                status_badge(item.get("status"))
                st.space("stretch")
                st.caption(f"Сходство формулировок: {similarity_label(item.get('similarity'))}",
                           help="Это не оценка достоверности вывода")
            before_column, arrow_column, after_column = st.columns([10, 1, 10], vertical_alignment="center")
            for column, side, label in ((before_column, "before", "До"), (after_column, "after", "После")):
                with column:
                    st.caption(f"{label} · {item.get(f'{side}_unit') or 'Подразделение не указано'}")
                    st.write(item.get(f"{side}_function") or "Функция не указана")
            arrow_column.markdown(":gray[:material/arrow_forward:]")
            render_evidence(item.get("evidence"))


def set_decision(finding_id, decision):
    st.session_state.decisions[finding_id] = decision
    st.toast(f"Решение сохранено: {DECISION_LABELS[decision]}",
             icon=":material/check:" if decision == "confirmed" else ":material/close:")


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
            format_func=lambda value: TYPE_LABELS.get(value, value),
            placeholder="Выберите типы", wrap=True,
            key=f"{run_id}:type_filter",
        )
    with severity_column:
        severities = st.multiselect(
            "Важность", severity_options, default=severity_options,
            format_func=lambda value: SEVERITY_LABELS.get(value, value),
            placeholder="Выберите важность", wrap=True,
            key=f"{run_id}:severity_filter",
        )
    visible = [item for item in findings
               if item.get("type", "не указан") in types
               and item.get("severity", "не указана") in severities]
    st.caption(f"Показано: {len(visible)} из {len(findings)}. Решение пользователя не меняет проверку цитат.")
    if not visible:
        st.info("По выбранным фильтрам находок нет.")
    for finding in paginate_items(visible, key=f"{run_id}:findings_page", page_size=6):
        finding_id = finding["id"]
        with st.container(border=True):
            kind, severity = finding.get("type", "не указан"), finding.get("severity", "не указана")
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                st.badge("Важность: " + SEVERITY_LABELS.get(severity, severity),
                         color=SEVERITY_COLORS.get(severity, "gray"), icon=":material/flag:")
                st.badge(TYPE_LABELS.get(kind, kind), color="blue")
            st.subheader(finding.get("title") or "Без названия", anchor=False)
            st.write(finding.get("description") or "Описание отсутствует.")
            st.caption("Подразделения: " + (", ".join(finding.get("units") or []) or "не указаны"))
            render_evidence(finding.get("evidence"))
            decision = st.session_state.decisions.get(finding_id)
            with st.container(horizontal=True, vertical_alignment="center"):
                st.button("Подтвердить", key=f"{run_id}:{finding_id}:confirm", icon=":material/check:",
                          on_click=set_decision, args=(finding_id, "confirmed"),
                          type="primary" if decision == "confirmed" else "secondary")
                st.button("Отклонить", key=f"{run_id}:{finding_id}:reject", icon=":material/close:",
                          on_click=set_decision, args=(finding_id, "rejected"),
                          type="primary" if decision == "rejected" else "secondary")
                st.caption(f"Решение: {DECISION_LABELS.get(decision, 'не принято')}")


def render_result(result):
    tabs = st.tabs(["Подразделения", "Сопоставление функций", "Находки", "Заключение", "Журнал агента", "Структура и пункты"])
    with tabs[0]:
        st.caption("Посмотрите, какие подразделения найдены в документах, и раскройте источники для проверки.")
        render_units(result.get("units") or [])
    with tabs[1]:
        st.caption("Слева — функция до изменений, справа — её возможное соответствие после.")
        render_functions(result.get("function_map") or [])
        ambiguous = result.get("ambiguous_matches") or []
        if ambiguous:
            st.warning(f"Неоднозначных записей: {len(ambiguous)}. Они не объявлены потерянными или новыми.")
            for index, item in enumerate(ambiguous):
                with st.expander(f"Требует проверки {index + 1}: {item.get('unit', '')}"):
                    st.text(item.get("function", ""))
                    for candidate in item.get("candidates", []):
                        st.text(f"Кандидат: {candidate.get('unit', '')} · {candidate.get('function', '')}")
                    render_evidence(item.get("evidence"))
    with tabs[2]:
        st.caption("Отберите находки по типу и важности, проверьте цитаты и отметьте своё решение.")
        render_findings(result.get("findings") or [])
    with tabs[3]:
        with st.container(border=True):
            st.write(result.get("conclusion") or "Заключение отсутствует.")
        st.warning("Выводы рекомендательные. Локальные правила могут пропускать функции и неверно сопоставлять переформулировки.")
        if result.get("ai_status"):
            st.info(result["ai_status"])
        if result.get("ai_insights"):
            st.subheader("Наблюдения ИИ для проверки", anchor=False)
            st.caption("Модель анализирует изменённые пункты. Наблюдения не добавлены в проверенное заключение автоматически.")
            for item in result["ai_insights"]:
                with st.container(border=True):
                    st.write(f"**{item['summary']}**")
                    st.write(item["explanation"])
                    render_evidence(item["evidence"])
    with tabs[4]:
        st.caption("Журнал фактически выполненных этапов; вызов OpenAI отмечается отдельно.")
        if st.session_state.journal:
            st.dataframe(st.session_state.journal, hide_index=True, width="stretch",
                         column_config={"time": "Время", "step": "Этап", "status": "Статус", "message": "Сообщение"})
        else:
            st.info("Журнал пуст.")
    with tabs[5]:
        render_sources(st.session_state.get("source_documents"), st.session_state.get("run_id"))


def render_impact(result):
    cards = impact_cards(result)
    if not cards:
        with st.container(border=True, key="empty_approval"):
            render_empty("Пока нечего согласовывать",
                         "В этом сравнении нет изменений с подтверждёнными источниками. "
                         "Если документы обновились, создайте новое сравнение.")
        return
    st.subheader("Кого затронули изменения", anchor=False)
    st.caption("Выберите изменения, проверьте источники и назначьте получателей. Отправки сообщений нет.")
    by_id = {card["id"]: card for card in cards}
    run_id = st.session_state.run_id
    selected = st.multiselect("Изменения для проверки", list(by_id),
                              format_func=lambda key: f"{by_id[key]['unit']} · {STATUS_LABELS.get(by_id[key]['status'], by_id[key]['status'])} · {by_id[key]['after'][:65]}",
                              key=f"{run_id}:impact_selection", placeholder="Выберите изменения", wrap=True)
    with st.expander("Список получателей · проверьте перед назначением", expanded=bool(selected)):
        st.caption("По умолчанию указаны вымышленные участники. Замените их своим списком.")
        people_text = st.text_area("Получатели: имя | должность или подразделение (одна строка на человека)",
                                  value="\n".join(f"{p['name']} | {p['role']}" for p in DEMO_PEOPLE), key=f"{run_id}:people",
                                  help="Например: Имя сотрудника | Отдел контроля")
    recipients, invalid = [], False
    for line in people_text.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 2 or not all(parts):
            invalid = True
            break
        recipients.append({"id": hashlib.sha256(line.strip().encode()).hexdigest()[:16], "name": parts[0], "role": parts[1]})
    if invalid:
        st.warning("В каждой строке нужны имя и роль, разделённые символом |.")
        return
    selected_cards = []
    for key in selected:
        card = dict(by_id[key])
        with st.container(border=True):
            st.subheader(card["unit"], anchor=False)
            left, right = st.columns(2)
            left.text("До: " + card["before"])
            right.text("После: " + card["after"])
            render_evidence(card["evidence"])
            card["recipient_ids"] = st.multiselect(
                "Кому относится это изменение", [p["id"] for p in recipients],
                format_func=lambda value: next(p["name"] + " · " + p["role"] for p in recipients if p["id"] == value),
                key=f"{run_id}:targets:{key}", placeholder="Выберите получателей", wrap=True)
        selected_cards.append(card)
    st.subheader("Параметры версии", anchor=False)
    title_col, revision_col = st.columns([3, 1])
    title = title_col.text_input("Название пакета", value="Изменения обязанностей", key=f"{run_id}:version_title")
    revision = revision_col.text_input("Редакция пакета", value="1", key=f"{run_id}:revision")
    reviewer = st.text_input("Ответственный за проверку", key=f"{run_id}:reviewed_by", placeholder="Имя ответственного")
    checked = st.checkbox("Я проверил выбранные изменения, цитаты и получателей", key=f"{run_id}:reviewed")
    if not selected_cards:
        st.caption("Сначала выберите хотя бы одно изменение в поле выше.")
    if st.button("Создать версию для согласования", disabled=not checked or not selected_cards, key=f"{run_id}:freeze",
                 type="primary", icon=":material/assignment_turned_in:", wrap=True):
        try:
            assigned = {rid for c in selected_cards for rid in c["recipient_ids"]}
            version_id = make_version(st.session_state.workspace, title=title, revision=revision, reviewed_by=reviewer,
                                      documents=st.session_state.source_documents["after"],
                                      reference_documents=st.session_state.source_documents["before"],
                                      changes=selected_cards, recipients=[p for p in recipients if p["id"] in assigned],
                                      comparison_id=run_id)
            st.session_state.active_version = version_id
            save_comparison()
            st.session_state.comparison_section = "Согласование"
            st.rerun()
        except ValueError as error:
            st.error(str(error))


def open_ai_chat():
    st.session_state.chat_dialog_run_id = st.session_state.run_id


def close_ai_chat():
    st.session_state.pop("chat_dialog_run_id", None)


@st.dialog("ИИ-помощник", width="medium", icon=":material/chat:", on_dismiss=close_ai_chat)
def render_ai_dialog():
    record = st.session_state.comparisons.get(st.session_state.run_id, {})
    st.caption(f"Текущее сравнение: {record.get('title', 'Документы')}")
    render_chat_page(in_dialog=True)
    if st.button("Вернуться к результату", key="close_ai_chat", icon=":material/arrow_back:"):
        close_ai_chat()
        st.rerun()


def render_chat_page(*, in_dialog=False):
    if st.session_state.get("result") is None or not st.session_state.get("source_documents"):
        st.info("Сначала откройте сравнение с обработанными документами.")
        return
    if not in_dialog:
        st.header("Вопросы по сравнению", anchor=False)
    st.caption("Ответы — рекомендации. Проверяйте пункты и цитаты." if in_dialog else
               "Ответы ИИ — рекомендации по обработанному комплекту. Проверяйте приведённые пункты и цитаты.")
    if not config.openai_available():
        st.info("Без ключа работает поиск близких выдержек; ситуационные ответы ИИ недоступны.")
    with st.container(height=260 if in_dialog else "content", border=False,
                      autoscroll=in_dialog, key="ai_chat_history" if in_dialog else "chat_page_history"):
        if not st.session_state.get("chat_history"):
            with st.chat_message("assistant"):
                st.write("Что хотите уточнить в этом сравнении?")
                st.caption("Например: «Кому передали обязанности?» или «Где есть дублирование функций?»")
        for message in st.session_state.get("chat_history", []):
            with st.chat_message(message["role"]):
                st.write(message["text"])
                if message.get("evidence"):
                    render_evidence(message["evidence"])
    limit_reached = len(st.session_state.get("chat_history", [])) >= 40
    if limit_reached:
        st.info("Достигнут лимит 20 вопросов для этого сравнения. Новый анализ сбросит историю чата.")
    question = st.chat_input("Спросите о различиях или опишите ситуацию", max_chars=2000,
                             disabled=limit_reached,
                             key=f"chat:{st.session_state.run_id}:{'dialog' if in_dialog else 'page'}")
    if question:
        if not question.strip():
            st.warning("Введите вопрос по документам.")
            return
        history = st.session_state.chat_history
        with st.spinner("Ищу ответ в документах…"):
            reply = answer_question(question, st.session_state.source_documents,
                                    st.session_state.result, history)
        history.append({"role": "user", "text": question})
        history.append({"role": "assistant", "text": reply["answer"],
                        "evidence": reply["evidence"], "mode": reply["mode"]})
        save_comparison()
        st.rerun()


def render_navigation():
    with st.container(key="brand_bar"):
        brand, settings = st.columns([4, 1], vertical_alignment="center")
        with brand:
            render_brand()
        with settings:
            with st.popover("Параметры", icon=":material/tune:", width="stretch"):
                st.markdown("**Рабочее пространство**")
                versions = len(st.session_state.workspace["versions"])
                st.caption(f"Версий в этой сессии: {versions}")
                with_ai = config.openai_available() and st.session_state.get("ai_enabled", True)
                st.badge("Локально + OpenAI" if with_ai else "Локальный анализ",
                         icon=":material/computer:", color="gray")
                motion_control()
                st.divider()
                st.markdown("**О прототипе**")
                st.caption("Выбор участника — симуляция. Нет проверки личности, ЭЦП и корпоративных интеграций.")
                st.caption("Данные хранятся только в текущей сессии браузера. Полное обновление страницы может завершить сессию.")
    with st.container(key="primary_nav"):
        page = st.radio(
            "Раздел", ["Мои сравнения", "Мои документы", "Документы новичка"], key="active_page", label_visibility="collapsed", horizontal=True, width="stretch",
        )
    return page


def count_by(items, field, labels, colors):
    counts = {}
    for item in items:
        key = item.get(field) or "не указан"
        counts[key] = counts.get(key, 0) + 1
    return [{"Категория": labels.get(key, key), "Количество": number,
             "color": CHART_COLORS[colors.get(key, "gray")]} for key, number in counts.items()]


def render_chart(rows, title, bars):
    render_animated_chart(rows, title, bars)


def render_overview(result):
    units, functions = result.get("units") or [], result.get("function_map") or []
    findings = result.get("findings") or []
    high = sum(item.get("severity") == "high" for item in findings)
    columns = iter(st.columns(4))
    with next(columns):
        st.metric("Подразделения", len(units), border=True, icon=":material/account_tree:",
                  delta=f"только после: {sum(u.get('status') == 'created' for u in units)}",
                  delta_color="off", delta_arrow="off")
    with next(columns):
        st.metric("Сопоставления функций", len(functions), border=True, icon=":material/compare_arrows:",
                  delta=f"без пары: {sum(f.get('status') == 'lost' for f in functions)}",
                  delta_color="off", delta_arrow="off")
    with next(columns):
        st.metric("Находки", len(findings), border=True, icon=":material/flag:",
                  delta=f"высокой важности: {high}",
                  delta_color="off", delta_arrow="off")
    with next(columns):
        st.metric("Решения приняты", f"{len(st.session_state.decisions)} из {len(findings)}",
                  border=True, icon=":material/task_alt:", delta="по находкам", delta_color="off", delta_arrow="off")
    charts = [(count_by(units, "status", SHORT_STATUS, STATUS_COLORS), "Подразделения по статусу"),
              (count_by(functions, "status", SHORT_STATUS, STATUS_COLORS), "Функции по статусу")]
    bars = max(len(rows) for rows, _ in charts) or 1
    for column, (rows, title) in zip(st.columns(2), charts):
        with column:
            render_chart(rows, title, bars)
    render_findings_overview(findings, st.session_state.decisions)


def render_analysis_page():
    if "result" not in st.session_state:
        clear_run()
    has_result = st.session_state.result is not None
    st.header("1. Выберите документы", anchor=False)
    with st.expander("Комплекты до и после изменений", expanded=not has_result, icon=":material/folder_open:"):
        st.caption("PDF с текстом, DOCX, XLSX или TXT. Общий размер загруженных файлов — до 50 МБ.")
        before_column, after_column = st.columns(2, gap="medium")
        with before_column:
            with st.container(border=True, key="upload_before"):
                st.subheader("До", anchor=False)
                st.caption("Действующая или предыдущая редакция")
                before = st.file_uploader(
                    "До", type=["pdf", "docx", "xlsx", "txt"], accept_multiple_files=True,
                    key="before_uploads", label_visibility="collapsed", on_change=uploads_changed,
                    max_upload_size=50,
                )
                upload_summary(before)
        with after_column:
            with st.container(border=True, key="upload_after"):
                st.subheader("После", anchor=False)
                st.caption("Новая редакция для сравнения")
                after = st.file_uploader(
                    "После", type=["pdf", "docx", "xlsx", "txt"], accept_multiple_files=True,
                    key="after_uploads", label_visibility="collapsed", on_change=uploads_changed,
                    max_upload_size=50,
                )
                upload_summary(after)
        if "input_signature" not in st.session_state:
            st.session_state.input_signature = input_fingerprint(before, after)
        available = config.openai_available()
        st.toggle("Улучшить анализ с OpenAI", value=available,
                  disabled=not available, key="ai_enabled",
                  help="Изменённые пункты передаются в OpenAI. Без ключа анализ выполняется локально.")
        with st.container(horizontal=True, vertical_alignment="center"):
            compare = st.button("Сравнить", disabled=not (before and after), type="primary", icon=":material/compare_arrows:")
            if before and after:
                st.caption("Комплекты готовы к сравнению")
            else:
                st.caption("Чтобы начать, добавьте хотя бы один файл в каждый комплект.")

    with st.expander("Попробовать без загрузки файлов", expanded=not has_result, icon=":material/play_circle:"):
        st.caption("Тестовый комплект показывает сравнение двух редакций. Синтетический пример помогает пройти весь процесс согласования.")
        with st.container(horizontal=True):
            demo = st.button("Демо на тестовом комплекте", icon=":material/description:", wrap=True)
            synthetic = st.button("Синтетический пример: подключения и кабельные работы", icon=":material/science:", wrap=True)
    if compare or demo or synthetic:
        progress = RunProgress()
        if compare:
            start_run(before, after, uploaded=True, on_event=progress)
        elif demo:
            start_run(*sample_paths(), on_event=progress)
        else:
            start_run(*[sorted((ROOT / "data" / "control" / side).glob("*.txt")) for side in ("before", "after")],
                      on_event=progress)
        progress.finish(success=st.session_state.result is not None)
        if st.session_state.result is not None:
            st.rerun()

    if st.session_state.error:
        st.error(st.session_state.error, icon=":material/error:")
    if st.session_state.result is None:
        return

    render_comparison()


COMPARISON_FIELDS = ("result", "journal", "run_id", "decisions", "source_documents",
                     "chat_history", "active_version", "input_signature")


def save_comparison():
    if st.session_state.get("result") is None:
        return
    comparisons = st.session_state.setdefault("comparisons", {})
    run_id = st.session_state.run_id
    previous = comparisons.get(run_id, {})
    docs = (st.session_state.get("source_documents") or {}).get("after", [])
    comparisons[run_id] = {
        **{key: deepcopy(st.session_state.get(key)) for key in COMPARISON_FIELDS},
        "title": previous.get("title") or (docs[0]["name"].split("/", 1)[-1].split("_", 1)[-1] if docs else "Сравнение документов"),
        "created_at": previous.get("created_at") or datetime.now().astimezone().strftime("%d.%m.%Y · %H:%M"),
    }


def open_comparison(run_id):
    save_comparison()
    record = st.session_state.comparisons[run_id]
    for key in COMPARISON_FIELDS:
        st.session_state[key] = deepcopy(record.get(key))
    st.session_state.comparison_view = "detail"
    st.session_state.comparison_section = "Результат"


def new_comparison():
    save_comparison()
    clear_run()
    for key in ("before_uploads", "after_uploads", "input_signature"):
        st.session_state.pop(key, None)
    st.session_state.comparison_view = "new"
    st.session_state.comparison_section = "Результат"


def show_comparisons():
    save_comparison()
    st.session_state.comparison_view = "list"


def show_section(section):
    st.session_state.comparison_section = section


def render_comparisons():
    comparisons = st.session_state.comparisons
    if not comparisons:
        with st.container(border=True, key="empty_state"):
            render_empty("Начните с первого сравнения", "Загрузите документы «до» и «после» или попробуйте готовый пример. "
                         "Здесь появятся результаты, вопросы и статус согласования каждого комплекта.", symbol="↔")
            st.button("Сравнить документы", type="primary", icon=":material/add:", on_click=new_comparison)
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("Сравнить документы", type="primary", icon=":material/add:", on_click=new_comparison)
        st.caption(f"Сравнений в этой сессии: {len(comparisons)}")
    for run_id, record in reversed(list(comparisons.items())):
        with st.container(border=True, key=f"comparison_card_{run_id}"):
            st.subheader(record["title"], anchor=False)
            version_id = record.get("active_version")
            state = approval_status(st.session_state.workspace, version_id) if version_id else "result"
            label = {"result": "Результат готов", "not_started": "Подготовлено к согласованию",
                     "pending": "На согласовании", "returned": "Требует доработки", "approved": "Согласовано"}[state]
            st.badge(label, color="green" if state == "approved" else "gray")
            st.caption(f"{record['created_at']} · Находок: {len(record['result'].get('findings', []))}")
            st.button("Открыть сравнение", key=f"open:{run_id}", on_click=open_comparison, args=(run_id,), icon=":material/arrow_forward:")


def render_comparison():
    result = st.session_state.result
    run_id = st.session_state.run_id
    record = st.session_state.comparisons[run_id]
    with st.container(border=True, key="comparison_heading"):
        st.caption(f"СРАВНЕНИЕ ДОКУМЕНТОВ · {record['created_at']}")
        st.title(record["title"], anchor=False)
        render_notice(WARNING)
    version_id = st.session_state.get("active_version")
    approved = bool(version_id and approval_status(st.session_state.workspace, version_id) == "approved")
    options = ["Результат", "Вопросы", "Согласование"]
    if approved:
        options.append("Ознакомление")
    section = st.session_state.get("comparison_section", "Результат")
    if section not in options:
        section = "Результат"
    with st.container(horizontal=True, key="comparison_nav"):
        for option in options:
            st.button(option, key=f"section:{option}", type="primary" if option == section else "secondary",
                      on_click=show_section, args=(option,))
    render_section_intro(section)
    if section == "Вопросы":
        render_chat_page()
    elif section == "Согласование":
        if version_id:
            render_approvals(st.session_state.workspace, version_id)
            if approval_status(st.session_state.workspace, version_id) == "returned":
                with st.expander("Подготовить новую редакцию"):
                    render_impact(result)
            if approval_status(st.session_state.workspace, version_id) == "approved":
                st.button("Назначить ознакомление", type="primary", on_click=show_section, args=("Ознакомление",))
        else:
            render_impact(result)
    elif section == "Ознакомление":
        render_acknowledgements(st.session_state.workspace, version_id)
        with st.expander("Собрать пакет новичку"):
            render_onboarding(st.session_state.workspace)
    else:
        st.subheader("Краткое резюме", anchor=False)
        st.write(result.get("conclusion") or "Заключение отсутствует.")
        findings = result.get("findings") or []
        important = sorted(findings, key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(item.get("severity"), 3))[:3]
        st.subheader("Важные находки", anchor=False)
        if not important:
            st.info("Находки отсутствуют.")
        for finding in important:
            with st.expander(f"{SEVERITY_LABELS.get(finding.get('severity'), 'Не указана')} важность · {finding.get('title', 'Находка')}"):
                st.write(finding.get("description", ""))
                render_evidence(finding.get("evidence"))
        with st.container(border=True, key="ai_assistant_card"):
            explanation, action = st.columns([2, 1], gap="medium", vertical_alignment="center")
            with explanation:
                st.subheader("ИИ-помощник по документам", anchor=False)
                st.write("Обсудите изменения и найдите нужный пункт. Чат откроется в отдельном окне.")
            with action:
                st.button("Спросить ИИ", icon=":material/chat:", type="primary", width="stretch",
                          key="open_ai_chat", on_click=open_ai_chat)
        with st.container(horizontal=True):
            st.button("Передать на согласование", icon=":material/assignment_turned_in:", on_click=show_section, args=("Согласование",))
        from src.report import build_docx
        st.download_button("Скачать отчёт", build_docx(result), file_name="comparison-report.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", icon=":material/download:")
        with st.expander("Графики и показатели"):
            render_overview(result)
        with st.expander("Все находки, функции и источники"):
            render_result(result)
        with st.expander("Исходные документы"):
            for side, docs in (st.session_state.source_documents or {}).items():
                st.caption("До" if side == "before" else "После")
                for index, doc in enumerate(docs):
                    st.download_button(doc["name"], doc["content"], file_name=doc["name"].split("/")[-1],
                                       key=f"source:{run_id}:{side}:{index}")
    save_comparison()



def main():
    st.set_page_config(page_title="Оргструктура · документы и решения", page_icon=":material/account_tree:", layout="wide")
    if "workspace" not in st.session_state:
        st.session_state.workspace = new_workspace()
    st.session_state.setdefault("comparisons", {})
    st.session_state.setdefault("comparison_view", "list")
    install_design()
    install_transitions()
    with st.container(key="app_shell"):
        page = render_navigation()
        view = st.session_state.comparison_view
        if page == "Документы новичка":
            from app.onboarding_ui import render_onboarding_page
            render_hero("Документы новичка", compact=True)
            with st.container(key="workspace"):
                render_onboarding_page(st.session_state.workspace)
        elif page == "Мои документы":
            from app.acknowledgements import render_my_documents
            render_hero("Мои документы", compact=True)
            st.html('<div id="workspace"></div>')
            with st.container(key="workspace"):
                render_my_documents(st.session_state.workspace)
        elif view == "list":
            render_hero("Мои сравнения", compact=bool(st.session_state.comparisons))
            render_notice(WARNING)
            st.html('<div id="workspace"></div>')
            with st.container(key="workspace"):
                render_comparisons()
        else:
            st.button("Мои сравнения", icon=":material/arrow_back:", on_click=show_comparisons)
            if view == "new":
                render_hero("Анализ изменений", compact=True)
                render_notice(WARNING)
                st.html('<div id="workspace"></div>')
                with st.container(key="workspace"):
                    render_analysis_page()
            elif st.session_state.get("result") is not None:
                with st.container(key="workspace"):
                    render_comparison()
        render_footer()
    dialog_run = st.session_state.get("chat_dialog_run_id")
    if (dialog_run and dialog_run == st.session_state.get("run_id")
            and page == "Мои сравнения" and view == "detail"):
        render_ai_dialog()
    elif dialog_run:
        close_ai_chat()


if __name__ == "__main__":
    main()
