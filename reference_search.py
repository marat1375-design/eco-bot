"""Deterministic search over the bot's local Kazakhstan legal corpus."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence


MATCH_DIRECT = "прямое совпадение"
MATCH_RELATED = "связанная норма"
MATCH_KEYWORDS = "совпадение по ключевым словам"

DOCUMENTS = {
    "ecocode.txt": ("Экологический кодекс Республики Казахстан", "https://adilet.zan.kz/rus/docs/K2100000400"),
    "koap_final.txt": ("Кодекс Республики Казахстан об административных правонарушениях", "https://adilet.zan.kz/rus/docs/K1400000235"),
    "nedra.txt": ("Кодекс Республики Казахстан «О недрах и недропользовании»", "https://adilet.zan.kz/rus/docs/K1700000125"),
    "atom.txt": ("Закон Республики Казахстан «Об использовании атомной энергии»", "https://adilet.zan.kz/rus/docs/Z1600000442"),
    "sanpin1.txt": ("Санитарные правила (ДСМ-90)", ""),
    "sanpin2.txt": ("Санитарные правила (ДСМ-90)", ""),
}

STOP_WORDS = {
    "а", "без", "бы", "в", "во", "всех", "где", "для", "до", "его", "и", "из",
    "или", "как", "к", "ли", "на", "не", "о", "об", "от", "по", "покажи", "при",
    "про", "с", "со", "что", "это", "встречается", "говорится", "каких", "каком",
    "законах", "норма", "нормы", "текст", "рк", "республики", "казахстан",
}

SITUATION_MARKERS = (
    "лежит", "лежат", "разлив", "разлито", "произош", "обнаруж", "смешан", "смешаны",
    "хранится", "хранятся", "складирован", "сброшен", "выброшен", "нет тары",
    "без тары", "на грунте", "на земле", "контейнере", "площадке", "территории",
)
REFERENCE_MARKERS = (
    "статья", "статью", "статьи", "пункт", "пункта", "часть", "кодекс", "коап",
    "дсм", "закон", "норматив", "где встреч", "в каких", "найди", "покажи",
)

THEMES = {
    "отходы": {"отход", "мусор", "утилизац", "захоронен", "накоплен", "хранен"},
    "нефтезагрязнение": {"нефтешлам", "нефть", "нефтепродукт", "маслян", "разлив", "загрязнен"},
    "земли": {"земл", "почв", "грунт", "рекультивац", "плодород"},
    "вода": {"вод", "сточн", "сброс", "водоем"},
    "воздух": {"воздух", "атмосфер", "выброс", "эмисси"},
}

DOC_ALIASES = {
    "коап": "административных правонарушениях",
    "экокодекс": "экологический кодекс",
    "экологический кодекс": "экологический кодекс",
    "недра": "недрах и недропользовании",
    "дсм-90": "дсм-90",
    "дсм 90": "дсм-90",
}

_INDEX_CACHE: dict[tuple[object, ...], list[tuple["ReferenceEntry", str, set[str], set[str], set[str]]]] = {}


@dataclass(frozen=True)
class ReferenceEntry:
    document: str
    locator: str
    title: str
    text: str
    url: str = ""
    tags: tuple[str, ...] = ()
    source: str = ""


@dataclass(frozen=True)
class SearchResult:
    entry: ReferenceEntry
    match_type: str
    score: float
    excerpt: str


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zа-яё№-]+", " ", text.lower())).strip()


def _stem(word: str) -> str:
    word = word.lower().replace("ё", "е")
    for ending in (
        "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "ение", "ения",
        "аний", "ать", "ять", "ить", "ться", "ого", "ая", "яя", "ое", "ее", "ые",
        "ие", "ый", "ий", "ой", "ам", "ям", "ах", "ях", "ов", "ев", "ом", "ем",
        "а", "я", "ы", "и", "у", "ю", "е", "о",
    ):
        if len(word) - len(ending) >= 4 and word.endswith(ending):
            return word[:-len(ending)]
    return word


def meaningful_tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[0-9a-zа-яё-]+", normalize(text)) if len(w) > 2 and w not in STOP_WORDS]


def classify_query(text: str, forced_reference: bool = False) -> str:
    """Return ``reference`` or ``situation`` without an LLM call."""
    if forced_reference:
        return "reference"
    value = normalize(text)
    if any(marker in value for marker in REFERENCE_MARKERS) or re.search(r"\b(?:ст(?:атья)?|п(?:ункт)?)\.?\s*\d+", value):
        return "reference"
    if any(marker in value for marker in SITUATION_MARKERS):
        return "situation"
    # Short noun phrases are lookup queries; described facts/actions are situations.
    tokens = meaningful_tokens(value)
    return "reference" if len(tokens) <= 4 else "situation"


def is_reference_query(text: str) -> bool:
    """Compatibility helper used by the Telegram routing layer."""
    return classify_query(text) == "reference"


def _locator(text: str, bare_point: bool = False) -> tuple[str, str]:
    article = re.search(r"(?im)^\s*(статья|ст\.)\s*(\d+(?:-\d+)?)\s*[.:]?\s*([^\n]{0,180})", text)
    point = re.search(r"(?im)^\s*(?:§\s*)?(пункт|п\.)\s*(\d+(?:\.\d+)*)\s*[.:]?\s*([^\n]{0,180})", text)
    if not point and bare_point:
        point = re.search(r"(?m)^\s*()(\d{2,4})\.\s+([^\n]{0,180})", text)
    match = article or point
    if not match:
        return "", ""
    kind = "Статья" if match is article else "Пункт"
    title = match.group(3).strip(" .:-")
    return f"{kind} {match.group(2)}", title


def _chunks(content: str, bare_points: bool = False) -> Iterable[str]:
    boundary = r"\n\s*\n+|(?=^\s*(?:Статья|СТАТЬЯ|Пункт|ПУНКТ)\s+\d+)"
    if bare_points:
        boundary += r"|(?=^\s*\d{2,4}\.\s+)"
    blocks = re.split(boundary, content, flags=re.MULTILINE)
    pending = ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if len(block) < 80:
            pending = f"{pending}\n{block}".strip()
            continue
        yield f"{pending}\n{block}".strip() if pending else block
        pending = ""


def build_entries(txt_bases: Mapping[str, str], articles: Sequence[Mapping[str, object]]) -> list[ReferenceEntry]:
    entries: list[ReferenceEntry] = []
    for article in articles:
        number = str(article.get("number", "")).strip()
        title = str(article.get("title", "")).strip()
        entries.append(ReferenceEntry(
            document=str(article.get("law", "Локальная база ARTICLES")),
            locator=f"Статья {number}" if number else "",
            title=title,
            text=str(article.get("text", "")).strip(),
            url=str(article.get("url", "")).strip(),
            tags=tuple(str(tag) for tag in article.get("tags", []) or []),
            source="ARTICLES",
        ))
    for filename, content in txt_bases.items():
        document, url = DOCUMENTS.get(filename, (filename, ""))
        bare_points = filename.startswith("sanpin")
        for chunk in _chunks(content, bare_points=bare_points):
            locator, title = _locator(chunk, bare_point=bare_points)
            entries.append(ReferenceEntry(document, locator, title, chunk, url, source=filename))
    return entries


def _indexed_entries(txt_bases, articles):
    signature = (
        id(txt_bases),
        tuple((name, len(content)) for name, content in txt_bases.items()),
        id(articles),
        len(articles),
    )
    cached = _INDEX_CACHE.get(signature)
    if cached is not None:
        return cached
    indexed = []
    theme_stems = {name: {_stem(word) for word in words} for name, words in THEMES.items()}
    for entry in build_entries(txt_bases, articles):
        body = normalize(" ".join((entry.document, entry.locator, entry.title, entry.text)))
        body_stems = {_stem(token) for token in meaningful_tokens(body)}
        tag_stems = {_stem(token) for tag in entry.tags for token in meaningful_tokens(tag)}
        entry_themes = {name for name, words in theme_stems.items() if body_stems & words}
        indexed.append((entry, body, body_stems, tag_stems, entry_themes))
    _INDEX_CACHE.clear()
    _INDEX_CACHE[signature] = indexed
    return indexed


def _query_identifiers(query: str) -> tuple[str, str]:
    value = normalize(query)
    article = re.search(r"\b(?:статья|статью|статьи|ст\.?)[ ]*(\d+(?:-\d+)?)", value)
    point = re.search(r"\b(?:пункт|пункта|п\.?)[ ]*(\d+(?:\.\d+)*)", value)
    return (article.group(1) if article else "", point.group(1) if point else "")


def _excerpt(text: str, phrase: str, tokens: Sequence[str], limit: int = 360) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    low = clean.lower()
    pos = low.find(phrase) if phrase else -1
    if pos < 0:
        positions = [low.find(token) for token in tokens if low.find(token) >= 0]
        pos = min(positions) if positions else 0
    start = max(0, pos - 90)
    end = min(len(clean), start + limit)
    value = clean[start:end].strip()
    return ("…" if start else "") + value + ("…" if end < len(clean) else "")


def search_reference(
    query: str,
    txt_bases: Mapping[str, str],
    articles: Sequence[Mapping[str, object]],
    limit: int = 20,
    max_results: int | None = None,
) -> list[SearchResult]:
    if max_results is not None:
        limit = max_results
    phrase = normalize(query)
    tokens = meaningful_tokens(query)
    stems = {_stem(token) for token in tokens}
    article_no, point_no = _query_identifiers(query)
    requested_docs = {target for alias, target in DOC_ALIASES.items() if alias in phrase}
    query_themes = {name for name, words in THEMES.items() if stems & {_stem(w) for w in words}}
    results: list[SearchResult] = []

    for entry, body, body_stems, tag_stems, entry_themes in _indexed_entries(txt_bases, articles):
        exact = bool(phrase and len(phrase) >= 4 and phrase in body)
        identifier = bool(
            (article_no and re.search(rf"\bстатья\s+{re.escape(article_no)}(?:\b|ч\d)", normalize(entry.locator + " " + entry.title)))
            or (point_no and re.search(rf"\bпункт\s+{re.escape(point_no)}\b", body))
        )
        doc_match = bool(requested_docs and any(target in body for target in requested_docs))
        overlap = stems & body_stems
        tag_overlap = stems & tag_stems
        theme_overlap = query_themes & entry_themes

        if exact:
            match_type, score = MATCH_DIRECT, 1000.0 + len(tokens) * 10
        elif identifier:
            match_type, score = MATCH_DIRECT, 900.0 + (80 if doc_match else 0)
        elif theme_overlap or tag_overlap:
            match_type, score = MATCH_RELATED, 500.0 + len(theme_overlap) * 35 + len(tag_overlap) * 12
        elif overlap:
            coverage = len(overlap) / max(1, len(stems))
            match_type, score = MATCH_KEYWORDS, 200.0 + coverage * 100 + len(overlap) * 8
        else:
            continue
        if requested_docs and not doc_match:
            score -= 120
        results.append(SearchResult(entry, match_type, score, _excerpt(entry.text, phrase, tokens)))

    # Prefer ARTICLES for identical norms because their metadata and official URL are structured.
    results.sort(key=lambda item: (-item.score, item.entry.source != "ARTICLES", item.entry.document, item.entry.locator))
    unique: list[SearchResult] = []
    seen: set[tuple[str, str, str]] = set()
    for item in results:
        key = (normalize(item.entry.document), normalize(item.entry.locator), normalize(item.excerpt[:120]))
        if key not in seen:
            seen.add(key)
            unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def format_reference_answer(query: str, results: Sequence[SearchResult]) -> str:
    if not results:
        return f"По запросу «{query.strip()}» в подключенной локальной нормативной базе ничего не найдено."
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        grouped[result.entry.document].append(result)
    lines = [f"Справочный поиск: «{query.strip()}»", ""]
    for document, items in grouped.items():
        lines.append(document)
        for item in items:
            entry = item.entry
            heading = " — ".join(value for value in (entry.locator, entry.title) if value)
            lines.append(f"• {heading or 'Фрагмент документа'}")
            lines.append(f"  Тип: {item.match_type}")
            lines.append(f"  {item.excerpt}")
            if entry.url:
                lines.append(f"  Официальный источник: {entry.url}")
        lines.append("")
    return "\n".join(lines).rstrip()
