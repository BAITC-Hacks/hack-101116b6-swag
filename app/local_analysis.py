"""Conservative, document-driven baseline until src.pipeline is available.

No fixture answers, external services or pipeline-owned file modifications.
Rules are intentionally narrow: matching citations does not prove an inference.
"""

from collections import Counter
from copy import deepcopy
from itertools import combinations
import math
from pathlib import Path
import re
import warnings

from src.parse import parse_document
from src.structure import extract_units


PREFIX = re.compile(r"^\s*\d+(?:\.\d+)*\.\s*")
ENTITY = r"(?:отдел|департамент|служба|центр|блок|управление|директор|руководитель|начальник|главный аудитор|работники)"
ACTION = r"(?:выполня\w*|осуществля\w*|обеспечива\w*|организу\w*|контролиру\w*|проверя\w*|вед[её]т|хран\w*|разрабатыва\w*|утвержда\w*|согласовыва\w*|провод\w*|обслужива\w*|ремонтиру\w*)"
DIRECT = re.compile(rf"^(?P<unit>{ENTITY}\b.+?)\s+(?P<action>{ACTION}\b.+)", re.I)
RENAME = re.compile(
    rf"(?P<old>{ENTITY}\s+[^().:\n]+?)(?:\s*\([^)]*\))?\s+переименован[ао]?\s+в\s+(?P<new>{ENTITY}\s+[^().:\n]+)", re.I
)
NEGATIVE = re.compile(r"\b(?:не имеют права|не имеет права|запрещ\w*|не вправе)\b", re.I)
PERMISSION = re.compile(r"\b(?:имеют право|имеет право|вправе)\b", re.I)
UNCERTAIN = re.compile(
    r"\b(?:если|может|могут|мог|могла|могли|возможно|должен|должна|должны|"
    r"при условии|в случае)\b", re.I
)
OWNER_HEADS = {
    "отдела": "отдел", "департамента": "департамент", "службы": "служба",
    "центра": "центр", "блока": "блок", "управления": "управление",
    "директора": "директор", "руководителя": "руководитель", "начальника": "начальник",
}
STOPWORDS = set("и в во на по с со из к для о об при а или не также функции следующие обязан обязаны подразделение".split())


def normalized(value):
    return " ".join(str(value).casefold().replace("ё", "е").split()).strip(" .;:")


def evidence(fragment, quote=None):
    return {"doc": fragment["doc"], "clause": fragment["clause"],
            "quote": fragment["text"] if quote is None else quote, "verified": False}


def _unsupported_statement(text):
    # Dropping a modal or an unrecognised negation would change the obligation.
    return bool(UNCERTAIN.search(text) or re.search(r"\bне\b", NEGATIVE.sub("", text), re.I))


def _header_subject(first):
    subject = re.split(
        r"\s+(?:осуществля\w*|выполня\w*|не имеют права|не имеет права|не вправе|"
        r"имеют право|имеет право|вправе|запрещ\w*|обязан\w*)\b",
        first.rstrip(":"), maxsplit=1, flags=re.I,
    )[0].strip()
    if re.match(r"^функции\s+", subject, re.I):
        subject = re.sub(r"^функции\s+", "", subject, count=1, flags=re.I)
        head, separator, rest = subject.partition(" ")
        subject = OWNER_HEADS.get(head.casefold(), head) + separator + rest
    if not re.match(ENTITY + r"\b", subject, re.I):
        return None
    if re.search(r"\b(?:состоит|подчиня\w*)\b", first, re.I) or _unsupported_statement(first):
        return None
    return subject


