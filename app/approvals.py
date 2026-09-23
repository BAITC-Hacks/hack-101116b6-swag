"""Local, version-bound document approval prototype; no authentication or signing."""

from copy import deepcopy
from datetime import datetime, timezone
import mimetypes

import streamlit as st


STATUS_LABELS = {
    "not_started": "Маршрут ещё не создан",
    "pending": "Ожидает решений",
    "returned": "Возвращено на доработку",
    "approved": "Согласовано всеми участниками",
}
DEMO_REVIEWERS = [
    "Вымышленный руководитель — Алия",
    "Вымышленный руководитель — Борис",
    "Вымышленный руководитель — Дана",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _version(workspace: dict, version_id: str) -> dict:
    if not isinstance(version_id, str) or not version_id:
        raise ValueError("Выберите существующую версию документа.")
    version = workspace.get("versions", {}).get(version_id)
    if version is None:
        raise ValueError("Версия документа не найдена.")
    reviewer = version.get("reviewed_by")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Сначала ответственный должен проверить изменения этой версии.")
    return version


def create_approval(workspace: dict, version_id: str, reviewers: list[str]) -> dict:
    """Start one immutable route for a reviewed snapshot, without changing it.

    Only the workspace's approvals section is updated. The returned record is
    detached from the stored state so a caller cannot edit a completed decision.
    """
    version = _version(workspace, version_id)
    if not isinstance(reviewers, list) or not reviewers:
        raise ValueError("Укажите хотя бы одного участника согласования.")
    if any(not isinstance(name, str) or not name.strip() for name in reviewers):
        raise ValueError("Имя каждого участника должно быть непустым.")
    names = [name.strip() for name in reviewers]
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Участники маршрута должны быть уникальными.")
    if version_id in workspace.get("approvals", {}):
        raise ValueError("Маршрут этой версии уже создан; изменить участников нельзя.")
    at = _now()
    record = {
        "version_id": version_id,
        "reviewers": names,
        "reviewed_by": version["reviewed_by"],
        "created_at": at,
        "decisions": {},
        "events": [{
            "at": at,
            "actor": version["reviewed_by"],
            "action": "created",
            "comment": "Создан маршрут согласования этой версии.",
        }],
    }
    workspace.setdefault("approvals", {})[version_id] = record
    return deepcopy(record)


def approval_status(workspace: dict, version_id: str) -> str:
    """Return the aggregate status for precisely this reviewed version."""
    _version(workspace, version_id)
    route = workspace.get("approvals", {}).get(version_id)
    if route is None:
        return "not_started"
    decisions = route["decisions"]
    if any(item["decision"] == "returned" for item in decisions.values()):
        return "returned"
    if all(name in decisions for name in route["reviewers"]):
        return "approved"
    return "pending"


def record_decision(
    workspace: dict, version_id: str, reviewer: str, decision: str, comment: str = ""
) -> dict:
    """Record a participant's one final answer, with a return closing the route."""
    _version(workspace, version_id)
    route = workspace.get("approvals", {}).get(version_id)
    if route is None:
        raise ValueError("Сначала создайте маршрут согласования.")
    if not isinstance(reviewer, str) or reviewer not in route["reviewers"]:
        raise ValueError("Этот участник не входит в маршрут согласования.")
    if decision not in ("approved", "returned"):
        raise ValueError("Допустимые решения: согласовать или вернуть на доработку.")
    if not isinstance(comment, str):
        raise ValueError("Комментарий должен быть текстом.")
    comment = comment.strip()
    if decision == "returned" and not comment:
        raise ValueError("Для возврата на доработку обязательно укажите комментарий.")
    if reviewer in route["decisions"]:
        raise ValueError("Решение этого участника уже записано и не может быть изменено.")
    if approval_status(workspace, version_id) != "pending":
        raise ValueError("Маршрут завершён. Для повторного согласования создайте новую ревизию.")
    at = _now()
    route["decisions"][reviewer] = {
        "decision": decision, "comment": comment, "at": at,
    }
    route["events"].append({
        "at": at, "actor": reviewer, "action": decision, "comment": comment,
    })
    return deepcopy(route)


def _render_version(version: dict, key_prefix: str) -> None:
    st.subheader(version.get("title") or "Пакет документов", anchor=False)
    st.text(f"Версия: {version['id']}")
    st.caption(
        f"Создана: {version.get('created_at', 'не указано')} · "
        f"Изменения проверил ответственный: {version['reviewed_by']}"
    )
    st.caption("Проверьте оригиналы и изменения перед записью решения.")
    for index, document in enumerate(version.get("documents", [])):
        name = document.get("name") or f"Документ {index + 1}"
        filename = name.replace("\\", "/").rsplit("/", 1)[-1] or "document"
        st.download_button(
            f"Скачать оригинал: {name}",
            data=document["content"],
            file_name=filename,
            mime=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            key=f"{key_prefix}:document:{index}",
            icon=":material/download:",
        )
        if document.get("text"):
            with st.expander(f"Текст: {name}"):
                st.text(document["text"])
    with st.expander("Документы и изменения этой версии"):
        changes = version.get("changes", [])
        if not changes:
            st.caption("В этой версии нет карточек изменений.")
        for change in changes:
            with st.container(border=True):
                st.subheader(change.get("unit") or "Подразделение / должность не указаны", anchor=False)
                before, after = st.columns(2)
                with before:
                    st.caption("До")
                    st.text(change.get("before") or "Не указано")
                with after:
                    st.caption("После")
                    st.text(change.get("after") or "Не указано")
                sources = change.get("evidence", [])
                if not sources:
                    st.warning("Источники изменения не указаны.")
                for source in sources:
                    with st.expander(
                        f"{source.get('doc') or 'Источник не указан'} · "
                        f"пункт {source.get('clause') or 'не указан'}"
                    ):
                        st.text(source.get("quote") or "Цитата не указана")
                        if source.get("verified") is not True:
                            st.badge("Цитата не проверена автоматически.", color="orange")
                        else:
                            st.badge("Цитата проверена", color="primary", icon=":material/check:")
                        st.caption("Проверка цитаты не подтверждает весь вывод.")


def render_approvals(workspace: dict, version_id: str) -> None:
    """Render within the main interface; the caller selects a saved version."""
    try:
        version = _version(workspace, version_id)
    except ValueError as error:
        st.warning(str(error))
        return
    prefix = f"approval:{version_id}"
    st.text("Проверьте сохранённую версию документов и соберите решения участников маршрута.")
    st.caption(
        "Локальный прототип: выбор участника имитирует вход руководителя. "
        "Нет проверки личности, внешних уведомлений и юридически значимой ЭЦП."
    )
    _render_version(version, prefix)
    status = approval_status(workspace, version_id)
    st.subheader("Маршрут согласования", anchor=False)
    st.badge(
        STATUS_LABELS[status],
        color={"not_started": "gray", "pending": "primary", "returned": "orange", "approved": "primary"}[status],
        icon=":material/check_circle:" if status == "approved" else None,
    )

    if status == "not_started":
        mode = st.radio(
            "Участники маршрута",
            ["Вымышленные руководители", "Список имён"],
            key=f"{prefix}:reviewer_mode",
            horizontal=True,
        )
        if mode == "Вымышленные руководители":
            reviewers = st.multiselect(
                "Выберите участников учебного согласования",
                DEMO_REVIEWERS,
                default=DEMO_REVIEWERS,
                key=f"{prefix}:reviewers",
                placeholder="Выберите участников",
            )
        else:
            names = st.text_area(
                "Имена участников — по одному в строке",
                key=f"{prefix}:reviewer_names",
                placeholder="Алия\nБорис",
                help="Участники должны иметь разные имена. После начала состав маршрута не меняется.",
            )
            reviewers = [name.strip() for name in names.splitlines() if name.strip()]
        st.caption("Состав маршрута фиксируется при создании. Любой возврат завершает маршрут.")
        if st.button("Начать согласование", key=f"{prefix}:start", type="primary",
                     icon=":material/play_arrow:"):
            try:
                create_approval(workspace, version_id, reviewers)
            except ValueError as error:
                st.error(str(error))
            else:
                st.rerun()
        return

    route = workspace["approvals"][version_id]
    st.caption(f"Решений получено: {len(route['decisions'])} из {len(route['reviewers'])}.")
    rows = []
    for name in route["reviewers"]:
        answer = route["decisions"].get(name, {})
        rows.append({
            "Участник": name,
            "Решение": {
                "approved": "Согласовано", "returned": "Возвращено",
            }.get(answer.get("decision"), "Ответ не получен"),
            "Время (UTC)": answer.get("at", "—"),
            "Комментарий": answer.get("comment") or "—",
        })
    st.table(rows)

    if status == "returned":
        st.text("Маршрут завершён возвратом. Ответственный создаёт новую ревизию после доработки.")
    elif status == "approved":
        st.text("Все участники согласовали указанную версию документов.")
        st.caption("Откройте раздел «Ознакомление», чтобы предоставить документы назначенным сотрудникам.")
    else:
        pending = [name for name in route["reviewers"] if name not in route["decisions"]]
        with st.container(border=True):
            st.subheader("Решение по версии", anchor=False)
            reviewer = st.selectbox(
                "Действующий участник (симуляция)", pending, key=f"{prefix}:actor",
                help="В списке остаются только участники, которые ещё не приняли решение.",
            )
            comment = st.text_area(
                "Комментарий руководителя (обязателен для возврата)",
                key=f"{prefix}:comment:{reviewer}",
                placeholder="Укажите, что нужно уточнить или доработать в этой версии.",
            )
            st.caption("Решение сохраняется для этой версии и не может быть изменено.")
            with st.container(horizontal=True):
                approved = st.button("Согласовать версию", key=f"{prefix}:approve",
                                     type="primary", icon=":material/check:")
                returned = st.button("Вернуть с комментарием", key=f"{prefix}:return",
                                     icon=":material/undo:")
        if approved or returned:
            try:
                record_decision(
                    workspace, version_id, reviewer,
                    "approved" if approved else "returned", comment,
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.rerun()

    with st.expander("Журнал согласования"):
        st.caption("Локальный журнал демонстрации; не защищённый аудит действий пользователей.")
        for event in route["events"]:
            label = {
                "created": "Маршрут создан", "approved": "Согласовано", "returned": "Возвращено",
            }[event["action"]]
            st.text(f"{event['at']} · {event['actor']} · {label}")
            if event["comment"]:
                st.text(event["comment"])
