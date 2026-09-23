"""Visible onboarding entry: mock checklist plus the existing real version workflow."""

import streamlit as st

from app.acknowledgements import render_onboarding


MOCK_DOCUMENTS = (
    ("job", "Должностная инструкция", "Обязанности и зона ответственности"),
    ("department", "Положение о подразделении", "Роль подразделения и порядок взаимодействия"),
    ("rules", "Правила внутреннего трудового распорядка", "Рабочий порядок и основные правила"),
    ("security", "Информационная безопасность", "Работа с данными и доступами"),
    ("safety", "Охрана труда", "Памятка по безопасной работе"),
)
DRAFT_FIELDS = ("first_name", "last_name", "role")


def update_draft():
    """Persist form values separately from widgets that disappear on navigation."""
    st.session_state.newcomer_draft = {
        field: st.session_state.get(f"newcomer:{field}", "") for field in DRAFT_FIELDS
    }
    st.session_state.newcomer_draft["documents"] = [
        key for key, _, _ in MOCK_DOCUMENTS if st.session_state.get(f"newcomer:doc:{key}")
    ]
    st.session_state.pop("newcomer_mock_package", None)


def render_onboarding_page(workspace):
    draft = st.session_state.get("newcomer_draft", {})
    for field in DRAFT_FIELDS:
        st.session_state.setdefault(f"newcomer:{field}", draft.get(field, ""))
    for key, _, _ in MOCK_DOCUMENTS:
        st.session_state.setdefault(f"newcomer:doc:{key}", key in draft.get("documents", ["job", "department"]))

    st.badge("Демонстрационный пакет", icon=":material/science:", color="gray")
    st.caption("Ниже — моковые документы для примерки сценария. Галочка добавляет документ в пакет, а не подтверждает ознакомление.")
    person, documents = st.columns([1, 1.25], gap="medium")
    with person:
        with st.container(border=True, key="newcomer_person"):
            st.subheader("Новый сотрудник", anchor=False)
            st.caption("Укажите, для кого собираете пакет.")
            st.text_input("Имя", key="newcomer:first_name", placeholder="Например, Алексей", on_change=update_draft, max_chars=80)
            st.text_input("Фамилия", key="newcomer:last_name", placeholder="Например, Иванов", on_change=update_draft, max_chars=80)
            st.text_input("Должность", key="newcomer:role", placeholder="Например, специалист отдела", on_change=update_draft, max_chars=160)
    with documents:
        with st.container(border=True, key="newcomer_documents"):
            st.subheader("Пакет документов", anchor=False)
            st.caption("Отметьте то, что нужно новому сотруднику.")
            for key, title, description in MOCK_DOCUMENTS:
                st.checkbox(title, key=f"newcomer:doc:{key}", help=description, on_change=update_draft)
            selected = [title for key, title, _ in MOCK_DOCUMENTS if st.session_state[f"newcomer:doc:{key}"]]
            st.caption(f"Выбрано документов: {len(selected)} из {len(MOCK_DOCUMENTS)}")
    values = {field: st.session_state[f"newcomer:{field}"].strip() for field in DRAFT_FIELDS}
    ready = all(values.values()) and bool(selected)
    if not ready:
        st.caption("Заполните имя, фамилию и должность. Выберите хотя бы один документ.")
    if st.button("Сформировать демо-пакет", type="primary", icon=":material/folder_open:",
                 key="newcomer:build", disabled=not ready):
        st.session_state.newcomer_mock_package = {**values, "documents": selected}

    package = st.session_state.get("newcomer_mock_package")
    if package:
        with st.container(border=True, key="newcomer_preview"):
            st.success("Демо-пакет подготовлен")
            st.text(f"{package['first_name']} {package['last_name']} · {package['role']}")
            for title in package["documents"]:
                st.text(f"• {title}")
            st.caption("Это пример списка: файлы не приложены, сотруднику ничего не отправлено. Пакет сохранён в текущей сессии.")

    with st.expander("Назначить реальные согласованные документы", icon=":material/verified:"):
        st.caption("Для рабочего назначения используются опубликованные версии и их получатели.")
        render_onboarding(workspace)
