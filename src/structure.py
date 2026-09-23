"""Консервативное извлечение структуры по явным текстовым конструкциям.

Не выполняет сравнение редакций и не подтверждает цитаты. Словари содержат
только общие типы подразделений/должностей, а не названия организаций.
Неполная русская морфология, косвенные связи и местоимения не разрешаются.
"""

import re


_UNIT = r"(?:блок(?:а|у|ом|е)?|департамент(?:а|у|ом|е)?|отдел(?:а|у|ом|е)?|управлени[еяю]|служб[аыуе]|центр(?:а|у|ом|е)?|дирекци[яию])"
_ROLE = r"(?:(?:главный|главного|главному|главным|генеральный|генерального|генеральному|генеральным)\s+)?(?:директор(?:а|у|ом)?|аудитор(?:а|у|ом)?|руководител[ьяю]|начальник(?:а|у|ом)?|менеджер(?:а|у|ом)?|президент(?:а|у|ом)?|председател[ьяю])"
_DEFINITION = re.compile(
    rf"\b(?P<name>{_UNIT}\s+[^()\n;:.]+?)\s*"
    r"\((?:далее\s*[-–—]?\s*)?(?P<abbr>[А-ЯЁA-Z][А-ЯЁA-Z0-9-]{1,19})\)", re.I
)
# re.I нужен для названий, но сокращение проверяется отдельно с учётом регистра.
_ABBR = re.compile(r"[А-ЯЁA-Z][А-ЯЁA-Z0-9-]{1,19}\Z")
_ITEM = re.compile(r"^\s*(?:[а-яa-z]|\d+)[.)]\s+(?P<name>.+?)\s*[.;]?\s*$", re.I)
_PREFIX = re.compile(r"^\s*\d+(?:\.\d+)*\.\s*")
_STOP = re.compile(
    r"\s+(?:находится|подчиняется|подчинены|подчиняются|является|осуществляет|"
    r"осуществляется|обязан|обязана|обязаны|должен|должна|должны|имеет|"
    r"вправе|взаимодействует|состоит|включает|входит|входят|разрабатывает|"
    r"утверждает|определяет|организует|несет|несёт|обеспечивает|проводит|"
    r"назначается|выполняет|принимает|контролирует|руководит|может|могут|"
    r"в\s+соответствии|по\s+вопросам|при\s+условии|для|котор\w*|а\s+также)\b", re.I
)
# Ограниченные формы только общих служебных слов; остальные слова не стеммятся.
_FORMS = {
    "блок": ("блок", "блока", "блоку", "блоком", "блоке"),
    "департамент": ("департамент", "департамента", "департаменту", "департаментом", "департаменте"),
    "отдел": ("отдел", "отдела", "отделу", "отделом", "отделе"),
    "управление": ("управление", "управления", "управлению", "управлением", "управлении"),
    "служба": ("служба", "службы", "службе", "службу", "службой"),
    "центр": ("центр", "центра", "центру", "центром", "центре"),
    "дирекция": ("дирекция", "дирекции", "дирекцию", "дирекцией"),
    "директор": ("директор", "директора", "директору", "директором"),
    "аудитор": ("аудитор", "аудитора", "аудитору", "аудитором"),
    "руководитель": ("руководитель", "руководителя", "руководителю", "руководителем"),
    "начальник": ("начальник", "начальника", "начальнику", "начальником"),
    "менеджер": ("менеджер", "менеджера", "менеджеру", "менеджером"),
    "президент": ("президент", "президента", "президенту", "президентом"),
    "председатель": ("председатель", "председателя", "председателю", "председателем"),
    "главный": ("главный", "главного", "главному", "главным"),
    "генеральный": ("генеральный", "генерального", "генеральному", "генеральным"),
    "совет": ("совет", "совета", "совету", "советом"),
    "комитет": ("комитет", "комитета", "комитету", "комитетом"),
}
_CANONICAL = {form: root for root, forms in _FORMS.items() for form in forms}


