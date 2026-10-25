from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from pathlib import Path
from urllib.parse import quote

from mainbrain.brain.actions import PhysicalActor, duckduckgo_url
from mainbrain.brain.intent import Intent, classify_intent, extract_topic, wants_execution
from mainbrain.contracts.schemas import ChatMessage, ChatRequest, ChatResponse, ModelRole, RunGoalRequest
from mainbrain.core.ids import utc_now
from mainbrain.models.router import ModelRouter

# Interaktīvā chata budžets — atgriežam atbildi PIRMS UI HttpClient noklusējuma (100s)
_CHAT_LLM_BUDGET_SEC = 70.0
_CHAT_RETRY_BUDGET_SEC = 28.0


SYSTEM_CHAT = """Tu esi Main Brain — lokāls Windows AI (llama.cpp + GGUF). Ollama NAV ieslēgta.
full_access=ON: drīksti lietot VISU datoru, programmas un internetu (arī publisku info par cilvēkiem).
Noteikumi:
1) Atbildi latviešu valodā — skaidri, konkrēti, bez tukšām frāzēm.
2) Atbildi TIKAI uz jautājumu. Nekad neatkārto lietotāja tekstu.
3) Ja dots konteksts (zināšanas / internets) — balsties uz to; neizdomā faktus.
4) Matemātiku rēķini precīzi.
5) NEDRĪKSTI atteikties no meklēšanas / pārlūka / personu publiskas info — lietotājs to atļāvis.
6) Ja nezini — saki «Nezinu» un dari «sameklē …» / «uztaisi …».
7) Īsas atbildes (2–6 teikumi), ja nav lūgts citādi."""

SYSTEM_EXPLAIN = """Tu esi Main Brain skolotājs (llama.cpp, bez Ollama).
Izskaidro latviešu valodā:
1) Kas tas ir (1–2 teikumi)
2) Kā strādā (2–4 punkti)
3) Neliels piemērs, ja der
Izmanto doto kontekstu. Bez atkārtojumiem un bez muļķībām."""

SYSTEM_SEARCH = """Tu esi Main Brain ar PILNU piekļuvi internetam un datoram (full_access).
Lietotājs EXPLICĪTI atļāvis meklēt publisku info (arī par cilvēkiem).
1) Apkopo TIKAI no dotajiem meklēšanas rezultātiem — saviem vārdiem latviski
2) Norādi 1–3 URL
3) NEDRĪKSTI atteikties («nevaru par personām», «privātums», «noteikumi») — tas ir aizliegts
4) Ja rezultātu maz — saki to un atsaucies uz atvērto pārlūka meklēšanu
Bez atkārtojumiem un bez morāles lekcijām."""