def extract_functions(fragments):
    """Keep owning headings and prohibitions; never assign a block duty to its units."""
    contexts = {}
    functions = []
    for f in fragments:
        body = PREFIX.sub("", f["text"]).strip()
        first = body.splitlines()[0] if body else ""
        # Definitions/lists are not executable functions.
        if first.endswith(":"):
            subject = _header_subject(first)
            # An unsupported inner heading masks a broader owning context.
            contexts[f["doc"], f["clause"]] = None
            if subject:
                kind = "prohibition" if NEGATIVE.search(first) else "permission" if PERMISSION.search(first) else "function"
                contexts[f["doc"], f["clause"]] = (subject, kind, evidence(f))
            # A header can contain its duties as bullet rows in the same fragment.
            body = "\n".join(body.splitlines()[1:]).strip()
            if not body:
                continue
        parents = [(clause, ctx) for (doc, clause), ctx in contexts.items()
                   if doc == f["doc"] and clause and
                   (f["clause"] == clause or f["clause"].startswith(clause + "."))]
        parent = max(parents, key=lambda item: len(item[0]))[1] if parents else None
        if (parents and parent is None) or _unsupported_statement(body):
            continue
        direct = DIRECT.match(body)
        if direct:
            unit, action, kind, assignment = direct["unit"].strip(), direct["action"], "function", evidence(f)
            if NEGATIVE.search(unit):
                unit, kind = NEGATIVE.split(unit, maxsplit=1)[0].strip(), "prohibition"
            elif PERMISSION.search(unit):
                continue
            if parent and parent[1] != "function":
                # A direct sentence inside a prohibition/permission list inherits it.
                kind = parent[1]
                assignment = parent[2]
        elif parent:
            unit, kind, assignment = parent
            action = body
        else:
            continue
        if kind == "permission":
            continue
        if NEGATIVE.search(body):
            kind = "prohibition"
        level = "role" if re.match(r"(?:директор|руководитель|начальник|главный аудитор|работники)", unit, re.I) else "block" if re.search(r"\bблок\b", unit, re.I) else "unit"
        for part in re.split(r";\s*|\n", action):
            part = part.strip()
            if len(part) < 12:
                continue
            functions.append({"unit": unit, "function": part, "kind": kind, "level": level,
                              "evidence": [evidence(f, part), assignment]})
    # Overlapping context must not turn one duty into its own duplicate.
    unique = {}
    for item in functions:
        key = (item["unit"], item["kind"], item["function"], item["evidence"][0]["doc"], item["evidence"][0]["clause"])
        unique.setdefault(key, item)
    return list(unique.values())


def tokens(text):
    return [w for w in re.findall(r"[а-яёa-z0-9]+", normalized(text)) if len(w) > 2 and w not in STOPWORDS]


def vectors(texts):
    counts = [Counter(tokens(text)) for text in texts]
    frequencies = Counter(word for count in counts for word in count)
    result = []
    for count in counts:
        vector = {word: n * (1 + math.log((1 + len(counts)) / (1 + frequencies[word]))) for word, n in count.items()}
        norm = math.sqrt(sum(n * n for n in vector.values()))
        result.append({word: n / norm for word, n in vector.items()} if norm else {})
    return result


def cosine(left, right):
    return min(1.0, max(0.0, sum(n * right.get(word, 0) for word, n in left.items())))


def verified_sources(items, fragments):
    """Exact normalized match at document AND clause, not just anywhere in a file."""
    index = {}
    for f in fragments:
        index.setdefault((f["doc"], f["clause"]), []).append(normalized(f["text"]))
    for item in items:
        for source in item.get("evidence", []):
            quote = normalized(source.get("quote", ""))
            source["verified"] = bool(quote) and any(
                quote in text for text in index.get((source.get("doc"), source.get("clause")), [])
            )
    return [item for item in items if item.get("evidence") and all(e["verified"] for e in item["evidence"])]


