from __future__ import annotations

import re
from typing import Any

from mainbrain.contracts.schemas import ChatMessage, ChatRequest, ChatResponse, ModelRole, RunGoalRequest
from mainbrain.models.router import ModelRouter


SYSTEM_PROMPT = """Tu esi Main Brain — lokāls Windows AI asistents.
Noteikumi:
1) Atbildi latviešu valodā, 1–3 īsos teikumos.
2) Atbildi TIKAI uz jautājumu. Nekad neatkārto tekstu.
3) Ja nezini faktu (cilvēki, jaunumi, privāta info) — saki: «Man nav šādu lokālo datu.»
4) Neizdomā biogrāfijas un nestāsti muļķības.
5) Matemātiku rēķini precīzi.
6) Ja lūdz izveidot/palaist/labot datorā — īsi apstiprini izpildi."""

_ACTION_RE = re.compile(
    r"(?i)\b("
    r"izveido|izveidot|uzraksti|uzrakstīt|izlabo|labot|palaid|palaist|"
    r"instalē|instalēt|kompilē|build|deploy|dzēs|izdzēs|"
    r"pārbaudi\s+test|uzraksti\s+kod|izveido\s+fail|"
    r"open\s+notepad|atver\s+notepad|atver\s+pārlūk"
    r")\b"
)

# Personu / privātu faktu meklēšana — 1.5B GGUF izdomā muļķības
_PERSON_RE = re.compile(
    r"(?i)("
    # "kas ir Vārds Uzvārds" — divi vārdi, lai neķertu «Kas ir Python?»
    r"\b(kas\s+(ir|bija)|who\s+is|who\s+was)\s+"
    r"[\wāčēģīķļņšūž]+\s+[\wāčēģīķļņšūž]+|"
    r"\b(pastāsti|stāsti|pastāstiet)\s+(man\s+)?par\b|"
    r"\b(atrast|atrod|meklē|meklēt|find|search)\b.{0,40}\b(par|about)\b|"
    r"\binformācij[ua]\s+par\b|"
    r"\b(ko\s+tu\s+zini\s+par|what\s+do\s+you\s+know\s+about)\b|"
    r"\b(persona|person|cilvēks|biogrāfij)\b"
    r")"
)

_BAD_REPLY = re.compile(
    r"(?i)("
    r"izveidojiet\s+savu\s+jautājumu|apstiprinām\s+jūsu\s+risinājumu|"
    r"lūdzu,\s*izveidojiet|riks,\s*ka\s*tev\s*ir|"
    r"tā\s+ir\s+jābūt\s+jautājumu|kādā\s+arī\s+gaidis|"
    r"informācij[ua]\s+par\s+gaidij|"
    r"tu\s+zini\s+latvijas\s+valod"
    r")"
)

_LATVIAN_NAME_TOKEN = re.compile(
    r"^[A-ZĀČĒĢĪĶĻŅŠŪŽ][a-zāčēģīķļņšūž]+(?:s|a|is|us|as|e|o)?$",
    re.UNICODE,
)


def wants_execution(text: str, force_execute: bool | None = None) -> bool:
    if force_execute is True:
        return True
    if force_execute is False:
        return False
    t = (text or "").strip()
    if t.lower().startswith(("izpildi:", "izpildīt:", "dari:", "run:", "/run")):
        return True
    if len(t) < 8:
        return False
    if t.endswith("?") and not _ACTION_RE.search(t):
        return False
    return bool(_ACTION_RE.search(t))


def _dedupe_sentences(text: str) -> str:
    chunks = [c.strip() for c in re.split(r"(?<=[.!?])\s+", text) if c.strip()]
    out: list[str] = []
    for c in chunks:
        if out and c.lower() == out[-1].lower():
            continue
        if out and c.lower() in out[-1].lower() and len(c) > 20:
            continue
        out.append(c)
    return " ".join(out).strip()


