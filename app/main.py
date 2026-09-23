"""Document analysis and human review workflows; no identities or e-signatures."""

import hashlib
import math
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

from src import config  # noqa: E402
from src.agent import run as agent_run  # noqa: E402
from src.parse import read_text  # noqa: E402
from app.workflow import DEMO_PEOPLE, impact_cards, make_version, new_workspace  # noqa: E402
from app.approvals import render_approvals  # noqa: E402
from app.acknowledgements import render_acknowledgements, render_onboarding  # noqa: E402
from app.ai_assistant import answer_question, enrich_analysis  # noqa: E402

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
                            source_documents=None, chat_history=[])


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
            with st.spinner("Сравниваем документы и проверяем изменённые пункты..."):
                result = run_analysis(paths_before, paths_after, log=log)
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
    except Exception:
        # Exception text may contain document contents, paths or credentials.
        st.session_state.error = "Не удалось проанализировать комплект. Проверьте формат, наличие текста и общий размер файлов (до 50 МБ)."


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
            st.text(f"Статус: {STATUS_LABELS.get(unit.get('status'), unit.get('status') or 'не указан')}")
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
            st.text(f"Статус: {STATUS_LABELS.get(item.get('status'), item.get('status') or 'не указан')} · Сходство: {similarity_label(item.get('similarity'))}")
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
        render_findings(result.get("findings") or [])
    with tabs[3]:
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
                         column_config={"time": "Время", "step": "step", "status": "status", "message": "message"})
        else:
            st.info("Журнал пуст.")


def render_impact(result):
    st.header("Кого затронули изменения")
    st.caption("Выберите изменения, проверьте источники и назначьте получателей. Отправки сообщений нет.")
    cards = impact_cards(result)
    if not cards:
        st.info("Нет изменений с проверенными цитатами для передачи на согласование.")
        return
    by_id = {card["id"]: card for card in cards}
    run_id = st.session_state.run_id
    selected = st.multiselect("Изменения для проверки", list(by_id),
                              format_func=lambda key: f"{by_id[key]['unit']} · {STATUS_LABELS.get(by_id[key]['status'], by_id[key]['status'])} · {by_id[key]['after'][:65]}",
                              key=f"{run_id}:impact_selection")
    people_text = st.text_area("Получатели: имя | должность или подразделение (одна строка на человека)",
                              value="\n".join(f"{p['name']} | {p['role']}" for p in DEMO_PEOPLE), key=f"{run_id}:people")
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
                key=f"{run_id}:targets:{key}")
        selected_cards.append(card)
    title = st.text_input("Название пакета", value="Изменения обязанностей", key=f"{run_id}:version_title")
    revision = st.text_input("Редакция пакета", value="1", key=f"{run_id}:revision")
    reviewer = st.text_input("Ответственный за проверку", key=f"{run_id}:reviewed_by")
    checked = st.checkbox("Я проверил выбранные изменения, цитаты и получателей", key=f"{run_id}:reviewed")
    if st.button("Создать версию для согласования", disabled=not checked or not selected_cards, key=f"{run_id}:freeze"):
        try:
            assigned = {rid for c in selected_cards for rid in c["recipient_ids"]}
            version_id = make_version(st.session_state.workspace, title=title, revision=revision, reviewed_by=reviewer,
                                      documents=st.session_state.source_documents["after"],
                                      reference_documents=st.session_state.source_documents["before"],
                                      changes=selected_cards, recipients=[p for p in recipients if p["id"] in assigned])
            st.session_state.active_version = version_id
            st.success(f"Версия {revision} · {version_id[:12]} сохранена в этой сессии. Откройте «Согласование» слева.")
        except ValueError as error:
            st.error(str(error))


def render_workflow_page(page):
    workspace = st.session_state.workspace
    if page == "Документы новичка":
        render_onboarding(workspace)
        return
    versions = workspace["versions"]
    if not versions:
        st.info("Сначала выполните анализ, проверьте изменения и создайте версию для согласования.")
        return
    choices = list(versions)
    active = st.session_state.get("active_version", choices[-1])
    version_id = st.selectbox("Версия документа", choices, index=choices.index(active) if active in choices else 0,
                             format_func=lambda vid: f"{versions[vid]['title']} · ред. {versions[vid]['revision']} · {vid[:12]}",
                             key=f"workflow:{page}:version")
    with st.expander("Исходные документы «до»"):
        for index, doc in enumerate(versions[version_id].get("reference_documents", [])):
            st.download_button(doc["name"], doc["content"], file_name=doc["name"].split("/")[-1], key=f"ref:{page}:{version_id}:{index}")
    if page == "Согласование":
        render_approvals(workspace, version_id)
    else:
        render_acknowledgements(workspace, version_id)


