"""Session-local document acknowledgement and onboarding; no external messages.

Version snapshots are owned by the main interface and are never mutated here.
A recorded acknowledgement is a prototype action, not an electronic signature.
"""

from copy import deepcopy
from datetime import datetime, timezone
import mimetypes
from uuid import uuid4


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _version(workspace, version_id):
    if not isinstance(version_id, str) or not version_id.strip():
        raise ValueError("Выберите существующую версию документа.")
    version = workspace.get("versions", {}).get(version_id)
    if not isinstance(version, dict):
        raise ValueError("Версия документа не найдена.")
    return version


def _approved(workspace, version_id):
    from app.approvals import approval_status

    if approval_status(workspace, version_id) != "approved":
        raise ValueError("Для ознакомления требуется согласованная версия.")


def _recipient(version, recipient_id):
    if not isinstance(recipient_id, str) or not recipient_id.strip():
        raise ValueError("Укажите назначенного сотрудника.")
    matches = [person for person in version.get("recipients", [])
               if person.get("id") == recipient_id]
    if len(matches) != 1:
        raise ValueError("Сотрудник не назначен получателем этой версии.")
    return matches[0]


def _document(version, document_index):
    if isinstance(document_index, bool) or not isinstance(document_index, int):
        raise ValueError("Неверный номер документа.")
    documents = version.get("documents", [])
    if document_index < 0 or document_index >= len(documents):
        raise ValueError("Документ не найден в выбранной версии.")
    return documents[document_index]


def _publication(workspace, version_id):
    version = _version(workspace, version_id)
    _approved(workspace, version_id)
    publication = workspace.get("acknowledgements", {}).get(version_id)
    if not publication or not publication.get("published_at"):
        raise ValueError("Ответственный ещё не открыл ознакомление с этой версией.")
    return version, publication


def _record(workspace, version_id, recipient_id, document_index):
    version, publication = _publication(workspace, version_id)
    _recipient(version, recipient_id)
    _document(version, document_index)
    record = publication["recipients"].get(recipient_id, {}).get("documents", {}).get(
        str(document_index)
    )
    if record is None:
        raise ValueError("Документ не назначен этому сотруднику.")
    return record


def publish_version(workspace, version_id):
    """Open an approved snapshot to its explicitly selected recipients, once."""
    version = _version(workspace, version_id)
    _approved(workspace, version_id)
    documents = version.get("documents", [])
    recipients = version.get("recipients", [])
    if not documents or not recipients:
        raise ValueError("Нужны оригиналы документов и назначенные получатели.")
    if any(not isinstance(document.get("content"), bytes) or not document["content"]
           for document in documents):
        raise ValueError("Для ознакомления нужны непустые оригиналы всех документов.")
    ids = [person.get("id") for person in recipients]
    if any(not isinstance(value, str) or not value.strip() for value in ids):
        raise ValueError("У каждого получателя должен быть идентификатор.")
    if len(ids) != len(set(ids)):
        raise ValueError("Получатели версии должны быть уникальны.")
    publications = workspace.setdefault("acknowledgements", {})
    if version_id not in publications:
        publications[version_id] = {
            "published_at": _now(),
            "published_by": version.get("reviewed_by", ""),
            "recipients": {
                person["id"]: {
                    "documents": {
                        str(index): {"acknowledged_at": None, "questions": []}
                        for index in range(len(documents))
                    }
                }
                for person in recipients
            },
        }
    return deepcopy(publications[version_id])


def acknowledge_document(workspace, version_id, recipient_id, document_index):
    """Record an explicit action for one recipient, document and exact version."""
    record = _record(workspace, version_id, recipient_id, document_index)
    if record["acknowledged_at"] is None:
        record["acknowledged_at"] = _now()
    return deepcopy(record)


def ask_question(workspace, version_id, recipient_id, document_index, question):
    """A question never creates or clears an acknowledgement."""
    record = _record(workspace, version_id, recipient_id, document_index)
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Введите вопрос по документу.")
    if len(question.strip()) > 4000:
        raise ValueError("Вопрос должен содержать не больше 4000 символов.")
    entry = {
        "id": uuid4().hex,
        "question": question.strip(),
        "asked_at": _now(),
        "answer": None,
        "answered_at": None,
        "answered_by": None,
    }
    record["questions"].append(entry)
    return deepcopy(entry)


