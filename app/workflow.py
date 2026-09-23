"""Immutable session snapshots connecting analysis to human document workflows."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from src.parse import split_clauses


DEMO_PEOPLE = [
    {"id": "demo-installer", "name": "Алия · вымышленный сотрудник", "role": "Отдел клиентских подключений"},
    {"id": "demo-cable", "name": "Данияр · вымышленный сотрудник", "role": "Отдел линейной инфраструктуры"},
    {"id": "demo-controller", "name": "Сауле · вымышленный сотрудник", "role": "Отдел контроля качества"},
]


def new_workspace():
    return {"versions": {}, "approvals": {}, "acknowledgements": {}, "onboarding": {}}


def make_version(workspace, *, title, revision, reviewed_by, documents, changes, recipients, reference_documents=None, comparison_id=None):
    if not title.strip() or not revision.strip() or not reviewed_by.strip():
        raise ValueError("Укажите название, редакцию и ответственного.")
    if not documents or not recipients or not changes:
        raise ValueError("Нужны оригиналы, проверенные изменения и выбранные получатели.")
    ids = [r.get("id", "") for r in recipients]
    if len(ids) != len(set(ids)) or any(not i for i in ids):
        raise ValueError("Получатели должны иметь уникальные идентификаторы.")
    if any(not r.get("name", "").strip() or not r.get("role", "").strip() for r in recipients):
        raise ValueError("Укажите имя и должность/подразделение каждого получателя.")
    all_docs = documents + (reference_documents or [])
    if any(not isinstance(d.get("content"), bytes) or not d["content"] for d in all_docs):
        raise ValueError("Оригиналы документов должны быть доступны.")
    sources = {}
    for doc in all_docs:
        for fragment in split_clauses(doc.get("text", ""), doc["name"]):
            sources.setdefault((fragment["doc"], fragment["clause"]), []).append(" ".join(fragment["text"].casefold().split()))
    for change in changes:
        if not change.get("evidence") or not all(e.get("verified") is True for e in change["evidence"]):
            raise ValueError("Для передачи изменений нужны проверенные цитаты.")
        for source in change["evidence"]:
            quote = " ".join(source.get("quote", "").casefold().split())
            if not quote or not any(quote in text for text in sources.get((source.get("doc"), source.get("clause")), [])):
                raise ValueError("Цитата не найдена в оригинале и пункте выбранного комплекта.")
        targets = change.get("recipient_ids", [])
        if not targets or not set(targets) <= set(ids):
            raise ValueError("Ответственный должен назначить получателей каждому изменению.")
    payload = deepcopy({"title": title.strip(), "revision": revision.strip(), "reviewed_by": reviewed_by.strip(),
                        "documents": documents, "reference_documents": reference_documents or [],
                        "changes": changes, "recipients": recipients})
    if comparison_id is not None:
        payload["comparison_id"] = comparison_id
    signature = deepcopy(payload)
    for doc in signature["documents"] + signature["reference_documents"]:
        doc["content"] = hashlib.sha256(doc["content"]).hexdigest()
    version_id = hashlib.sha256(json.dumps(signature, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if version_id not in workspace["versions"]:
        payload.update(id=version_id, created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        workspace["versions"][version_id] = payload
    return version_id


def impact_cards(result):
    cards = []
    for index, row in enumerate(result.get("units", [])):
        status = row.get("status")
        if status not in ("created", "removed", "reorganized"):
            continue
        if not row.get("evidence") or not all(e.get("verified") is True for e in row["evidence"]):
            continue
        cards.append({"id": f"unit-{index}", "unit": row.get("name") or "Название не установлено",
                      "before": "Не обнаружено в извлечённой структуре до" if status == "created" else "Упоминается в исходной структуре",
                      "after": "Не обнаружено в извлечённой структуре после; требуется проверка" if status == "removed" else "Признаки изменения структуры; см. источники" if status == "reorganized" else "Упоминается в новой структуре",
                      "status": status, "evidence": deepcopy(row["evidence"])})
    for index, row in enumerate(result.get("function_map", [])):
        if row.get("status") in ("kept", "сохранено"):
            continue
        if not row.get("evidence") or not all(e.get("verified") is True for e in row["evidence"]):
            continue
        cards.append({"id": f"function-{index}", "unit": row.get("after_unit") or row.get("before_unit") or "Исполнитель не установлен",
                      "before": row.get("before_function") or "Не найдено в извлечённых функциях до",
                      "after": row.get("after_function") or "Не найдено в извлечённых функциях после; требуется проверка",
                      "status": row.get("status", ""), "evidence": deepcopy(row["evidence"])})
    return cards