def render_chat_page():
    st.header("ИИ-чат по изменениям")
    if st.session_state.get("result") is None or not st.session_state.get("source_documents"):
        st.info("Сначала сравните документы в разделе «Анализ изменений».")
        return
    st.caption("Ответы ИИ — рекомендации по обработанному комплекту. Проверяйте приведённые пункты и цитаты.")
    if not config.openai_available():
        st.info("Без ключа работает поиск близких выдержек; ситуационные ответы ИИ недоступны.")
    for message in st.session_state.get("chat_history", []):
        with st.chat_message(message["role"]):
            st.write(message["text"])
            if message.get("evidence"):
                render_evidence(message["evidence"])
    limit_reached = len(st.session_state.get("chat_history", [])) >= 40
    if limit_reached:
        st.info("Достигнут лимит 20 вопросов для этого сравнения. Новый анализ сбросит историю чата.")
    question = st.chat_input("Спросите о различиях или опишите ситуацию", max_chars=2000,
                             disabled=limit_reached)
    if question:
        history = st.session_state.chat_history
        reply = answer_question(question, st.session_state.source_documents,
                                st.session_state.result, history)
        history.append({"role": "user", "text": question})
        history.append({"role": "assistant", "text": reply["answer"],
                        "evidence": reply["evidence"], "mode": reply["mode"]})
        st.rerun()


def main():
    st.set_page_config(page_title="Анализ организационной структуры", page_icon="↔", layout="wide")
    st.markdown("""
        <style>
        h1 { font-family: Georgia, serif !important; }
        </style>
    """, unsafe_allow_html=True)
    st.title("Анализ организационной структуры")
    st.warning(WARNING)
    st.caption("Анализ → проверка изменений → согласование → ознакомление. Работает без ключей.")
    st.sidebar.markdown("## Документы и изменения")
    page = st.sidebar.radio("Раздел", ["Анализ изменений", "ИИ-чат", "Согласование", "Ознакомление", "Документы новичка"])
    st.sidebar.info("Прототип: выбор участника — симуляция. Нет проверки личности, ЭЦП и корпоративных интеграций. Данные хранятся только в текущей сессии браузера.")
    if "workspace" not in st.session_state:
        st.session_state.workspace = new_workspace()
    if page == "ИИ-чат":
        render_chat_page()
        return
    if page != "Анализ изменений":
        render_workflow_page(page)
        return

    if "result" not in st.session_state:
        clear_run()
    st.caption("PDF, DOCX, XLSX или TXT · до 50 МБ на весь загружаемый комплект · PDF должен содержать текст.")
    before_column, after_column = st.columns(2)
    with before_column:
        with st.container(border=True):
            st.subheader("До", anchor=False)
            before = st.file_uploader("До", type=["pdf", "docx", "xlsx", "txt"], accept_multiple_files=True,
                                      key="before_uploads", label_visibility="collapsed")
    with after_column:
        with st.container(border=True):
            st.subheader("После", anchor=False)
            after = st.file_uploader("После", type=["pdf", "docx", "xlsx", "txt"], accept_multiple_files=True,
                                     key="after_uploads", label_visibility="collapsed")

    signature = input_fingerprint(before, after)
    if signature != st.session_state.get("input_signature"):
        clear_run()
        st.session_state.input_signature = signature

    available = config.openai_available()
    st.toggle("Улучшить анализ с OpenAI", value=available,
              disabled=not available, key="ai_enabled",
              help="Изменённые пункты передаются в OpenAI. Без ключа анализ выполняется локально.")

    compare_column, demo_column = st.columns(2)
    compare = compare_column.button("Сравнить", disabled=not (before and after), type="primary", width="stretch")
    demo = demo_column.button("Демо на тестовом комплекте", width="stretch")
    synthetic = st.button("Синтетический пример: подключения и кабельные работы", width="stretch")
    if compare:
        start_run(before, after, uploaded=True)
    elif demo:
        start_run(*sample_paths())
    elif synthetic:
        start_run(*[sorted((ROOT / "data" / "control" / side).glob("*.txt")) for side in ("before", "after")])

    if st.session_state.error:
        st.error(st.session_state.error)
    if st.session_state.result is not None:
        st.divider()
        if st.session_state.result.get("analysis_mode") == "local" and not st.session_state.result.get("ai_status"):
            st.info("Локальный анализ правилами и TF-IDF: реальные тексты читаются, но извлечение может быть неполным. LLM не используется.")
        st.caption("Источники относятся к обработанному комплекту. Контрольный пример синтетический и не описывает обязанности сотрудников Казахтелекома.")
        render_result(st.session_state.result)
        with st.expander("Оригиналы обработанных документов"):
            for side, docs in (st.session_state.source_documents or {}).items():
                for index, doc in enumerate(docs):
                    st.download_button(doc["name"], doc["content"], file_name=doc["name"].split("/")[-1],
                                       key=f"source:{st.session_state.run_id}:{side}:{index}")
        st.divider()
        render_impact(st.session_state.result)
    elif not st.session_state.error:
        st.info("Добавьте файлы с обеих сторон или откройте демо на тестовом комплекте.")


if __name__ == "__main__":
    main()
