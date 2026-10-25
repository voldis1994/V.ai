from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    GREET = "greet"
    MATH = "math"
    PERSON = "person"  # privāta persona — neizdomājam
    EXPLAIN = "explain"  # izskaidro / kas ir (koncepts)
    LEARN = "learn"  # iemācies — izskaidro + saglabā zināšanās
    SEARCH = "search"  # sameklē — internets + atver pārlūku
    BUILD = "build"  # uztaisi / izveido / uzprogrammē
    OPEN = "open"  # atver programmu / failu / pārlūku
    CHAT = "chat"


_GREET_RE = re.compile(
    r"(?i)^\s*(sveiks|sveiki|labdien|labvakar|hello|hi|hey)[!.,\s]*$"
)

_MATH_RE = re.compile(
    r"(?i)^\s*(cik\s+(ir\s+)?)?\d+\s*[+\-*/x×]\s*\d+\s*\??\s*$"
)

_BUILD_RE = re.compile(
    r"(?i)\b("
    r"izveido|izveidot|uztaisi|uztaisīt|uzraksti|uzrakstīt|"
    r"uzprogrammē|uzprogrammēt|uzbūvē|uzbūvēt|"
    r"izlabo|labot|instalē|instalēt|"
    r"kompilē|build|deploy|dzēs|izdzēs|"
    r"uzraksti\s+kod|izveido\s+fail|izveido\s+programm|"
    r"uztaisi\s+programm|make\s+a\s+|create\s+a\s+|write\s+a\s+|"
    # «palaid skriptu/testu» = build; tīrs «atver notepad» = OPEN (zemāk)
    r"palaid\s+(skript|test|kod|python|program)|"
    r"hello\s*world|hello\.py|\.py\b"
    r")\b"
)

_EXPLAIN_RE = re.compile(
    r"(?i)\b("
    r"izskaidro|izskaidrot|paskaidro|paskaidrot|"
    r"pastāsti\s+kā|stāsti\s+kā|kā\s+strādā|kā\s+darbojas|"
    r"what\s+is|how\s+does|how\s+do\s+i|explain|"
    r"kas\s+(ir|bija)\b(?!\s+[\wāčēģīķļņšūž]+\s+[\wāčēģīķļņšūž]+)"  # «kas ir X» bet ne «kas ir Vārds Uzvārds»
    r")\b"
)

_LEARN_RE = re.compile(
    r"(?i)\b(iemācies|iemācīties|iemācīt|iemāci|iemāciet|learn|teach\s+me|apgūt|apgūsti)\b"
)

_SEARCH_RE = re.compile(
    r"(?i)\b("
    r"sameklē|sameklēt|meklē|meklēt|atrast|atrod|"
    r"find|search|google|look\s+up|"
    r"informācij[ua]\s+par"
    r")\b"
)

_OPEN_RE = re.compile(
    r"(?i)\b("
    r"atver|atvērt|open|palaid|palaist|"
    r"atver\s+pārlūk|open\s+browser|start\s+"
    r")\b"
)

_PERSON_HINT_RE = re.compile(
    r"(?i)\b(persona|person|cilvēks|biogrāfij|who\s+is|who\s+was)\b"
)

_NAME_TOKEN = re.compile(
    r"^[A-ZĀČĒĢĪĶĻŅŠŪŽ][a-zāčēģīķļņšūž]+(?:s|a|is|us|as|e)?$",
    re.UNICODE,
)

_ABOUT_RE = re.compile(
    r"(?i)\b(?:par|about)\s+(.+?)(?:\s*[?!.]|$)"
)


def _name_tokens(text: str) -> list[str]:
    words = re.findall(r"[\wāčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ]+", text, flags=re.UNICODE)
    return [w for w in words if _NAME_TOKEN.match(w)]


def looks_like_human_name(text: str) -> bool:
    """Vārds + uzvārds (vai 2 Title-Case tokens)."""
    names = _name_tokens(text)
    if len(names) >= 2:
        return True
    # «Edgars Gaidulis» arī lowercase kontekstā: divi vārdi pēc «par»
    m = _ABOUT_RE.search(text)
    if m:
        parts = [p for p in re.split(r"\s+", m.group(1).strip()) if p.isalpha()]
        if len(parts) >= 2 and all(len(p) >= 3 for p in parts[:2]):
            # Izslēdz tipiskus tehniskos terminus
            tech = {
                "python",
                "windows",
                "linux",
                "javascript",
                "typescript",
                "docker",
                "react",
                "fastapi",
                "llama",
                "main",
                "brain",
            }
            if parts[0].lower() not in tech and parts[1].lower() not in tech:
                # Divi vārdi pēc «par» bieži ir persona, ja nav tech
                if parts[0][:1].isupper() or parts[1][:1].isupper() or len(parts) >= 2:
                    # lowercase «edgars gaidulis» — joprojām persona, ja abi izskatās pēc vārdiem
                    if not any(p.lower() in tech for p in parts):
                        return len(parts) >= 2 and all(p.isalpha() for p in parts[:2])
    return False