def answer_question(workspace, version_id, recipient_id, document_index,
                    question_id, answer, answered_by):
    record = _record(workspace, version_id, recipient_id, document_index)
    matches = [item for item in record["questions"] if item["id"] == question_id]
    if not matches:
        raise ValueError("Вопрос не найден.")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Введите ответ сотруднику.")
    if len(answer.strip()) > 4000:
        raise ValueError("Ответ должен содержать не больше 4000 символов.")
    if not isinstance(answered_by, str) or not answered_by.strip():
        raise ValueError("Укажите имя ответственного.")
    if matches[0]["answer"] is not None:
        raise ValueError("Ответ уже сохранён; история вопроса не изменяется.")
    matches[0].update(answer=answer.strip(), answered_at=_now(),
                      answered_by=answered_by.strip())
    return deepcopy(matches[0])


def acknowledgement_summary(workspace, version_id):
    """Per-document rows retain explicit version and recipient identities."""
    version = _version(workspace, version_id)
    publication = workspace.get("acknowledgements", {}).get(version_id, {})
    rows = []
    for person in version.get("recipients", []):
        for index, document in enumerate(version.get("documents", [])):
            record = publication.get("recipients", {}).get(person["id"], {}).get(
                "documents", {}
            ).get(str(index), {})
            questions = record.get("questions", [])
            rows.append({
                "version_id": version_id,
                "recipient_id": person["id"],
                "name": person.get("name", person["id"]),
                "role": person.get("role", ""),
                "document_index": index,
                "document_name": document.get("name", f"Документ {index + 1}"),
                "published": bool(publication.get("published_at")),
                "acknowledged_at": record.get("acknowledged_at"),
                "question_count": len(questions),
                "open_questions": sum(item.get("answer") is None for item in questions),
            })
    return rows


def assign_onboarding(workspace, recipient, version_ids):
    """Assign only published snapshots already addressed to this same role/id."""
    if not isinstance(recipient, dict) or any(
        not isinstance(recipient.get(field), str) or not recipient[field].strip()
        for field in ("id", "name", "role")
    ):
        raise ValueError("Укажите сотрудника и его должность.")
    if not isinstance(version_ids, list) or not version_ids:
        raise ValueError("Выберите хотя бы одну опубликованную версию.")
    if any(not isinstance(version_id, str) for version_id in version_ids):
        raise ValueError("Неверный идентификатор версии.")
    selected = list(dict.fromkeys(version_ids))
    for version_id in selected:
        version, _ = _publication(workspace, version_id)
        canonical = _recipient(version, recipient["id"])
        if canonical.get("role") != recipient["role"]:
            raise ValueError("Должность сотрудника не совпадает с получателем версии.")
        if canonical.get("name") != recipient["name"]:
            raise ValueError("Имя сотрудника не совпадает с получателем версии.")
    packages = workspace.setdefault("onboarding", {})
    previous = packages.get(recipient["id"])
    history = deepcopy(previous.get("history", [])) if previous else []
    assigned_at = _now()
    snapshot = {
        "recipient": {field: recipient[field] for field in ("id", "name", "role")},
        "version_ids": selected,
        "assigned_at": assigned_at,
    }
    if previous and all(previous.get(key) == snapshot[key]
                        for key in ("recipient", "version_ids")):
        return deepcopy(previous)
    history.append(deepcopy(snapshot))
    packages[recipient["id"]] = {**snapshot, "history": history}
    return deepcopy(packages[recipient["id"]])


def onboarding_progress(workspace, recipient_id):
    if not isinstance(recipient_id, str) or not recipient_id.strip():
        raise ValueError("Укажите назначенного сотрудника.")
    package = workspace.get("onboarding", {}).get(recipient_id)
    if package is None:
        raise ValueError("Пакет документов этому сотруднику ещё не назначен.")
    rows = []
    for version_id in package["version_ids"]:
        version = _version(workspace, version_id)
        for row in acknowledgement_summary(workspace, version_id):
            if row["recipient_id"] == recipient_id:
                rows.append({**row, "version_title": version.get("title", version_id)})
    completed = sum(bool(row["acknowledged_at"]) for row in rows)
    total = len(rows)
    return {
        "recipient_id": recipient_id,
        "role": package["recipient"]["role"],
        "total": total,
        "acknowledged": completed,
        "pending": total - completed,
        "percent": round(100 * completed / total) if total else 0,
        "documents": rows,
    }