_BAD_REPLY = re.compile(
    r"(?i)("
    r"izveidojiet\s+savu\s+jautājumu|apstiprinām\s+jūsu\s+risinājumu|"
    r"lūdzu,\s*izveidojiet|riks,\s*ka\s*tev\s*ir|"
    r"tā\s+ir\s+jābūt\s+jautājumu|kādā\s+arī\s+gaidis|"
    r"informācij[ua]\s+par\s+gaidij|"
    r"tu\s+zini\s+latvijas\s+valod|"
    # Ekrānšāviņa muļķības — modelis izdomā «nevaru audio» u.tml.
    r"nevaru\s+atbildēt\s+audio|tikai\s+tev\s+palīdzot|"
    r"zaudētu\s+informāciju|paziņojiet\s+man\s+par\s+to|"
    r"as an ai|i('m| am) (just |only )?(a )?language model|"
    r"es\s+nevaru\s+(palīdzēt|izpildīt|darīt)\s+šo|"
    r"diemžēl\s+es\s+nevaru\s+izpildīt|"
    # «Nobloķēts» — modelis atsakās meklēt cilvēkus / internetu
    r"nevaru\s+informēt\s+par\s+konkrēt|nezinu,?\s+kāds\s+ir\s+šī\s+persona|"
    r"atbilst\s+noteikumiem|privātuma\s+apsvērum|"
    r"i\s+can'?t\s+(help|provide|share).{0,40}(person|people|private)|"
    r"nevaru\s+(sameklēt|meklēt|atvērt)|man\s+nav\s+piekļuves\s+internet|"
    r"es\s+nevaru\s+pārlūkot|cannot\s+browse|don'?t\s+have\s+access\s+to\s+(the\s+)?internet"
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

        if intent == Intent.OPEN:
            return self._physical_open(req, session, history, user_msg)

        # Kamera / sejas / «ko tu redzi» — fiziska uztvere
        if re.search(
            r"(?i)\b(kamer|camera|webcam|seja|face|ko\s+tu\s+redzi|redzi\s+mani|"
            r"atpazī\w*\s+sej|face\s+recogn)",
            user_msg,
        ) and intent != Intent.BUILD:
            # Ja lūdz izveidot programmu — BUILD jau apstrādāts; šeit = analizē tagad
            if not re.search(r"(?i)\b(izveido|uztaisi|uzraksti|uzprogrammē)\b", user_msg):
                return await self._camera_sense(req, session, history, user_msg)

        if intent == Intent.GREET:
            return self._finish(
                session,
                history,
                "Sveiki! Esmu Main Brain — lokāls AI (llama.cpp + GGUF, bez Ollama). "
                "Es mācos no mūsu sarunām zināšanu bāzē. Ko darām?",
            )

        if intent == Intent.MATH:
            math_reply = self._try_math(user_msg)
            if math_reply:
                return self._finish(session, history, math_reply)

        # Meta: mācīšanās / Ollama — godīga, deterministiska atbilde (bez LLM muļķībām)
        meta = self._meta_about_self(user_msg)
        if meta:
            return self._finish(session, history, meta)

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

        # Personas / meklēšana — internets + FIZISKI atver pārlūku
        if intent in {Intent.PERSON, Intent.SEARCH}:
            resp = await self._search_and_act(req, session, history, user_msg, topic, intent)
            if resp.reply and not _is_junk(resp.reply):
                self._remember(topic, resp.reply, kind="search")
            return resp

        if intent in {Intent.LEARN, Intent.EXPLAIN}:
            # Ja «iemācies» + izveido — tas jau ir BUILD; šeit tikai tīra mācīšanās
            local_hits = self._search_local_knowledge(topic)
            web_hits: list[str] = []
            if self._internet_enabled():
                web_hits = await self._search_web(topic)
            reply = await self._llm_task(
                intent=intent,
                user_msg=user_msg,
                topic=topic,
                history=history,
                local_hits=local_hits + web_hits,
            )
            if _is_junk(reply):
                # Neļaujam muļķīgai LLM atbildei — izmantojam faktus / skaidru statusu
                if web_hits or local_hits:
                    reply = "\n".join((local_hits + web_hits)[:3])
                else:
                    reply = (
                        f"Apgūstu tēmu «{topic}». "
                        "Šobrīd maz gatavu faktu — mēģini «sameklē {topic}» vai UPGRADE_MODEL.bat."
                    ).replace("{topic}", topic)
            saved = self._remember(
                topic, reply, kind="learn" if intent == Intent.LEARN else "explain"
            )
            if intent == Intent.LEARN:
                status = (
                    "[Iemācīts] Saglabāju lokālajā zināšanu bāzē — nākamreiz izmantošu."
                    if saved
                    else "[Atmiņa] Šī atbilde jau bija saglabāta vai bija pārāk īsa."
                )
                reply = f"{reply}\n\n{status}"
            return self._finish(session, history, reply)

        # Vispārīgs chat — VIENMĒR atmiņa; jautājumiem arī internets; pēc tam mācās
        local_hits = self._search_local_knowledge(topic)
        if not local_hits:
            local_hits = self._search_local_knowledge(user_msg)
        web_hits: list[str] = []
        if self._internet_enabled() and self._looks_like_question(user_msg):
            web_hits = await self._search_web(topic if topic else user_msg)
        reply = await self._llm_task(
            intent=Intent.CHAT,
            user_msg=user_msg,
            topic=topic,
            history=history,
            local_hits=local_hits + web_hits,
        )
        if _is_junk(reply):
            if local_hits or web_hits:
                reply = "\n".join((local_hits + web_hits)[:3])
            else:
                reply = (
                    "Nesapratu skaidri. Spied konkrēti:\n"
                    "• «uztaisi …» — izpildīšu uzdevumu\n"
                    "• «iemācies …» — saglabāšu zināšanās\n"
                    "• «sameklē …» — internets + pārlūks\n"
                    "• «atver notepad» — fiziski atvēršu"
                )
        learned = False
        if reply and not _is_junk(reply):
            learned = self._remember(topic or user_msg, reply, kind="chat")
        if learned and self._looks_like_question(user_msg):
            reply = f"{reply}\n\n〔atmiņa〕 Saglabāju šo atbildi nākamajām reizēm."
        return self._finish(session, history, reply)

    def _actor(self) -> PhysicalActor | None:
        tools = getattr(getattr(self.brain, "runtime", None), "tools", None)
        if tools is None:
            return None
        return PhysicalActor(tools)

    def _finish(
        self,
        session: str,
        history: list[dict[str, str]],
        reply: str,
        *,
        mode: str = "chat",
        goal_status: str | None = None,
        ui_action: str | None = None,
        open_url: str | None = None,
        open_path: str | None = None,
        focus: str | None = None,
        speak_text: str | None = None,
        image_path: str | None = None,
        user_msg: str | None = None,
    ) -> ChatResponse:
        cleaned: list[dict[str, str]] = []
        for m in history:
            if m["role"] == "assistant" and _is_junk(m["content"]):
                continue
            cleaned.append(m)
        history[:] = cleaned[-10:]
        history.append({"role": "assistant", "content": reply})

        # Audio: ja lietotājs lūdz runāt / pasaki
        speak = speak_text
        probe = (user_msg or "").lower()
        if speak is None and re.search(r"(?i)\b(pasaki|runā|speak|audio|skaļi|izrunā)\b", probe):
            speak = reply
        if speak:
            actor_tools = getattr(getattr(self.brain, "runtime", None), "tools", None)
            if actor_tools is not None:
                try:
                    from mainbrain.contracts.schemas import ToolRequest

                    actor_tools.execute(
                        ToolRequest(
                            tool="audio.speak",
                            arguments={"text": speak[:800], "lang": "lv"},
                            agent_id="ChatService",
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

        return ChatResponse(
            reply=reply,
            mode=mode,
            session_id=session,
            goal_status=goal_status,
            messages=[ChatMessage(**m) for m in history[-10:]],
            ui_action=ui_action,
            open_url=open_url,
            open_path=open_path,
            focus=focus,
            speak_text=speak,
            image_path=image_path,
        )

    async def _camera_sense(
        self,
        req: ChatRequest,
        session: str,
        history: list[dict[str, str]],
        user_msg: str,
    ) -> ChatResponse:
        tools = getattr(getattr(self.brain, "runtime", None), "tools", None)
        if tools is None:
            return self._finish(
                session,
                history,
                "Kameras rīki nav pieejami. Instalē OpenCV: scripts\\install_sense.ps1",
                user_msg=user_msg,
            )
        from mainbrain.contracts.schemas import ToolRequest

        vision = tools.execute(
            ToolRequest(tool="vision.analyze", arguments={"camera_index": 0}, agent_id="ChatService")
        )
        faces = tools.execute(
            ToolRequest(tool="face.detect", arguments={"camera_index": 0}, agent_id="ChatService")
        )
        vout = vision.output if isinstance(vision.output, dict) else {}
        fout = faces.output if isinstance(faces.output, dict) else {}
        if not vision.ok and not faces.ok:
            err = vout.get("error") or fout.get("error") or vision.error or faces.error
            return self._finish(
                session,
                history,
                f"Kamera/analīze neizdevās: {err}. "
                "Pārbaudi kameras atļaujas un palaid scripts\\install_sense.ps1",
                user_msg=user_msg,
            )
        desc = vout.get("description") or fout.get("summary") or "Kadrs saglabāts."
        path = fout.get("annotated_path") or vout.get("path") or fout.get("path")
        reply = (
            f"{desc}\n"
            f"Sejas: {fout.get('face_count', 0)}. "
            f"Kadrs: {path or '—'}.\n"
            "Ja gribi programmu: «izveido sejas atpazīšanas programmu»."
        )
        # Runā rezultātu skaļi
        return self._finish(
            session,
            history,
            reply,
            mode="act",
            ui_action="open_path",
            open_path=path,
            focus="live",
            speak_text=desc,
            image_path=path,
            user_msg=user_msg,
        )

    async def _search_and_act(
        self,
        req: ChatRequest,
        session: str,
        history: list[dict[str, str]],
        user_msg: str,
        topic: str,
        intent: Intent,
    ) -> ChatResponse:
        """VIENMĒR: atver pārlūku + meklē + izskaidro. Nekādu «nevaru par personām»."""
        q = (topic if topic else user_msg).strip() or user_msg
        search_q = user_msg if intent == Intent.PERSON else q

        # 1) FIZISKI atver pārlūku PIRMS LLM — lietotājs REDZ meklēšanu
        url = duckduckgo_url(search_q)
        actor = self._actor()
        opened: dict[str, Any] | None = None
        if actor is not None:
            try:
                opened = actor.search_and_open(search_q)
                url = str(opened.get("url") or url)
            except Exception as exc:  # noqa: BLE001
                opened = {"error": str(exc)}

        # 2) Faktiski rezultāti (DDG + Wikipedia) — neatkarīgi no modeļa «bloķēšanas»
        local_hits = self._search_local_knowledge(q)
        web_hits: list[str] = []
        wiki_bits: list[str] = []
        if self._internet_enabled():
            web_hits = await self._search_web(search_q)
            wiki_bits = await self._search_wikipedia(search_q)

        facts = [h for h in (wiki_bits + web_hits + local_hits) if h and not h.startswith("(")]
        factual = self._facts_to_reply(q, facts)

        # 3) LLM tikai pārfrāzē FAKTUS — ja atsakās / muļķojas, ņem factual
        reply = factual
        if facts:
            llm_reply = await self._llm_task(
                intent=Intent.SEARCH,
                user_msg=user_msg,
                topic=q,
                history=history[-2:],
                local_hits=facts[:4],
            )
            if llm_reply and not _is_junk(llm_reply):
                reply = llm_reply
        elif not factual:
            reply = (
                f"Atvēru interneta meklēšanu pārlūkā par «{q}». "
                "Rezultāti ielādējas pārlūkā — paskaties logu; ja vajag, pajautā vēlreiz pēc 2 sekundēm."
            )

        if _is_junk(reply):
            reply = factual or (
                f"Atvēru pārlūkā: {url}\n"
                "Modelis mēģināja atteikties, bet full_access ir ieslēgts — meklēšana ir atvērta."
            )

        act_note = f"\n\n[Darbība] Atvēru pārlūku un sameklēju → {url}"
        if isinstance(opened, dict) and opened.get("error"):
            act_note += f" (bridge: {opened.get('error')}; UI/os.startfile joprojām mēģināja)"
        self._remember(q, reply, kind="search")
        return self._finish(
            session,
            history,
            reply + act_note,
            mode="act",
            ui_action="open_browser",
            open_url=url,
            focus="browser",
        )

    @staticmethod
    def _facts_to_reply(topic: str, facts: list[str]) -> str:
        if not facts:
            return ""
        lines = [f"Par «{topic}» no interneta:"]
        for i, f in enumerate(facts[:4], 1):
            chunk = f.strip()
            if len(chunk) > 450:
                chunk = chunk[:450] + "…"
            lines.append(f"{i}) {chunk}")
        lines.append("Pārlūkā atvēru pilno meklēšanu — tur vari lasīt avotus.")
        return "\n".join(lines)

    async def _search_wikipedia(self, query: str) -> list[str]:
        """Ātri fakti par cilvēkiem/tēmām — bez LLM bloķēšanas."""
        q = (query or "").strip()
        if not q:
            return []
        out: list[str] = []
        try:
            import httpx

            headers = {"User-Agent": "MainBrainOS/1.2 (local; full_access)"}
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
                for lang in ("lv", "en"):
                    r = await client.get(
                        f"https://{lang}.wikipedia.org/w/api.php",
                        params={
                            "action": "opensearch",
                            "search": q,
                            "limit": 1,
                            "namespace": 0,
                            "format": "json",
                        },
                    )
                    if r.status_code >= 400:
                        continue
                    data = r.json()
                    titles = data[1] if isinstance(data, list) and len(data) > 1 else []
                    if not titles:
                        continue
                    title = str(titles[0])
                    s = await client.get(
                        f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title, safe='')}"
                    )
                    if s.status_code >= 400:
                        continue
                    js = s.json()
                    extract = str(js.get("extract") or "").strip()
                    page_url = str((js.get("content_urls") or {}).get("desktop", {}).get("page") or "")
                    if extract:
                        bit = extract[:500]
                        if page_url:
                            bit += f"\nAvots: {page_url}"
                        out.append(bit)
                        break
        except Exception:  # noqa: BLE001
            return out
        return out

    def _physical_open(
        self,
        req: ChatRequest,
        session: str,
        history: list[dict[str, str]],
        user_msg: str,
    ) -> ChatResponse:
        actor = self._actor()
        if actor is None:
            return self._finish(session, history, "Rīki nav pieejami — nevaru atvērt programmu.")

        app = actor.detect_open_app(user_msg)
        # atver pārlūku / URL
        if re.search(r"(?i)(pārlūk|browser|chrome|edge|firefox|internet)", user_msg) or re.search(
            r"https?://", user_msg
        ):
            m = re.search(r"(https?://\S+)", user_msg)
            url = m.group(1) if m else "https://duckduckgo.com/"
            if not m and re.search(r"(?i)meklē|search|samekl", user_msg):
                url = duckduckgo_url(extract_topic(user_msg))
            try:
                actor.open_url(url)
            except Exception as exc:  # noqa: BLE001
                return self._finish(session, history, f"Neizdevās atvērt pārlūku: {exc}")
            return self._finish(
                session,
                history,
                f"Atvēru pārlūku: {url}",
                mode="act",
                ui_action="open_browser",
                open_url=url,
                focus="browser",
            )

        if app:
            result = actor.launch_app(app)
            ok = bool(result.get("ok") or result.get("performed"))
            return self._finish(
                session,
                history,
                f"{'Atvēru' if ok else 'Mēģināju atvērt'} programmu «{app}».",
                mode="act",
                ui_action="open_app",
                focus="home",
            )

        # fails ceļš
        m = re.search(r"(?i)([a-z]:\\[^\s]+|/[^\s]+|\S+\.(py|txt|md|cs|json))", user_msg)
        if m:
            path = m.group(1)
            actor.open_path(path)
            return self._finish(
                session,
                history,
                f"Atvēru: {path}",
                mode="act",
                ui_action="open_path",
                open_path=path,
                focus="editor",
            )

        return self._finish(
            session,
            history,
            "Norādi ko atvērt — piem.: «atver notepad», «atver pārlūku», «atver chrome».",
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
        # 7B Q4: pietiekami tokeni kvalitātei, bet ne tik daudz, lai 100s timeout
        if intent == Intent.EXPLAIN or intent == Intent.LEARN:
            system = SYSTEM_EXPLAIN
            max_tokens = 360
            role = ModelRole.CODING if self._looks_technical(topic) else ModelRole.REASONING
        elif intent == Intent.SEARCH:
            system = SYSTEM_SEARCH
            max_tokens = 260
            role = ModelRole.REASONING
        else:
            system = SYSTEM_CHAT
            max_tokens = 220
            role = ModelRole.REASONING

        context_bits = ""
        if local_hits:
            joined = "\n- ".join(h[:350] for h in local_hits[:3])
            context_bits = f"\n\nZināšanas / konteksts (izmanto!):\n- {joined}"

        if intent == Intent.SEARCH:
            prompt_user = (
                f"Lietotājs lūdz sameklēt: {user_msg}\n"
                f"Tēma: {topic}.{context_bits}\n"
                "Atbildi noderīgi, īsākām teikumiem."
            )
        elif intent in {Intent.EXPLAIN, Intent.LEARN}:
            prompt_user = (
                f"Izskaidro īsi: {topic}\n"
                f"Jautājums: {user_msg}.{context_bits}"
            )
        else:
            prompt_user = user_msg

        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        # Minimāla vēsture — mazāks prompt = ātrāka prefills
        for m in history[-2:]:
            if m["content"] == user_msg and m["role"] == "user":
                continue
            content = m["content"]
            if len(content) > 400:
                content = content[:400] + "…"
            messages.append({"role": m["role"], "content": content})
        messages.append({"role": "user", "content": prompt_user})

        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.models.complete_messages(
                    role=role,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=max_tokens,
                    frequency_penalty=0.45,
                    presence_penalty=0.25,
                    repeat_penalty=1.18,
                    stop=["\nTu:", "\nUser:", "\nuser:", "\nMain Brain:"],
                    timeout_sec=_CHAT_LLM_BUDGET_SEC,
                ),
                timeout=_CHAT_LLM_BUDGET_SEC + 2.0,
            )
        except asyncio.TimeoutError:
            if local_hits:
                return "\n".join(local_hits[:3]) + "\n\n(Modelis bija pārāk lēns — rādu lokālo kontekstu.)"
            return (
                "Modelis neatbildēja laikā (CPU pārāk noslogots). "
                "Aizver smagas programmas un mēģini vēlreiz, vai UPGRADE_MODEL.bat (ātrāks Q4)."
            )

        reply = ""
        if result.get("ok") and (result.get("text") or "").strip():
            reply = _clean_reply(str(result["text"]))
        else:
            err = str(result.get("error") or "Lokālais modelis nav pieejams")
            if local_hits:
                return "\n".join(local_hits[:3]) + f"\n\n(Modelis: {err})"
            return (
                f"{err} "
                "Ja atbildes ir vājas — UPGRADE_MODEL.bat (3B/7B Q4)."
            )

        elapsed = time.monotonic() - t0
        # Otrais LLM mēģinājums TIKAI ja vēl ir budžets — citādi UI timeout
        if _is_junk(reply) and elapsed < _CHAT_RETRY_BUDGET_SEC:
            remain = max(12.0, _CHAT_LLM_BUDGET_SEC - elapsed - 2.0)
            try:
                retry = await asyncio.wait_for(
                    self.models.complete_messages(
                        role=role,
                        messages=[
                            {
                                "role": "system",
                                "content": "Atbildi latviešu valodā skaidri un īsākām. Ja nezini — «Nezinu.»",
                            },
                            {"role": "user", "content": prompt_user},
                        ],
                        temperature=0.05,
                        max_tokens=min(120, max_tokens),
                        frequency_penalty=0.7,
                        repeat_penalty=1.3,
                        timeout_sec=remain,
                    ),
                    timeout=remain + 1.0,
                )
            except asyncio.TimeoutError:
                retry = {"ok": False}
            if retry.get("ok") and (retry.get("text") or "").strip():
                reply = _clean_reply(str(retry["text"]))
            if _is_junk(reply):
                if local_hits:
                    return "\n".join(local_hits[:4])
                return (
                    f"Nezinu drošu atbildi par «{topic}». "
                    "Mēģini vēlreiz vai UPGRADE_MODEL.bat (3B/7B) labākai saprašanai."
                )
        elif _is_junk(reply):
            if local_hits:
                return "\n".join(local_hits[:4])
            return (
                f"Modelis iedeva neskaidru atbildi par «{topic}». "
                "Mēģini vēlreiz īsāku jautājumu."
            )

        if intent in {Intent.SEARCH, Intent.PERSON} and local_hits:
            reply = f"[Avoti: {len(local_hits)}]\n{reply}"

        return reply

    @staticmethod
    def _looks_like_question(text: str) -> bool:
        t = (text or "").strip()
        if "?" in t:
            return True
        return bool(
            re.search(
                r"(?i)^\s*(kas|kā|kur|kad|kāpēc|cik|vai|who|what|where|when|why|how|which)\b",
                t,
            )
        )

    @staticmethod
    def _meta_about_self(user_msg: str) -> str | None:
        """Godīgas atbildes par mācīšanos / Ollama — bez LLM."""
        t = (user_msg or "").strip()
        if not t:
            return None
        about_learn = bool(
            re.search(
                r"(?i)\b(mācies|mācās|mācīties|mācīšan|iemācies|pati?\s+māc|self[- ]?learn|"
                r"learn(s|ing)?\s+(by\s+itself|alone|automatically)|vai\s+tu\s+māc)\b",
                t,
            )
        )
        about_ollama = bool(re.search(r"(?i)\bollama\b", t))
        about_model = bool(
            re.search(r"(?i)\b(gguf|llama\.?cpp|kāds\s+model|kurš\s+model|qwen)\b", t)
        )
        if not (about_learn or about_ollama or about_model):
            return None
        parts: list[str] = []
        # Parastam lietotājam — cilvēciski, bez tehniskā žargona
        if about_learn:
            parts.append(
                "Jā — es mācos no mūsu sarunām. "
                "Labās atbildes saglabāju atmiņā un nākamreiz tās izmantoju. "
                "Ja gribi, lai es īpaši iegaumēju tēmu, saki: «iemācies …»."
            )
            # Tehniskās detaļas tikai ja jautā par modeli/GGUF/Ollama
            if about_model or about_ollama:
                parts.append(
                    "(Tehniski: atmiņa ir lokāla zināšanu bāze, ne modeļa svaru pārtrenēšana.)"
                )
        if about_ollama and not about_model:
            parts.append(
                "Ollama netiek izmantota. Strādāju ar lokālo modeli datorā (llama-server)."
            )
        elif about_model and not about_learn:
            parts.append(
                "Strādāju ar lokālo Qwen modeli datorā (llama-server). Ollama ir izslēgta."
            )
        elif about_ollama and about_model and not about_learn:
            parts.append(
                "Ollama netiek kustināta. Primārais ir lokālais llama-server + modelis datorā."
            )
        return " ".join(parts)

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

            # Īss timeout — meklēšana nedrīkst apēst visu chat budžetu
            payload = await asyncio.wait_for(web_search(query, max_results=4), timeout=12.0)
            text = format_search_for_llm(payload)
            if not payload.get("ok") and not payload.get("results"):
                return []
            return [text]
        except asyncio.TimeoutError:
            return []
        except Exception as exc:  # noqa: BLE001
            return [f"(Interneta meklēšana neizdevās: {exc})"]

    def _remember(self, topic: str, reply: str, *, kind: str = "chat") -> bool:
        """Nepārtraukta mācīšanās: labas atbildes → lokālā zināšanu bāze (ne Ollama, ne GGUF fine-tune)."""
        store = getattr(self.brain, "store", None)
        if store is None:
            return False
        summary = reply.split("\n\n[Iemācīts]")[0].split("\n\n〔atmiņa〕")[0].strip()[:800]
        if _is_junk(summary) or len(summary) < 24:
            return False
        topic_key = (topic or "").strip()[:120] or "saruna"
        # Neindexē meta/atkārtotus dublikātus ar to pašu sākumu
        try:
            existing = store.search_knowledge(topic_key, limit=3)
            for row in existing or []:
                prev = str(row.get("content") or "")
                if summary[:80].lower() in prev.lower():
                    return False
        except Exception:  # noqa: BLE001
            pass
        try:
            store.index_knowledge(
                f"{topic_key}\n{summary}",
                source=f"{kind}:{topic_key[:80]}",
                verified=False,
                metadata={"kind": kind, "topic": topic_key, "at": utc_now().isoformat()},
            )
            # Metrika — redzams /learning/metrics
            learning = getattr(self.brain, "learning", None)
            if learning is not None:
                try:
                    learning.record_outcome("ChatMemory", success=True, duration_ms=0)
                except Exception:  # noqa: BLE001
                    pass
            return True
        except Exception:  # noqa: BLE001
            return False

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
        paths: list[str] = []
        if arts:
            for a in arts[:8]:
                p = getattr(a, "path", None) or (a.get("path") if isinstance(a, dict) else None)
                if p:
                    paths.append(str(p))
            if paths:
                parts.append("Faili:\n- " + "\n- ".join(paths))
                for p in paths:
                    if p.endswith((".py", ".md", ".txt", ".cs")):
                        try:
                            text = Path(p).read_text(encoding="utf-8")[:600]
                            parts.append(f"--- {Path(p).name} ---\n{text}")
                        except OSError:
                            pass
                        break

        # FIZISKI atver izveidoto failu (Notepad / noklusējuma programma)
        open_path = paths[0] if paths else None
        actor = self._actor()
        if actor is not None and open_path:
            try:
                if open_path.endswith((".py", ".txt", ".md", ".cs", ".json")):
                    actor.launch_app("notepad", [open_path])
                else:
                    actor.open_path(open_path)
                parts.append(f"Atvēru failu: {open_path}")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"(Neizdevās atvērt failu: {exc})")

        summary = "\n".join(parts)
        # Mācās no izpildes — nākamreiz zinās, ko darīja
        self._remember(goal[:120], summary, kind="execute")
        if "iemāc" in goal.lower() or "learn" in goal.lower():
            parts.append("[Iemācīts] Saglabāju arī šo izpildi zināšanu bāzē.")
            summary = "\n".join(parts)
        return self._finish(
            session,
            history,
            summary,
            mode="execute",
            goal_status=status,
            ui_action="open_path" if open_path else "none",
            open_path=open_path,
            focus="editor" if open_path else "home",
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