def extract_topic(message: str) -> str:
    m = _ABOUT_RE.search(message)
    if m:
        return m.group(1).strip(" ?.!,;:")
    # «izskaidro X», «iemācies X», «sameklē X»
    m2 = re.search(
        r"(?i)\b(?:izskaidro|izskaidrot|paskaidro|iemācies|iemācīties|iemāci|"
        r"sameklē|meklē|atrast|explain|learn|find|search)\s+(.+)$",
        message.strip(),
    )
    if m2:
        return m2.group(1).strip(" ?.!,;:")
    m3 = re.search(r"(?i)\bkas\s+ir\s+(.+?)[\s?]*$", message.strip())
    if m3:
        return m3.group(1).strip(" ?.!,;:")
    return message.strip()


def classify_intent(text: str, *, force_execute: bool | None = None) -> Intent:
    """Deterministiska intent klasifikācija — 1.5B modelim neuzticamies."""
    if force_execute is True:
        return Intent.BUILD
    if force_execute is False:
        # lietotājs aizliedza izpildi — tomēr var būt explain/search
        pass

    t = (text or "").strip()
    if not t:
        return Intent.CHAT

    if t.lower().startswith(("izpildi:", "izpildīt:", "dari:", "run:", "/run")):
        return Intent.BUILD

    if _GREET_RE.match(t):
        return Intent.GREET
    if _MATH_RE.match(t):
        return Intent.MATH

    topic = extract_topic(t)
    personish = bool(_PERSON_HINT_RE.search(t)) or looks_like_human_name(t) or looks_like_human_name(
        topic
    )

    # «persona X» / «kas ir Vārds Uzvārds» / «info par Vārds Uzvārds»
    if personish and (_PERSON_HINT_RE.search(t) or _SEARCH_RE.search(t) or _ABOUT_RE.search(t)):
        return Intent.PERSON
    if personish and re.search(r"(?i)\b(kas\s+(ir|bija)|who\s+is|who\s+was)\b", t):
        parts = topic.split()
        if len(parts) >= 2:
            return Intent.PERSON

    explicit_do = bool(
        re.search(
            r"(?i)\b("
            r"izveido|uztaisi|uzraksti|uzprogrammē|uzbūvē|"
            r"build|create|make|write\s+a|deploy|instalē|kompilē|"
            r"izlabo|labo\s+kod|palaid\s+skript|izpildi\s+uzdev"
            r")\b",
            t,
        )
    )
    howto_only = bool(re.search(r"(?i)\b(kā\s+uztais|kā\s+izveidot|how\s+to\s+)", t)) and not explicit_do

    # Atver programmu / pārlūku — PIRMS build, ja nav izveido/uztaisi
    if _OPEN_RE.search(t) and not _SEARCH_RE.search(t) and not explicit_do:
        # «atver un uztaisi» already has explicit_do; tīrs «atver notepad» = OPEN
        if not _BUILD_RE.search(t):
            return Intent.OPEN

    # BUILD PIRMS «iemācies» — «iemācies UN uztaisi» = IZPILDE (nevis tikai runāšana)
    if force_execute is not False and (_BUILD_RE.search(t) or explicit_do):
        if howto_only:
            if _SEARCH_RE.search(t):
                return Intent.SEARCH
            if _LEARN_RE.search(t):
                return Intent.LEARN
            return Intent.EXPLAIN
        if t.endswith("?") and not explicit_do and not _BUILD_RE.search(t):
            pass
        else:
            return Intent.BUILD

    # Tīra mācīšanās / skaidrojums (bez izveido/uztaisi)
    if _LEARN_RE.search(t):
        return Intent.LEARN
    if _EXPLAIN_RE.search(t):
        return Intent.EXPLAIN

    if _SEARCH_RE.search(t):
        return Intent.SEARCH

    # Īsa ziņa = tikai vārds uzvārds
    cleaned = re.sub(r"[?!.,;:]+$", "", t).strip()
    words = [w for w in cleaned.split() if w.isalpha()]
    if 2 <= len(words) <= 3 and all(_NAME_TOKEN.match(w) for w in words):
        return Intent.PERSON

    return Intent.CHAT


def wants_execution(text: str, force_execute: bool | None = None) -> bool:
    return classify_intent(text, force_execute=force_execute) == Intent.BUILD