def _render_changes(version, recipient_id):
    import streamlit as st

    changes = [item for item in version.get("changes", [])
               if recipient_id in item.get("recipient_ids", [])]
    st.subheader("Изменения для вашей роли", anchor=False)
    st.caption("Ответственный назначил эти изменения выбранному сотруднику.")
    if not changes:
        st.caption("Персональные изменения не назначены. Ознакомьтесь с оригиналами.")
    for change in changes:
        with st.expander(str(change.get("unit") or "Изменение")):
            before, after = st.columns(2)
            with before:
                st.caption("Было")
                st.text(change.get("before") or "Не указано")
            with after:
                st.caption("Стало")
                st.text(change.get("after") or "Не указано")
            for evidence in change.get("evidence", []):
                with st.expander(
                    f"{evidence.get('doc') or 'Источник не указан'} · "
                    f"пункт {evidence.get('clause') or 'не указан'}"
                ):
                    st.text(evidence.get("quote") or "Цитата не указана")
    st.caption("Пояснения не заменяют оригинал документа.")


def _render_document(workspace, version_id, recipient_id, index, namespace):
    import streamlit as st

    version = _version(workspace, version_id)
    document = _document(version, index)
    record = _record(workspace, version_id, recipient_id, index)
    key = f"{namespace}:{version_id}:{recipient_id}:{index}"
    with st.container(border=True):
        st.subheader(f"{index + 1}. {document.get('name', 'Документ')}", anchor=False)
        st.caption(f"Версия: {version_id}")
        content = document.get("content")
        if record["acknowledged_at"]:
            st.badge("Ознакомлен", icon=":material/check:", color="primary")
            st.caption(f"Отметка сохранена: {record['acknowledged_at']}")
        else:
            st.badge("Ожидает ознакомления", color="gray")
        if isinstance(content, bytes):
            filename = str(document.get("name") or f"document-{index + 1}")
            filename = filename.replace("\\", "/").rsplit("/", 1)[-1] or "document"
            st.download_button("Скачать оригинал", data=content,
                               file_name=filename,
                               mime=mimetypes.guess_type(filename)[0] or "application/octet-stream",
                               key=f"{key}:download", icon=":material/download:")
        else:
            st.warning("Оригинал недоступен. Подтверждение ознакомления отключено.")
        if document.get("text"):
            with st.expander(f"Текст документа: {document.get('name', 'Документ')}"):
                st.text(document["text"])
        if st.button("Ознакомлен с этой версией документа", key=f"{key}:ack",
                     disabled=bool(record["acknowledged_at"]) or not isinstance(content, bytes),
                     type="primary", icon=":material/check:",
                     help="Сохранит отметку только для выбранного сотрудника и этой версии документа."):
            acknowledge_document(workspace, version_id, recipient_id, index)
            st.rerun()
        st.caption("Вопрос ответственному можно задать отдельно. Он не заменяет отметку об ознакомлении.")
        with st.form(f"{key}:question-form", clear_on_submit=True, border=False):
            question = st.text_area(
                "Вопрос по документу", key=f"{key}:question", max_chars=4000,
                placeholder="Укажите пункт документа и что требуется пояснить.", height=100,
            )
            if st.form_submit_button("Задать вопрос", icon=":material/chat:"):
                try:
                    ask_question(workspace, version_id, recipient_id, index, question)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        for entry in record["questions"]:
            st.caption(f"Вопрос · {entry['asked_at']}")
            st.text(entry["question"])
            if entry["answer"] is not None:
                st.caption(f"Ответ · {entry['answered_by']} · {entry['answered_at']}")
                st.text(entry["answer"])
            else:
                st.badge("Ожидает ответа", color="gray")