def _clean_reply(text: str) -> str:
    t = (text or "").strip()
    for prefix in ("assistant:", "Assistant:", "ASSISTANT:", "Main Brain:", "main brain:"):
        if t.lower().startswith(prefix.lower()):
            t = t[len(prefix) :].strip()
    parts = [p.strip() for p in re.split(r"\n+", t) if p.strip()]
    uniq: list[str] = []
    for p in parts:
        if uniq and p.lower() == uniq[-1].lower():
            continue
        uniq.append(p)
    t = "\n".join(uniq)
    t = _dedupe_sentences(t)
    if len(t) > 400:
        t = t[:400].rsplit(" ", 1)[0] + "…"
    return t.strip()


def _is_junk(text: str) -> bool:
    if not text or len(text.strip()) < 2:
        return True
    if _BAD_REPLY.search(text):
        return True
    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    if len(words) >= 8:
        uniq = len(set(words))
        if uniq / max(1, len(words)) < 0.35:
            return True
    for n in (12, 18, 24):
        if len(text) >= n * 2:
            head = text[:n]
            if text.count(head) >= 2:
                return True
    # Same sentence pasted twice (common with tiny GGUF)
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(sentences) >= 2 and len(set(s.lower() for s in sentences)) == 1:
        return True
    return False


def looks_like_person_lookup(message: str) -> bool:
    """True → neļaujam 1.5B izdomāt biogrāfiju."""
    raw = (message or "").strip()
    if not raw:
        return False
    if _PERSON_RE.search(raw):
        return True

    # Tikai īsa ziņa: «Edgars Gaidulis» / «Edgars Gaidulis?»
    cleaned = re.sub(r"[?!.,;:]+$", "", raw).strip()
    words = [w for w in cleaned.split() if w.isalpha()]
    if 2 <= len(words) <= 3 and all(_LATVIAN_NAME_TOKEN.match(w) for w in words):
        return True

    return False