def _match_functions(left, right, vector, incomplete):
    """Match one-to-one, reserving exact same-owner duties before possible moves.

    Similar alternatives are left for a person. An unresolved candidate is never
    converted to a loss/new claim just because another row used its best match.
    """
    scores = {
        (i, j): cosine(vector[i], vector[len(left) + j])
        for i, f in enumerate(left) for j, g in enumerate(right)
        if f["level"] == g["level"]
    }
    assignments, used = {}, set()

    def same_owner(i, j):
        return normalized(left[i]["unit"]) == normalized(right[j]["unit"])

    # Preserve identical repeated rows by stable pairing within their owner.
    for i, f in enumerate(left):
        for j, g in enumerate(right):
            if j not in used and f["level"] == g["level"] and same_owner(i, j) and normalized(f["function"]) == normalized(g["function"]):
                assignments[i] = j
                used.add(j)
                break

    for require_same_owner in (True, False):
        while True:
            options = {}
            reserved = {j for i in range(len(left)) if i not in assignments
                        for j in range(len(right)) if j not in used
                        and same_owner(i, j) and scores.get((i, j), 0) >= 0.65}
            for i in range(len(left)):
                if i in assignments:
                    continue
                same_owner_options = [j for j in range(len(right))
                                      if j not in used and same_owner(i, j) and scores.get((i, j), 0) >= 0.65]
                # Do not guess a transfer while this owner's own alternatives remain.
                if not require_same_owner and same_owner_options:
                    continue
                options[i] = [(scores[i, j], j) for j in range(len(right))
                              if j not in used and scores.get((i, j), 0) >= 0.65
                              and (require_same_owner or j not in reserved)
                              and (same_owner(i, j) or not require_same_owner)]
            proposals = []
            for i, pairs in options.items():
                pairs = sorted(pairs, reverse=True)
                if not pairs or (len(pairs) > 1 and pairs[0][0] - pairs[1][0] <= 0.03):
                    continue
                score, j = pairs[0]
                competitors = sorted(
                    ((other_score, other_i) for other_i, choices in options.items()
                     for other_score, other_j in choices if other_j == j), reverse=True
                )
                if competitors[0][1] == i and (len(competitors) == 1 or score - competitors[1][0] > 0.03):
                    proposals.append((i, j))
            if not proposals:
                break
            for i, j in proposals:
                assignments[i] = j
                used.add(j)

    mapped, ambiguous = [], []
    for i, f in enumerate(left):
        j = assignments.get(i)
        g = right[j] if j is not None else None
        candidates = [(score, k) for (old_i, k), score in scores.items() if old_i == i and score >= 0.65]
        if g is None and candidates:
            ambiguous.append({
                "side": "before", "unit": f["unit"], "function": f["function"],
                "candidates": [{"unit": right[k]["unit"], "function": right[k]["function"],
                                "similarity": round(score, 4)} for score, k in candidates],
                "evidence": deepcopy(f["evidence"] + [e for _, k in candidates for e in right[k]["evidence"]]),
            })
            continue
        if g is None and incomplete:
            continue
        score = scores[i, j] if g else max((score for (old_i, _), score in scores.items() if old_i == i), default=0.0)
        status = "lost" if g is None else "changed" if score < 0.90 else "kept" if same_owner(i, j) else "moved"
        mapped.append({
            "before_unit": f["unit"], "before_function": f["function"],
            "after_unit": g["unit"] if g else "", "after_function": g["function"] if g else "",
            "status": status, "similarity": round(score, 4),
            "evidence": deepcopy(f["evidence"] + (g["evidence"] if g else [])),
        })
    for j, f in enumerate(right):
        if j in used:
            continue
        candidates = [(score, i) for (i, new_j), score in scores.items() if new_j == j and score >= 0.65]
        if candidates:
            ambiguous.append({
                "side": "after", "unit": f["unit"], "function": f["function"],
                "candidates": [{"unit": left[i]["unit"], "function": left[i]["function"],
                                "similarity": round(score, 4)} for score, i in candidates],
                "evidence": deepcopy(f["evidence"] + [e for _, i in candidates for e in left[i]["evidence"]]),
            })
        elif not incomplete:
            mapped.append({"before_unit": "", "before_function": "", "after_unit": f["unit"],
                           "after_function": f["function"], "status": "new", "similarity": 0.0,
                           "evidence": deepcopy(f["evidence"])})
    return mapped, ambiguous


