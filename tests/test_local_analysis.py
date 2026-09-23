"""Adversarial extraction and document-driven offline comparison checks."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.local_analysis import extract_functions, run, verified_sources
from src.parse import parse_document, split_clauses


def analyze(tmp_path, before, after):
    paths = []
    for side, text in (("before", before), ("after", after)):
        directory = tmp_path / side
        directory.mkdir(exist_ok=True)
        path = directory / "synthetic.txt"
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return run([paths[0]], [paths[1]]), paths


def assert_sources(result, paths):
    fragments = [fragment for path in paths for fragment in parse_document(path)]
    index = {(f["doc"], f["clause"]): f["text"] for f in fragments}
    for name in ("units", "function_map", "findings", "ambiguous_matches"):
        for item in result[name]:
            assert item["evidence"]
            for source in item["evidence"]:
                assert source["verified"] is True
                assert source["quote"] in index[source["doc"], source["clause"]]


def test_identical_sets_keep_each_owner_without_false_moves_new_or_lost(tmp_path):
    document = (
        "1.1. Отдел альфа:\n"
        "1.1.1. Проверяет качество завершённых кабельных работ.\n"
        "1.2. Отдел бета:\n"
        "1.2.1. Проверяет качество завершённых кабельных работ."
    )
    result, paths = analyze(tmp_path, document, document)
    assert len(result["function_map"]) == 2
    assert {row["status"] for row in result["function_map"]} == {"kept"}
    assert all(row["before_unit"] == row["after_unit"] for row in result["function_map"])
    assert result["ambiguous_matches"] == []
    assert not any(item["type"] == "loss" for item in result["findings"])
    assert_sources(result, paths)


@pytest.mark.parametrize("text", [
    "Отдел контроля не выполняет проверку качества работ.",
    "Отдел контроля может выполнять проверку качества работ.",
    "Отдел контроля выполняет проверку качества работ, если поступила заявка.",
    "Если поступила заявка, Отдел контроля выполняет проверку качества работ.",
    "Отдел контроля вправе выполнять проверку качества работ.",
])
def test_negation_modality_and_conditions_are_not_positive_assignments(text):
    assert extract_functions(split_clauses("1.1. " + text, "probe.txt")) == []


def test_unsupported_inner_header_does_not_inherit_outer_owner():
    text = (
        "1. Отдел альфа:\n"
        "1.1. Отдел бета может выполнять:\n"
        "1.1.1. Проверку качества завершённых кабельных работ."
    )
    assert extract_functions(split_clauses(text, "probe.txt")) == []


def test_block_and_department_function_headings_preserve_levels():
    text = (
        "1.1. Функции блока внутреннего аудита:\n"
        "1.1.1. Проверяет качество завершённых кабельных работ.\n"
        "1.2. Функции отдела контроля:\n"
        "1.2.1. Проверяет качество завершённых кабельных работ."
    )
    functions = extract_functions(split_clauses(text, "probe.txt"))
    assert [(f["unit"], f["level"]) for f in functions] == [
        ("блок внутреннего аудита", "block"), ("отдел контроля", "unit"),
    ]


def test_block_function_does_not_match_department_function(tmp_path):
    before = "1.1. Функции блока проверки:\n1.1.1. Проверяет качество завершённых кабельных работ."
    after = "1.1. Функции отдела проверки:\n1.1.1. Проверяет качество завершённых кабельных работ."
    result, paths = analyze(tmp_path, before, after)
    assert {row["status"] for row in result["function_map"]} == {"lost", "new"}
    assert not any(f["type"] == "duplicate" for f in result["findings"])
    assert_sources(result, paths)


def test_ne_vprave_header_retains_owner_and_generates_supported_conflict(tmp_path):
    document = (
        "1.1. Отдел контроля:\n"
        "1.1.1. Согласовывать собственные отчёты о результатах внутренних проверок.\n"
        "2.1. Отдел контроля не вправе:\n"
        "2.1.1. Согласовывать собственные отчёты о результатах внутренних проверок."
    )
    functions = extract_functions(split_clauses(document, "probe.txt"))
    assert len(functions) == 2
    assert {f["unit"] for f in functions} == {"Отдел контроля"}
    assert {f["kind"] for f in functions} == {"function", "prohibition"}
    result, paths = analyze(tmp_path, document, document)
    conflicts = [f for f in result["findings"] if f["type"] == "conflict"]
    assert len(conflicts) == 1
    assert {e["clause"] for e in conflicts[0]["evidence"]} >= {"1.1.1", "2.1", "2.1.1"}
    assert_sources(result, paths)


def test_inline_prohibition_does_not_create_owner_with_negation():
    text = "1.1. Отдел контроля не вправе согласовывать собственные отчёты о проверке."
    functions = extract_functions(split_clauses(text, "probe.txt"))
    assert len(functions) == 1
    assert functions[0]["unit"] == "Отдел контроля"
    assert functions[0]["kind"] == "prohibition"


def test_ambiguous_transfer_does_not_invent_move_loss_or_new(tmp_path):
    before = "1.1. Отдел альфа:\n1.1.1. Хранит архив актов завершённых подключений."
    after = (
        "1.1. Отдел бета:\n1.1.1. Хранит архив актов завершённых подключений.\n"
        "1.2. Отдел гамма:\n1.2.1. Хранит архив актов завершённых подключений."
    )
    result, paths = analyze(tmp_path, before, after)
    assert result["function_map"] == []
    assert result["ambiguous_matches"]
    assert not any(f["type"] == "loss" for f in result["findings"])
    assert "Неоднозначных записей" in result["conclusion"]
    assert_sources(result, paths)


def test_one_remaining_function_is_not_reused_for_two_previous_owners(tmp_path):
    before = (
        "1.1. Отдел альфа:\n1.1.1. Хранит архив актов завершённых подключений.\n"
        "1.2. Отдел бета:\n1.2.1. Хранит архив актов завершённых подключений."
    )
    after = "1.1. Отдел бета:\n1.1.1. Хранит архив актов завершённых подключений."
    result, _ = analyze(tmp_path, before, after)
    assert len(result["function_map"]) == 1
    assert result["function_map"][0]["before_unit"] == "Отдел бета"
    assert result["function_map"][0]["status"] == "kept"
    assert result["ambiguous_matches"][0]["unit"] == "Отдел альфа"


def test_unambiguous_transfer_is_moved(tmp_path):
    before = "1.1. Отдел альфа:\n1.1.1. Хранит архив актов завершённых подключений."
    after = "1.1. Отдел бета:\n1.1.1. Хранит архив актов завершённых подключений."
    result, _ = analyze(tmp_path, before, after)
    assert [row["status"] for row in result["function_map"]] == ["moved"]
    assert result["ambiguous_matches"] == []


def test_synthetic_control_finds_all_kinds_with_real_sources_without_network(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Offline comparison must not access the network")

    monkeypatch.setattr("socket.socket.connect", no_network)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    paths = [ROOT / "data" / "control" / side / "regulation.txt" for side in ("before", "after")]
    result = run([paths[0]], [paths[1]])
    assert {f["type"] for f in result["findings"]} >= {"loss", "duplicate", "conflict", "reorganization"}
    assert result["analysis_mode"] == "local"
    assert "кандидатов" in result["conclusion"]
    assert "Проверка цитат не подтверждает интерпретацию" in result["conclusion"]
    assert_sources(result, paths)


def test_evidence_must_match_document_and_clause():
    fragments = [{"doc": "after.txt", "clause": "1", "text": "Дословная цитата", "section": ""}]
    records = [{"evidence": [{"doc": "before.txt", "clause": "1", "quote": "Дословная цитата"}]}]
    assert verified_sources(records, fragments) == []
    assert records[0]["evidence"][0]["verified"] is False