def _render_supervisor(workspace, version_id):
    import streamlit as st

    rows = acknowledgement_summary(workspace, version_id)
    st.subheader("Статус ознакомления", anchor=False)
    if rows:
        acknowledged = sum(bool(row["acknowledged_at"]) for row in rows)
        st.progress(acknowledged / len(rows),
                    text=f"Отметок об ознакомлении: {acknowledged} из {len(rows)}")
        st.caption("Каждая строка — один сотрудник и один документ этой версии.")
        st.dataframe([{
            "Сотрудник": row["name"], "Должность": row["role"],
            "Документ": row["document_name"], "Версия": row["version_id"],
            "Статус": "Ознакомлен" if row["acknowledged_at"] else "Ожидает ознакомления",
            "Время": row["acknowledged_at"] or "—",
            "Вопросов без ответа": row["open_questions"],
        } for row in rows], hide_index=True, width="stretch")
    publication = workspace["acknowledgements"][version_id]
    if any(row["question_count"] for row in rows):
        st.subheader("Вопросы сотрудников", anchor=False)
        st.caption("Ответ сохраняется в истории вопроса и доступен сотруднику.")
    else:
        st.caption("Вопросов по этой версии пока нет.")
    for row in rows:
        record = publication["recipients"][row["recipient_id"]]["documents"][str(row["document_index"])]
        for question in record["questions"]:
            with st.expander(f"Вопрос: {row['name']} · {row['document_name']}"):
                st.text(question["question"])
                st.caption(f"Версия: {version_id} · задан {question['asked_at']}")
                if question["answer"] is not None:
                    st.badge("Ответ сохранён", color="primary")
                    st.text(f"{question['answered_by']}: {question['answer']}")
                    continue
                st.badge("Ожидает ответа", color="gray")
                with st.form(f"ack:answer:{version_id}:{question['id']}", border=False):
                    author = st.text_input(
                        "Ответственный", value=_version(workspace, version_id).get("reviewed_by", ""),
                        placeholder="Имя ответственного",
                    )
                    answer = st.text_area("Ответ", max_chars=4000,
                                          placeholder="Поясните требование и сошлитесь на пункт документа.")
                    if st.form_submit_button("Сохранить ответ", type="primary", icon=":material/save:"):
                        try:
                            answer_question(workspace, version_id, row["recipient_id"],
                                            row["document_index"], question["id"], answer, author)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))


def render_acknowledgements(workspace, version_id):
    import streamlit as st

    version = _version(workspace, version_id)
    st.text("Откройте сотрудникам согласованную версию, отслеживайте ознакомление и отвечайте на вопросы.")
    st.caption("Симуляция ролей: выбор сотрудника не подтверждает его личность. «Ознакомлен» не является ЭЦП.")
    try:
        _approved(workspace, version_id)
    except ValueError:
        st.info("Сначала завершите согласование этой версии руководителями.")
        return
    publication = workspace.get("acknowledgements", {}).get(version_id)
    if not publication:
        with st.container(border=True):
            st.subheader("Доступ к согласованной версии", anchor=False)
            st.badge("Готова к ознакомлению", color="primary", icon=":material/check_circle:")
            st.text(f"Получателей: {len(version.get('recipients', []))}. Версия: {version_id}.")
            st.caption("Каждый получатель увидит оригиналы и изменения, назначенные для его роли.")
            if st.button("Открыть ознакомление назначенным сотрудникам", key=f"ack:publish:{version_id}",
                         type="primary", icon=":material/visibility:"):
                try:
                    publish_version(workspace, version_id)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        return
    st.badge("Ознакомление открыто", color="primary")
    st.caption(f"Ознакомление открыто: {publication['published_at']}. Версия: {version_id}")
    mode = st.radio("Просмотр ознакомления", ["Ответственный", "Сотрудник (симуляция)"],
                    horizontal=True, key=f"ack:mode:{version_id}")
    if mode == "Ответственный":
        _render_supervisor(workspace, version_id)
        return
    people = {person["id"]: person for person in version["recipients"]}
    recipient_id = st.selectbox("Сотрудник", list(people),
                                format_func=lambda value: f"{people[value]['name']} · {people[value]['role']}",
                                key=f"ack:person:{version_id}",
                                help="Показываются только документы и изменения, назначенные этому сотруднику.")
    _render_changes(version, recipient_id)
    st.subheader("Документы для ознакомления", anchor=False)
    for index in range(len(version["documents"])):
        _render_document(workspace, version_id, recipient_id, index, "ack:reader")