def run(before: list[Path], after: list[Path], log=None) -> dict:
    def event(step, message):
        if log:
            log(step, "Локально", message)

    if not before or not after:
        raise ValueError("Both document sets are required")
    sides, incomplete = [], False
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", UserWarning)
        for paths in (before, after):
            fragments = []
            for path in paths:
                parsed = parse_document(path)
                if not parsed:
                    raise ValueError("An input document has no readable fragments")
                fragments.extend(parsed)
            sides.append(fragments)
        incomplete = any(issubclass(w.category, UserWarning) for w in captured)
    event("parse", f"Прочитано фрагментов: до {len(sides[0])}, после {len(sides[1])}.")
    functions = [extract_functions(fragments) for fragments in sides]
    units_by_side = []
    for fragments, funcs in zip(sides, functions):
        units = {normalized(u["name"]): u for u in extract_units(fragments)}
        for f in funcs:
            units.setdefault(normalized(f["unit"]), {"name": f["unit"], "abbr": None,
                                                     "level": f["level"], "evidence": [f["evidence"][-1]]})
        units_by_side.append(units)
    old, new = units_by_side
    renamed = {}
    for f in sides[1]:
        for match in RENAME.finditer(PREFIX.sub("", f["text"])):
            renamed[normalized(match["old"])] = (match["new"].strip(), evidence(f))
    units = []
    for key in sorted(old.keys() | new.keys()):
        if key in renamed and key in old:
            name, ev = renamed[key]
            units.append({"name": name, "abbr": None, "status": "reorganized", "evidence": old[key]["evidence"] + [ev]})
            continue
        if any(key == normalized(name) for name, _ in renamed.values()):
            continue
        status = "kept" if key in old and key in new else "created" if key in new else "removed"
        if incomplete and status != "kept":
            continue
        record = new.get(key) or old[key]
        ev = (old[key]["evidence"] if key in old else []) + (new[key]["evidence"] if key in new else [])
        units.append({"name": record["name"], "abbr": record.get("abbr"), "status": status, "evidence": ev})
    event("structure", f"Сопоставлено записей структуры: {len(units)}. Отсутствие упоминания — кандидат на изменение.")
    event("functions", f"Извлечено функций и запретов: {len(functions[0])} / {len(functions[1])}. Только явные исполнители.")
    left = [f for f in functions[0] if f["kind"] == "function"]
    right = [f for f in functions[1] if f["kind"] == "function"]
    vector = vectors([f["function"] for f in left + right])
    mapped, ambiguous = _match_functions(left, right, vector, incomplete)
    event("match", f"TF-IDF по словам; неоднозначных записей: {len(ambiguous)}. Сходство даёт кандидата, а не подтверждение сохранения смысла.")
    findings = []

    def add(kind, title, description, affected, ev, severity="medium"):
        findings.append({"id": f"local-{len(findings) + 1}", "type": kind, "severity": severity,
                         "title": title, "description": description, "units": affected, "evidence": deepcopy(ev)})

    for row in mapped:
        if row["status"] == "lost":
            add("loss", "Кандидат на потерю функции", "В извлечённых функциях новой редакции не найдена достаточно близкая пара. Проверьте полноту извлечения и возможное переформулирование.", [row["before_unit"]], row["evidence"], "high")
    for u in units:
        if u["status"] != "kept":
            add("reorganization", "Признаки изменения структуры", "Сопоставление упоминаний требует проверки ответственным. Упоминание только в одной редакции само по себе не доказывает создание или упразднение.", [u["name"]], u["evidence"], "low")
    for (i, f), (j, g) in combinations(enumerate(right), 2):
        if normalized(f["unit"]) != normalized(g["unit"]) and f["level"] == g["level"] and cosine(vector[len(left) + i], vector[len(left) + j]) >= 0.90:
            add("duplicate", "Признаки дублирования функции", "Близкие формулировки поручены разным исполнителям одного уровня. Проверьте объект, границы ответственности и разделение этапов.", [f["unit"], g["unit"]], f["evidence"] + g["evidence"])
    prohibitions = [f for f in functions[1] if f["kind"] == "prohibition"]
    for p in prohibitions:
        for f in right:
            if normalized(p["unit"]) != normalized(f["unit"]):
                continue
            pv, fv = vectors([NEGATIVE.sub("", p["function"]), f["function"]])
            if cosine(pv, fv) >= 0.75:
                add("conflict", "Возможное противоречие функции и запрету", "Одному исполнителю адресованы близкая функция и запрет. Условия применимости требуют проверки.", [f["unit"]], p["evidence"] + f["evidence"], "high")
    for f, g in combinations(right, 2):
        if normalized(f["unit"]) != normalized(g["unit"]):
            continue
        control, execution = (f, g) if re.match(r"(?:контрол\w*|провер\w*)\b", f["function"], re.I) else (g, f)
        if not re.match(r"(?:контрол\w*|провер\w*)\b", control["function"], re.I) or not re.match(r"(?:выполня\w*|утвержда\w*|согласовыва\w*|ремонтиру\w*)\b", execution["function"], re.I):
            continue
        c, e = tokens(control["function"])[1:], tokens(execution["function"])[1:]
        if len(c) >= 2 and c == e:
            add("conflict", "Признаки совмещения выполнения и контроля", "Выполнение и контроль одного объекта поручены одному исполнителю. Это кандидат на конфликт интересов, требующий оценки полномочий и компенсирующих мер.", [f["unit"]], f["evidence"] + g["evidence"], "high")
    event("findings", f"Сформировано кандидатов: {len(findings)}. Юридических выводов нет.")
    all_fragments = sides[0] + sides[1]
    units = verified_sources(units, all_fragments)
    mapped = verified_sources(mapped, all_fragments)
    ambiguous = verified_sources(ambiguous, all_fragments)
    findings = verified_sources(findings, all_fragments)
    event("verify", "Цитаты проверены по исходному документу и пункту; неподтверждённые записи исключены.")
    counts = Counter(f["type"] for f in findings)
    conclusion = (
        f"Локальный анализ обнаружил {len(findings)} кандидатов с проверенными цитатами: "
        f"потеря функции — {counts['loss']}, дублирование — {counts['duplicate']}, "
        f"конфликт — {counts['conflict']}, изменение структуры — {counts['reorganization']}. "
        "Каждый кандидат раскрыт с источниками на вкладке «Находки». Проверка цитат не подтверждает интерпретацию. "
        "Рекомендуется проверить владельцев функций, переформулировки и полноту комплекта. "
        "Извлечение правилами неполно; отсутствие находок не означает отсутствия рисков."
    )
    if incomplete:
        conclusion += " Есть нечитаемые страницы: выводы об отсутствии функций и подразделений отключены."
    if ambiguous:
        conclusion += f" Неоднозначных записей сопоставления: {len(ambiguous)}; они требуют ручной проверки и не объявлены потерянными или новыми."
    event("report", "Подготовлено рекомендательное заключение только по кандидатам с найденными цитатами.")
    return {"units": units, "function_map": mapped, "findings": findings, "conclusion": conclusion,
            "analysis_mode": "local", "coverage_complete": not incomplete, "ambiguous_matches": ambiguous}