class ChatService:
    """Conversational front-door to Main Brain + optional goal execution."""

    def __init__(self, models: ModelRouter, brain: Any) -> None:
        self.models = models
        self.brain = brain
        self._sessions: dict[str, list[dict[str, str]]] = {}

    def _history(self, session_id: str) -> list[dict[str, str]]:
        return self._sessions.setdefault(session_id or "default", [])

    async def chat(self, req: ChatRequest) -> ChatResponse:
        session = req.session_id or "default"
        history = self._history(session)
        user_msg = req.message.strip()
        history.append({"role": "user", "content": user_msg})
        # Mazam modelim īsa vēsture — citādi sabrūk / atkārto junk
        if len(history) > 8:
            del history[:-8]

        execute = wants_execution(user_msg, req.force_execute)
        if execute:
            return await self._execute(req, session, history)

        # Vietējās drošās atbildes (bez LLM) — sveiciens, valodas, matemātika, personas
        local = self._local_reply(user_msg)
        if local:
            history.append({"role": "assistant", "content": local})
            return ChatResponse(
                reply=local,
                mode="chat",
                session_id=session,
                messages=[ChatMessage(**m) for m in history[-8:]],
            )

        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history[-4:])

        result = await self.models.complete_messages(
            role=ModelRole.REASONING,
            messages=messages,
            temperature=0.2,
            max_tokens=160,
            frequency_penalty=0.6,
            presence_penalty=0.4,
            repeat_penalty=1.25,
            stop=["\nTu:", "\nUser:", "\nuser:", "\nMain Brain:", "\n\n\n"],
        )

        reply = ""
        model_error = None
        if result.get("ok") and (result.get("text") or "").strip():
            reply = _clean_reply(str(result["text"]))
        else:
            model_error = str(result.get("error") or "Lokālais modelis nav pieejams.")

        if model_error and not reply:
            reply = (
                f"Modelis neatbild ({model_error}). "
                "Pārbaudiet llama-server (FIX_BACKEND.bat / START_MAINBRAIN.bat)."
            )
        elif _is_junk(reply):
            retry = await self.models.complete_messages(
                role=ModelRole.REASONING,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Atbildi latviešu valodā VIENĀ teikumā. "
                            "Ja nezini — «Nezinu.» Bez atkārtojumiem."
                        ),
                    },
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.05,
                max_tokens=80,
                frequency_penalty=0.8,
                repeat_penalty=1.35,
                stop=["\n"],
            )
            if retry.get("ok") and (retry.get("text") or "").strip():
                reply = _clean_reply(str(retry["text"]))
            if _is_junk(reply):
                reply = self._offline_fact_reply(user_msg)

        # Izgriez junk no vēstures, lai nākamais turns nesabojātos
        cleaned_hist: list[dict[str, str]] = []
        for m in history:
            if m["role"] == "assistant" and _is_junk(m["content"]):
                continue
            cleaned_hist.append(m)
        history[:] = cleaned_hist[-8:]
        history.append({"role": "assistant", "content": reply})

        return ChatResponse(
            reply=reply,
            mode="chat",
            session_id=session,
            messages=[ChatMessage(**m) for m in history[-8:]],
        )

    async def _execute(
        self,
        req: ChatRequest,
        session: str,
        history: list[dict[str, str]],
    ) -> ChatResponse:
        ack_text = "Sapratu — sāku izpildi ar aģentiem."
        goal = req.message.strip()
        for prefix in ("izpildi:", "izpildīt:", "dari:", "run:", "/run"):
            if goal.lower().startswith(prefix):
                goal = goal[len(prefix) :].strip()
                break

        result = await self.brain.run_goal(
            RunGoalRequest(
                text=goal,
                workspace_path=req.workspace_path,
                auto_approve_safe=True,
            )
        )
        status = getattr(result.status, "value", str(result.status))
        summary = f"{ack_text}\n\n[Izpilde] Statuss: {status}."
        if result.verification and result.verification.summary:
            summary += f" {result.verification.summary}"
        history.append({"role": "assistant", "content": summary})
        return ChatResponse(
            reply=summary,
            mode="execute",
            session_id=session,
            goal_status=status,
            messages=[ChatMessage(**m) for m in history[-8:]],
        )

    def _local_reply(self, message: str) -> str | None:
        m = message.lower().strip()
        m_clean = re.sub(r"[?!.,;:]+$", "", m).strip()

        if m_clean in {"sveiks", "sveiki", "labdien", "labvakar", "hello", "hi", "hey"}:
            return "Sveiki! Kā varu palīdzēt?"

        if looks_like_person_lookup(message):
            return (
                "Man nav drošu lokālo datu par šo personu. "
                "Esmu lokāls asistents bez interneta — biogrāfijas neizdomāju. "
                "Varu palīdzēt ar kodu, Windows uzdevumiem vai vienkāršiem jautājumiem."
            )

        # Valodu jautājumi — 1.5B bieži sabojā
        if re.search(r"(?i)(valod|language|scottish|scotland|skotij)", message):
            if re.search(r"(?i)(scottish|scotland|skot)", message):
                return (
                    "Skotijā oficiāli lieto angļu; papildus — skotu (Scots) un skotu gēlu. "
                    "Es pats atbildu latviski un angliski."
                )
            return (
                "Es saprotu un atbildu latviešu un angļu valodā. "
                "Citas valodas saprotu vāji — esmu mazs lokāls modelis."
            )

        math_reply = self._try_math(message)
        if math_reply:
            return math_reply

        return None

    @staticmethod
    def _try_math(message: str) -> str | None:
        m = message.lower().strip()
        math = re.fullmatch(
            r"(cik\s+(ir\s+)?)?(\d+)\s*([+\-*/x×])\s*(\d+)\s*\??",
            m,
        )
        if not math:
            return None
        a = int(math.group(3))
        op = math.group(4)
        b = int(math.group(5))
        if op == "+":
            return f"{a} + {b} = {a + b}"
        if op == "-":
            return f"{a} - {b} = {a - b}"
        if op in {"*", "x", "×"}:
            return f"{a} × {b} = {a * b}"
        if op == "/":
            if b == 0:
                return "Dalīt ar nulli nevar."
            return f"{a} ÷ {b} = {a / b:.4g}"
        return None

    @staticmethod
    def _offline_fact_reply(message: str) -> str:
        m = message.lower().strip()
        if m in {"sveiks", "sveiki", "labdien", "hello", "hi"}:
            return "Sveiki! Kā varu palīdzēt?"
        return (
            "Nezinu drošu atbildi uz to (lokālais modelis ir mazs). "
            "Jautā par kodu, Windows uzdevumu vai vienkāršu aprēķinu — tur palīdzēšu labāk."
        )
