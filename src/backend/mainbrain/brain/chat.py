from __future__ import annotations

import re
from typing import Any

from mainbrain.brain.intent import Intent, classify_intent, extract_topic, wants_execution
from mainbrain.contracts.schemas import ChatMessage, ChatRequest, ChatResponse, ModelRole, RunGoalRequest
from mainbrain.core.ids import utc_now
from mainbrain.models.router import ModelRouter


SYSTEM_CHAT = """Tu esi Main Brain — Windows AI ar piekļuvi VISAM lietotāja datoram un internetam.
Noteikumi:
1) Atbildi latviešu valodā, skaidri un pēc būtības.
2) Atbildi TIKAI uz jautājumu. Nekad neatkārto tekstu.
3) Ja ir tīmekļa/meklēšanas konteksts — balsties uz to; neizdomā.
4) Matemātiku rēķini precīzi.
5) Ja lūdz izveidot/palaist/labot datorā — īsi apstiprini izpildi (full_access)."""

SYSTEM_EXPLAIN = """Tu esi Main Brain skolotājs ar internetu un datoru.
Izskaidro tēmu latviešu valodā strukturēti:
1) Kas tas ir (1–2 teikumi)
2) Kā tas strādā (2–4 punkti)
3) Neliels piemērs (kods vai soļi), ja der
Ja dots tīmekļa konteksts — izmanto to. Bez atkārtojumiem."""

SYSTEM_SEARCH = """Tu esi Main Brain ar INTERNETU un pilnu datoru.
Lietotājs lūdz sameklēt. Tev ir tīmekļa rezultāti kontekstā.
1) Apkopo faktus no rezultātiem
2) Norādi 1–3 avotu URL
3) Ja rezultāti vāji — saki to un piedāvā nākamo soli (uztaisi / atver pārlūkā)
Bez muļķībām un bez atkārtojumiem."""

_BAD_REPLY = re.compile(
    r"(?i)("
    r"izveidojiet\s+savu\s+jautājumu|apstiprinām\s+jūsu\s+risinājumu|"
    r"lūdzu,\s*izveidojiet|riks,\s*ka\s*tev\s*ir|"
    r"tā\s+ir\s+jābūt\s+jautājumu|kādā\s+arī\s+gaidis|"
    r"informācij[ua]\s+par\s+gaidij|"
    r"tu\s+zini\s+latvijas\s+valod"
    r")"
)


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
    if len(t) > 1200:
        t = t[:1200].rsplit(" ", 1)[0] + "…"
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
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(sentences) >= 2 and len(set(s.lower() for s in sentences)) == 1:
        return True
    return False


