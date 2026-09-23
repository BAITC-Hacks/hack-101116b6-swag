from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.source_explorer import extract_sources


def test_extraction_preserves_editions_duplicates_and_raw_evidence():
    documents = {
        'before': [{'name': 'До/1_rules.txt', 'text': '8.1. Отдел лунной логистики (ОЛЛ).\n8.1. Отдел снежных карт (ОСК).'}],
        'after': [{'name': 'После/1_rules.txt', 'text': '8.1. Департамент звёздных маршрутов (ДЗМ).'}],
    }
    original = deepcopy(documents)
    result = extract_sources(documents)
    assert documents == original
    assert [f['clause'] for f in result['before']['fragments']] == ['8.1', '8.1']
    assert len(result['before']['units']) == 2
    assert len(result['after']['units']) == 1
    for side in ('before', 'after'):
        for unit in result[side]['units']:
            assert 'status' not in unit
            for evidence in unit['evidence']:
                assert evidence['verified'] is False
                assert evidence['doc'] == documents[side][0]['name']
                assert evidence['quote'] in documents[side][0]['text']
    assert extract_sources(None)['before']['fragments'] == []


def _screen():
    from app.source_explorer import render_sources
    render_sources({
        'before': [{'name': 'До/rules.txt', 'text': '3.4. Отдел лунной логистики (ОЛЛ).\n3.4. Повторный номер.'}],
        'after': [{'name': 'После/rules.txt', 'text': '5.8. Отдел снежных карт (ОСК).'}],
    }, 'test')


def test_browser_filters_and_repeated_clause_selection():
    app = AppTest.from_function(_screen).run()
    assert not app.exception
    fragment = next(w for w in app.selectbox if w.key.endswith('before:fragment:None:'))
    fragment.select(1).run()
    assert not app.exception
    assert any(t.value == '3.4. Повторный номер.' for t in app.text)
    query = next(w for w in app.text_input if w.key == 'sources:test:before:query')
    query.set_value('нет такого текста').run()
    assert not app.exception
    assert any('Нет пунктов' in item.value for item in app.info)
    next(w for w in app.text_input if w.key == 'sources:test:before:query').set_value('3.4').run()
    assert not app.exception
    next(w for w in app.selectbox if w.key == 'sources:test:before:level').select('role').run()
    assert not app.exception
    assert any('Записи этого типа не извлечены' in item.value for item in app.info)


def test_real_demo_exposes_sources_without_api(monkeypatch):
    monkeypatch.setenv('DEMO_MODE', 'true')
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    from src import config

    def no_api(*args, **kwargs):
        raise AssertionError('Source browser must work offline')

    monkeypatch.setattr(config, 'get_llm', no_api)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app/main.py', default_timeout=30).run()
    next(b for b in app.button if b.label == "Сравнить документы").click().run()
    next(b for b in app.button if b.label == 'Демо на тестовом комплекте').click().run()
    assert not app.exception
    assert any(tab.label == 'Структура и пункты' for tab in app.tabs)
    assert len([m for m in app.metric if m.label == 'Фрагменты' and int(m.value) > 0]) == 2
    run_id = app.session_state['run_id']
    next(w for w in app.text_input if w.key == f'sources:{run_id}:before:query').set_value('3.4').run()
    assert not app.exception
    assert any('БВА состоит из следующих структурных подразделений' in t.value for t in app.text)