def _key(name: str) -> str:
    words = name.casefold().split()
    # Меняем только голову названия, не зависимые слова («Совет директоров»).
    modifiers = _FORMS['главный'] + _FORMS['генеральный']
    head_length = 2 if words and words[0] in modifiers else 1
    for index in range(min(head_length, len(words))):
        words[index] = _CANONICAL.get(words[index], words[index])
    return " ".join(words)


def _name(value: str) -> str:
    value = re.split(r"[(),;:\n]", value, maxsplit=1)[0]
    value = _STOP.split(value, maxsplit=1)[0]
    return value.strip(" \t.\u00a0")


def _level(name: str) -> str:
    if re.match(rf"{_ROLE}\b", name, re.I):
        return "role"
    if re.match(r"блок\b", _key(name)):
        return "block"
    if re.match(rf"{_UNIT}\b", name, re.I):
        return "unit"
    return "unknown"


def _evidence(fragment: dict, quote: str) -> dict:
    return {"doc": fragment["doc"], "clause": fragment["clause"],
            "quote": quote, "verified": False}


def _append_unique(items: list, item: dict) -> None:
    if item not in items:
        items.append(item)


def extract_units(fragments: list[dict]) -> list[dict]:
    """Извлечь названия, явные сокращения и непосредственные связи.

    Определения сокращений действуют только в пределах исходного документа.
    Одинаковые названия ролей в разных списках подчинения сохраняются отдельно.
    Идентификатор пункта не считается уникальным. Все цитаты — срезы text,
    verified всегда False. При неоднозначном сокращении связь пропускается.
    """
    records = []
    contexts = []  # (doc, нормализованное имя, контекст роли)
    aliases = {}   # (doc, сокращение) -> индексы, без произвольного выбора

    def add(name, fragment, quote, abbr=None, scope=""):
        name = _name(name)
        if not name:
            return None
        context = (fragment['doc'], _key(name), scope)
        if context in contexts:
            index = contexts.index(context)
            # Конфликтующие явные сокращения не затирают прежнее определение.
            if abbr and records[index]['abbr'] not in (None, abbr):
                context = (*context[:2], scope + ':' + abbr)
                index = contexts.index(context) if context in contexts else len(records)
        else:
            index = len(records)
        if index == len(records):
            contexts.append(context)
            records.append({"name": name, "abbr": abbr, "level": _level(name),
                            "parents": [], "evidence": []})
        record = records[index]
        if abbr:
            record['abbr'] = abbr
            aliases.setdefault((fragment['doc'], abbr), set()).add(index)
        _append_unique(record['evidence'], _evidence(fragment, quote))
        return index

    def resolve(value, fragment):
        value = _name(value)
        if not value:
            return None
        doc = fragment['doc']
        if (doc, value) in aliases:
            matches = aliases[doc, value]
        else:
            matches = {i for i, (source, key, _) in enumerate(contexts)
                       if source == doc and key == _key(value)}
        return next(iter(matches)) if len(matches) == 1 else None

    def entity(value, fragment, quote):
        value = _name(value)
        if re.search(rf"\s+и\s+(?:работник\w*|сотрудник\w*|{_ROLE}|{_UNIT})\b", value, re.I):
            return None
        found = resolve(value, fragment)
        if found is not None:
            _append_unique(records[found]['evidence'], _evidence(fragment, quote))
            return found
        # Не превращаем нерасшифрованное/неоднозначное сокращение в организацию.
        if not re.match(rf"(?:{_ROLE}|{_UNIT}|совет\w*|комитет\w*)\b", value, re.I):
            return None
        if any(doc == fragment['doc'] and key == _key(value) for doc, key, _ in contexts):
            return None
        return add(value, fragment, quote)

    def relate(child, parent, relation, fragment, quote):
        if child is None or parent is None or child == parent:
            return
        parents = records[child]['parents']
        name = records[parent]['name']
        item = next((p for p in parents if p['name'] == name and p['relation'] == relation), None)
        if item is None:
            item = {"name": name, "relation": relation, "evidence": []}
            parents.append(item)
        _append_unique(item['evidence'], _evidence(fragment, quote))

    # Сначала явные определения: ссылки на сокращение могут идти раньше определения.
    for fragment in fragments:
        for match in _DEFINITION.finditer(fragment['text']):
            # «система управления ...» и «процесс управления ...» — не отделы.
            prefix = fragment['text'][:match.start()]
            if re.search(r"\b(?:систем\w*|процесс\w*|метод\w*)\s+\Z", prefix, re.I):
                continue
            if _ABBR.fullmatch(match['abbr']):
                add(match['name'], fragment, match.group(), match['abbr'])

    # Списки подразделений и должностей; область — весь текст, а не номера пунктов.
    lists = []
    for fragment in fragments:
        text = fragment['text']
        header = _PREFIX.sub('', text.split('\n', 1)[0])
        if re.search(r'\b(?:не|может|могут|если)\b', header, re.I):
            continue
        membership = re.match(r"(.+?)\s+(?:состоит из|включает в себя)\b", header, re.I)
        subordinates = re.match(
            r"(.+?)\s+(?:(?:административно|функционально)\s+)?подчиняются\b",
            header, re.I,
        )
        if ':' not in header or not (membership or subordinates):
            continue
        match = membership or subordinates
        parent = entity(match[1], fragment, text)
        if parent is None:
            continue
        relation = ('functional' if re.search(r'\bфункциональ\w*', header, re.I)
                    else 'administrative' if re.search(r'\bадминистратив\w*', header, re.I)
                    else 'unspecified')
        for line in text.splitlines()[1:]:
            item = _ITEM.match(line)
            if not item:
                continue
            name = _name(item['name'])
            if _level(name) == 'unknown':
                continue
            if subordinates and _level(name) != 'role':
                continue
            if membership and _level(name) == 'role':
                continue
            scope = _key(records[parent]['name']) if _level(name) == 'role' else ''
            child = add(name, fragment, text, scope=scope)
            lists.append((child, parent, relation, fragment, text))
    for args in lists:
        relate(*args)

    # Прямые утверждения: X подчиняется Y; X находится в ... подчинении Y;
    # административное руководство X осуществляется Y.
    for fragment in fragments:
        for sentence in re.split(r'(?<=[.!?])\s+|\n', fragment['text']):
            body = _PREFIX.sub('', sentence).strip()
            if re.search(r'\b(?:не|может|могут|должен|должна|если)\b', body, re.I):
                continue  # Не выдаём отрицание, возможность или условие за связь.
            direct = re.match(
                r'(.+?)\s+(?:(?P<adverb>административно|функционально)\s+)?'
                r'(?:подчиняется|находится\s+в\s+(?:(?P<kind>административном|функциональном)\s+)?подчинении)\s+(.+)', body, re.I)
            management = re.search(
                r'\b(?P<kind>административное|функциональное)\s+руководство\s+(.+?)\s+осуществляется\s+(.+)', body, re.I)
            if direct:
                child_text, parent_text = direct[1], direct[4]
                kind = direct['kind'] or direct['adverb'] or ''
            elif management:
                child_text, parent_text = management[2], management[3]
                kind = management['kind']
            else:
                # Только явно названная роль в начале утверждения.
                name = _name(body)
                if _level(name) == 'role' and len(name.split()) <= 12 and _STOP.search(body):
                    entity(name, fragment, sentence)
                continue
            child = entity(child_text, fragment, sentence)
            parent = entity(parent_text, fragment, sentence)
            relation = ('functional' if kind.lower().startswith('функциональ') else
                        'administrative' if kind.lower().startswith('административ') else 'unspecified')
            relate(child, parent, relation, fragment, sentence)
    return records