class ChatService:
    """Conversational front-door: intent → explain/search/learn/build/chat."""

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
        if len(history) > 10:
            del history[:-10]

        intent = classify_intent(user_msg, force_execute=req.force_execute)

        if intent == Intent.BUILD:
            return await self._execute(req, session, history)

        if intent == Intent.GREET:
            return self._finish(session, history, "Sveiki! Kā varu palīdzēt?")

        if intent == Intent.MATH:
            math_reply = self._try_math(user_msg)
            if math_reply:
                return self._finish(session, history, math_reply)

        # Valodu īsie FAQ
        if re.search(r"(?i)(valod|language|scottish|scotland|skotij)", user_msg):
            if re.search(r"(?i)(scottish|scotland|skot)", user_msg):
                reply = (
                    "Skotijā oficiāli lieto angļu; papildus — skotu (Scots) un skotu gēlu. "
                    "Es atbildu latviski un angliski."
                )
            else:
                reply = (
                    "Es saprotu un atbildu latviešu un angļu valodā. "
                    "Citas valodas — vāji (lokālais modelis)."
                )
            return self._finish(session, history, reply)

        topic = extract_topic(user_msg)

        # Personas / meklēšana / mācīšanās — ar internetu
        if intent in {Intent.PERSON, Intent.SEARCH, Intent.LEARN, Intent.EXPLAIN}:
            local_hits = self._search_local_knowledge(topic)
            web_hits: list[str] = []
            if self._internet_enabled():
                web_hits = await self._search_web(topic if intent != Intent.PERSON else user_msg)
            if intent == Intent.PERSON and not web_hits and not local_hits:
                return self._finish(
                    session,
                    history,
                    "Internets neatdeva drošus rezultātus par šo personu. "
                    "Mēģini precīzāku vārdu vai «sameklē …».",
                )
            reply = await self._llm_task(
                intent=Intent.SEARCH if intent == Intent.PERSON else intent,
                user_msg=user_msg,
                topic=topic,
                history=history,
                local_hits=local_hits + web_hits,
            )
            if intent == Intent.LEARN and reply and not _is_junk(reply):
                self._remember(topic, reply)
            return self._finish(session, history, reply)

        # Vispārīgs chat
        reply = await self._llm_task(
            intent=Intent.CHAT,
            user_msg=user_msg,
            topic=topic,
            history=history,
            local_hits=[],
        )
        return self._finish(session, history, reply)

    def _finish(self, session: str, history: list[dict[str, str]], reply: str) -> ChatResponse:
        cleaned: list[dict[str, str]] = []
        for m in history:
            if m["role"] == "assistant" and _is_junk(m["content"]):
                continue
            cleaned.append(m)
        history[:] = cleaned[-10:]
        history.append({"role": "assistant", "content": reply})
        return ChatResponse(
            reply=reply,
            mode="chat",
            session_id=session,
            messages=[ChatMessage(**m) for m in history[-10:]],
        )

    async def _llm_task(
        self,
        *,
        intent: Intent,
        user_msg: str,
        topic: str,
        history: list[dict[str, str]],
        local_hits: list[str],
    ) -> str:
        if intent == Intent.EXPLAIN or intent == Intent.LEARN:
            system = SYSTEM_EXPLAIN
            max_tokens = 480
            role = ModelRole.CODING if self._looks_technical(topic) else ModelRole.REASONING
        elif intent == Intent.SEARCH:
            system = SYSTEM_SEARCH
            max_tokens = 360
            role = ModelRole.REASONING
        else:
            system = SYSTEM_CHAT
            max_tokens = 220
            role = ModelRole.REASONING

        context_bits = ""
        if local_hits:
            joined = "\n- ".join(local_hits[:3])
            context_bits = f"\n\nLokālās zināšanas:\n- {joined}"

        if intent == Intent.SEARCH:
            prompt_user = (
                f"Lietotājs lūdz sameklēt: {user_msg}\n"
                f"Tēma: {topic}.{context_bits}\n"
                "Atbildi noderīgi, bez interneta pretīšanām."
            )
        elif intent in {Intent.EXPLAIN, Intent.LEARN}:
            prompt_user = (
                f"Izskaidro: {topic}\n"
                f"Oriģināls jautājums: {user_msg}.{context_bits}"
            )
        else:
            prompt_user = user_msg

        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        # Īsa vēsture + aktuālais prompt
        for m in history[-4:]:
            if m["content"] == user_msg and m["role"] == "user":
                continue
            messages.append(m)
        messages.append({"role": "user", "content": prompt_user})

        result = await self.models.complete_messages(
            role=role,
            messages=messages,
            temperature=0.25 if intent != Intent.CHAT else 0.2,
            max_tokens=max_tokens,
            frequency_penalty=0.55,
            presence_penalty=0.35,
            repeat_penalty=1.22,
            stop=["\nTu:", "\nUser:", "\nuser:", "\nMain Brain:"],
        )

        reply = ""
        if result.get("ok") and (result.get("text") or "").strip():
            reply = _clean_reply(str(result["text"]))
        else:
            err = str(result.get("error") or "Lokālais modelis nav pieejams")
            return (
                f"Modelis neatbild ({err}). "
                "Ja atbildes ir vājas — lejupielādē capable profilu (7B): UPGRADE_MODEL.bat"
            )

        if _is_junk(reply):
            retry = await self.models.complete_messages(
                role=role,
                messages=[
                    {
                        "role": "system",
                        "content": "Atbildi latviešu valodā skaidri, bez atkārtojumiem. Ja nezini — «Nezinu.»",
                    },
                    {"role": "user", "content": prompt_user},
                ],
                temperature=0.05,
                max_tokens=min(200, max_tokens),
                frequency_penalty=0.8,
                repeat_penalty=1.35,
            )
            if retry.get("ok") and (retry.get("text") or "").strip():
                reply = _clean_reply(str(retry["text"]))
            if _is_junk(reply):
                if local_hits:
                    return "\n".join(local_hits[:4])
                return (
                    f"Nezinu drošu atbildi par «{topic}». "
                    "Mēģini vēlreiz vai UPGRADE_MODEL.bat (3B/7B) labākai saprašanai."
                )

        if intent in {Intent.SEARCH, Intent.PERSON} and local_hits:
            reply = f"[Avoti: {len(local_hits)}]\n{reply}"

        if intent == Intent.LEARN:
            reply = f"{reply}\n\n[Iemācīts] Saglabāju īsu kopsavilkumu lokālajā zināšanu bāzē."

        return reply

    def _internet_enabled(self) -> bool:
        runtime = getattr(self.brain, "runtime", None)
        if runtime is not None:
            m = getattr(runtime, "models", None)
            if m is not None and getattr(m, "settings", None) is not None:
                if getattr(m.settings, "offline_mode", False):
                    return False
                return bool(getattr(m.settings, "full_access", True))
            tools = getattr(runtime, "tools", None)
            if tools is not None and getattr(tools, "policy", None) is not None:
                return bool(getattr(tools.policy, "full_access", True))
        return True

    def _search_local_knowledge(self, topic: str) -> list[str]:
        store = getattr(self.brain, "store", None)
        if store is None or not topic.strip():
            return []
        try:
            rows = store.search_knowledge(topic, limit=5)
        except Exception:  # noqa: BLE001 — FTS var mest uz dīvainiem vaicājumiem
            return []
        out: list[str] = []
        for row in rows or []:
            content = str(row.get("content") or "").strip()
            if content:
                out.append(content[:400])
        return out

    async def _search_web(self, query: str) -> list[str]:
        try:
            from mainbrain.tools.web import format_search_for_llm, web_search

            payload = await web_search(query, max_results=5)
            text = format_search_for_llm(payload)
            if not payload.get("ok") and not payload.get("results"):
                return []
            return [text]
        except Exception as exc:  # noqa: BLE001
            return [f"(Interneta meklēšana neizdevās: {exc})"]

    def _remember(self, topic: str, reply: str) -> None:
        store = getattr(self.brain, "store", None)
        if store is None:
            return
        summary = reply.split("\n\n[Iemācīts]")[0].strip()[:800]
        try:
            store.index_knowledge(
                f"{topic}\n{summary}",
                source=f"learn:{topic[:80]}",
                verified=False,
                metadata={"kind": "learn", "topic": topic, "at": utc_now().isoformat()},
            )
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _looks_technical(topic: str) -> bool:
        return bool(
            re.search(
                r"(?i)(python|kod|programm|api|http|json|sql|windows|fail|script|"
                r"javascript|typescript|react|docker|git|regex|funkcij|klase|algoritm)",
                topic,
            )
        )

    async def _execute(
        self,
        req: ChatRequest,
        session: str,
        history: list[dict[str, str]],
    ) -> ChatResponse:
        ack_text = "Sapratu uzdevumu — sāku izpildi ar aģentiem."
        goal = req.message.strip()
        for prefix in ("izpildi:", "izpildīt:", "dari:", "run:", "/run"):
            if goal.lower().startswith(prefix):
                goal = goal[len(prefix) :].strip()
                break

        try:
            result = await self.brain.run_goal(
                RunGoalRequest(
                    text=goal,
                    workspace_path=req.workspace_path,
                    auto_approve_safe=True,
                )
            )
        except Exception as exc:  # noqa: BLE001 — chat nedrīkst mest 500
            err = f"Izpilde neizdevās: {exc}"
            history.append({"role": "assistant", "content": err})
            return ChatResponse(
                reply=err,
                mode="execute",
                session_id=session,
                goal_status="failed",
                messages=[ChatMessage(**m) for m in history[-10:]],
            )

        status = getattr(result.status, "value", str(result.status))
        parts = [ack_text, f"[Izpilde] Statuss: {status}."]

        ver = result.verification
        if ver is not None:
            passed = "OK" if getattr(ver, "passed", False) else "nav OK"
            notes = (getattr(ver, "notes", None) or "").strip()
            parts.append(f"Verifikācija: {passed}." + (f" {notes}" if notes else ""))

        arts = list(getattr(result, "artifacts", None) or [])
        if arts:
            paths = []
            for a in arts[:8]:
                p = getattr(a, "path", None) or (a.get("path") if isinstance(a, dict) else None)
                if p:
                    paths.append(str(p))
            if paths:
                parts.append("Faili:\n- " + "\n- ".join(paths))
                # Parādi hello.py saturu, ja ir
                for p in paths:
                    if p.endswith((".py", ".md", ".txt", ".cs")):
                        try:
                            from pathlib import Path

                            text = Path(p).read_text(encoding="utf-8")[:600]
                            parts.append(f"--- {Path(p).name} ---\n{text}")
                        except OSError:
                            pass
                        break

        summary = "\n".join(parts)
        history.append({"role": "assistant", "content": summary})
        return ChatResponse(
            reply=summary,
            mode="execute",
            session_id=session,
            goal_status=status,
            messages=[ChatMessage(**m) for m in history[-10:]],
        )

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