def render_onboarding(workspace):
    import streamlit as st

    st.text("Соберите документы для конкретного сотрудника и следите за прохождением его пакета.")
    st.caption("В пакет входят опубликованные версии, назначенные сотруднику и его должности. Действия выполняются в режиме симуляции.")
    eligible = {}
    people = {}
    for version_id, version in workspace.get("versions", {}).items():
        try:
            _publication(workspace, version_id)
        except ValueError:
            continue
        eligible[version_id] = version
        for person in version.get("recipients", []):
            identity = (person.get("id"), person.get("role"), person.get("name"))
            if all(isinstance(value, str) and value.strip() for value in identity):
                people[identity] = person
    mode = st.radio("Просмотр пакета новичка", ["Назначить пакет", "Новичок (симуляция)"],
                    horizontal=True, key="onboarding:mode")
    if mode == "Назначить пакет":
        if not people:
            st.info("Сначала согласуйте версию и откройте ознакомление назначенным получателям.")
            return
        st.subheader("Назначение пакета", anchor=False)
        person_key = st.selectbox("Получатель пакета", list(people),
                                 format_func=lambda key: f"{people[key]['name']} · {people[key]['role']}",
                                 key="onboarding:assign-person")
        person = people[person_key]
        choices = [version_id for version_id, version in eligible.items()
                   if any(item.get("id") == person["id"] and item.get("role") == person["role"]
                          and item.get("name") == person["name"] for item in version["recipients"])]
        selected = st.multiselect("Версии документов для пакета", choices,
                                  format_func=lambda value: f"{eligible[value]['title']} · {value}",
                                  key=f"onboarding:versions:{person['id']}:{person['role']}",
                                  placeholder="Выберите опубликованные версии",
                                  help="Доступны только версии, в которых сотрудник указан получателем с этой должностью.")
        st.caption("Отметки об ознакомлении привязаны к точной версии каждого документа.")
        if st.button("Назначить пакет документов", disabled=not selected,
                     key="onboarding:assign", type="primary", icon=":material/assignment:"):
            try:
                assign_onboarding(workspace, person, selected)
                st.success("Пакет назначен. Для просмотра выберите «Новичок (симуляция)».")
            except ValueError as exc:
                st.error(str(exc))
        packages = workspace.get("onboarding", {})
        if packages:
            st.subheader("Назначенные пакеты", anchor=False)
            st.dataframe([{
                "Сотрудник": package["recipient"]["name"],
                "Должность": package["recipient"]["role"],
                "Ознакомлен / документов": f"{onboarding_progress(workspace, person_id)['acknowledged']} / {onboarding_progress(workspace, person_id)['total']}",
                "Назначен": package["assigned_at"],
            } for person_id, package in packages.items()], hide_index=True, width="stretch")
        return
    packages = workspace.get("onboarding", {})
    if not packages:
        st.info("Ответственный ещё не назначил пакет документов.")
        return
    person_id = st.selectbox("Новичок", list(packages),
                             format_func=lambda value: f"{packages[value]['recipient']['name']} · {packages[value]['recipient']['role']}",
                             key="onboarding:reader-person")
    package = packages[person_id]
    progress = onboarding_progress(workspace, person_id)
    st.subheader("Ваш прогресс", anchor=False)
    st.caption("Прочитайте оригиналы и отметьте ознакомление по каждому документу.")
    st.progress(progress["percent"] / 100,
                text=f"Ознакомлен: {progress['acknowledged']} из {progress['total']} документов")
    for version_id in package["version_ids"]:
        version = _version(workspace, version_id)
        st.subheader(version["title"], anchor=False)
        try:
            _publication(workspace, version_id)
        except ValueError as exc:
            st.warning(str(exc))
            continue
        _render_changes(version, person_id)
        for index in range(len(version["documents"])):
            _render_document(workspace, version_id, person_id, index, "onboarding:reader")
    with st.expander("История назначения пакета"):
        for entry in package["history"]:
            st.text(f"{entry['assigned_at']} · {entry['recipient']['role']} · версии: {', '.join(entry['version_ids'])}")
