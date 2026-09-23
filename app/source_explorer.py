"""Read-only source browser for independently extracted document editions."""

import streamlit as st

from src.parse import split_clauses
from src.structure import extract_units

LEVELS = {"block": "Блок", "unit": "Подразделение", "role": "Должность", "unknown": "Тип не определён"}
RELATIONS = {"administrative": "Административное", "functional": "Функциональное", "unspecified": "Вид не указан"}


def extract_sources(documents):
    """Use already-read text with display paths; preserve duplicate clauses/roles."""
    result = {}
    for side in ("before", "after"):
        docs = (documents or {}).get(side, [])
        fragments = [fragment for doc in docs
                     for fragment in split_clauses(doc["text"], doc["name"])]
        result[side] = {"documents": len(docs), "fragments": fragments,
                        "units": extract_units(fragments)}
    return result


def _sources(items):
    for item in items:
        st.text(f"{item['doc']} · пункт {item['clause'] or 'без номера'}")
        st.text(item['quote'])
        st.caption("Цитата из этапа извлечения · проверка не выполнена")


def _edition(data, side, run_id):
    prefix = f"sources:{run_id}:{side}"
    st.subheader("До изменений" if side == "before" else "После изменений", anchor=False)
    counts = st.columns(3)
    counts[0].metric("Документы", data['documents'])
    counts[1].metric("Фрагменты", len(data['fragments']))
    counts[2].metric("Записи структуры", len(data['units']))
    st.caption("Записи включают подразделения и должности; одинаковые названия могут относиться к разным руководителям.")
    level = st.selectbox("Тип записи", ["all", *LEVELS],
                         format_func=lambda value: "Все типы" if value == "all" else LEVELS[value],
                         key=f"{prefix}:level")
    units = [unit for unit in data['units'] if level == "all" or unit['level'] == level]
    if units:
        def label(index):
            unit = units[index]
            parents = ', '.join(parent['name'] for parent in unit['parents'])
            return f"{index + 1}. {unit['name']}" + (f" → {parents}" if parents else "")

        index = st.selectbox("Подразделение или должность", range(len(units)), format_func=label,
                             key=f"{prefix}:unit:{level}")
        unit = units[index]
        with st.container(border=True):
            st.text(unit['name'])
            st.caption(f"{LEVELS[unit['level']]} · сокращение: {unit['abbr'] or 'не указано'}")
            with st.expander("Пункты и цитаты названия"):
                _sources(unit['evidence'])
            if not unit['parents']:
                st.caption("Явное подчинение не извлечено.")
            for parent in unit['parents']:
                with st.expander(f"Подчинение: {parent['name']}"):
                    st.text(f"Вид: {RELATIONS[parent['relation']]}")
                    _sources(parent['evidence'])
    else:
        st.info("Записи этого типа не извлечены. Проверьте исходные пункты ниже.")

    st.markdown("#### Исходные пункты")
    fragments = data['fragments']
    docs = list(dict.fromkeys(f['doc'] for f in fragments))
    selected_doc = st.selectbox("Документ", [None, *docs],
                                format_func=lambda value: value or "Все документы",
                                key=f"{prefix}:doc")
    query = st.text_input("Номер пункта или текст", key=f"{prefix}:query").strip().casefold()
    visible = [f for f in fragments
               if (selected_doc is None or f['doc'] == selected_doc)
               and (not query or query in f['clause'].casefold() or query in f['text'].casefold())]
    st.caption(f"Найдено фрагментов: {len(visible)}")
    if not visible:
        st.info("Нет пунктов по выбранным условиям.")
        return
    # Индекс сохраняет отдельные фрагменты с одинаковыми номерами.
    index = st.selectbox("Фрагмент", range(len(visible)),
                         format_func=lambda i: f"{i + 1}. {visible[i]['clause'] or 'Без номера'} · {visible[i]['doc']}",
                         key=f"{prefix}:fragment:{selected_doc}:{query}")
    fragment = visible[index]
    st.text(f"Раздел: {fragment['section'] or 'не определён'}")
    st.text(fragment['text'])


def render_sources(documents, run_id):
    st.subheader("Структура и исходные пункты", anchor=False)
    st.caption("Каждая редакция извлечена отдельно. Здесь нет выводов о создании, упразднении или передаче функций.")
    if not documents:
        st.info("Исходные документы ещё не обработаны.")
        return
    data = extract_sources(documents)
    columns = st.columns(2, gap="large")
    for column, side in zip(columns, ("before", "after")):
        with column:
            _edition(data[side], side, run_id)
