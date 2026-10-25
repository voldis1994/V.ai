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

# Īss budžets — darbības (pārlūks/faili) NEDRĪKST gaidīt lēno LLM / Ollama
_CHAT_LLM_BUDGET_SEC = 22.0
_CHAT_RETRY_BUDGET_SEC = 0.0  # bez otrā LLM mēģinājuma — ātrums > perfekcija


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
                "Sveiki! Esmu Main Brain — brīvs lokāls AI datorā (bez Ollama). "
                "Saki «sameklē …», «uztaisi …» vai «atver …» — daru uzreiz. Ko darām?",
            )

        if intent == Intent.MATH:
            math_reply = self._try_math(user_msg)
            if math_reply:
                return self._finish(session, history, math_reply)

        # Meta TIKAI jautājumiem «vai tu mācies?» — NE komandai «iemācies X»
        if intent not in {Intent.LEARN, Intent.BUILD, Intent.SEARCH, Intent.PERSON, Intent.EXPLAIN}:
            meta = self._meta_about_self(user_msg)
            if meta:
                return self._finish(session, history, meta, user_msg=user_msg)

        # Valodu īsie FAQ — tikai skaidri jautājumi par valodām (ne «izrunā valodu»)
        if re.search(r"(?i)\b(kād[aā]s?\s+valod|which\s+language|scottish|scotland|skotij)", user_msg):
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
            return self._finish(session, history, reply, user_msg=user_msg)

        topic = extract_topic(user_msg)

        # «iemācies» bez tēmas — pajautā, KO iegaumēt (nevis atkārto meta frāzi)
        if intent == Intent.LEARN and (not topic or topic.lower().strip() in {"iemācies", "learn", "iemāci"}):
            ask = (
                "Labi — ko tieši iegaumēt? Piemēram: «iemācies kas ir Python» "
                "vai «iemācies Edgars Gaidulis». Es sameklēšu, saglabāšu failā un atmiņā."
            )
            return self._finish(session, history, ask, user_msg=user_msg)

        # BRĪVAIS REŽĪMS: jautājumi / personas / meklēšana / skaidrojumi / iemācies
        # → pārlūks + fakti + SAGLABĀ fails. NEgaidām Ollama.
        if intent in {Intent.PERSON, Intent.SEARCH, Intent.EXPLAIN, Intent.LEARN} or (
            intent == Intent.CHAT and self._looks_like_question(user_msg)
        ):
            return await self._search_and_act(
                req,
                session,
                history,
                user_msg,
                topic,
                intent,
                learn=intent == Intent.LEARN,
            )

        # Īss chat bez jautājuma — mēģina LLM ātri; ja lēns/nav — skaidra norāde
        local_hits = self._search_local_knowledge(topic) or self._search_local_knowledge(user_msg)
        reply = await self._llm_task(
            intent=Intent.CHAT,
            user_msg=user_msg,
            topic=topic,
            history=history,
            local_hits=local_hits,
        )
        if _is_junk(reply):
            if local_hits:
                reply = "\n".join(local_hits[:3])
            else:
                reply = (
                    "Labāk tā (es daru UZREIZ, bez Ollama):\n"
                    "• «sameklē …» — atveru pārlūku + pastāstu\n"
                    "• «uztaisi …» — izveidoju failu/programmu\n"
                    "• «atver chrome / notepad» — fiziski atveru"
                )
        if reply and not _is_junk(reply):
            self._remember(topic or user_msg, reply, kind="chat")
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

        # Audio TIKAI ja lietotājs to prasa («pasaki», «skaļi» …) — ne pēc katras darbības
        speak: str | None = None
        if self._wants_voice(user_msg or ""):
            speak = (speak_text or reply).split("\n\n[Darbība]")[0].split("\n\n[Iemācīts]")[0].strip()
            if len(speak) > 800:
                speak = speak[:800] + "…"

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

    @staticmethod
    def _wants_voice(text: str) -> bool:
        return bool(
            re.search(
                r"(?i)\b(pasaki|pasaki\s+skaļi|runā|runāt|speak|audio|skaļi|izrunā|balsī|voice)\b",
                text or "",
            )
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
                speak_text="Kameras rīki nav pieejami. Palaid install sense skriptu.",
                user_msg=user_msg,
            )
        from mainbrain.contracts.schemas import ToolRequest

        vision = None
        faces = None
        vout: dict[str, Any] = {}
        fout: dict[str, Any] = {}
        # Mēģina 0. un 1. kameru (USB / iebūvēta)
        for idx in (0, 1):
            vision = tools.execute(
                ToolRequest(
                    tool="vision.analyze",
                    arguments={"camera_index": idx},
                    agent_id="ChatService",
                )
            )
            vout = vision.output if isinstance(vision.output, dict) else {}
            if vision.ok:
                faces = tools.execute(
                    ToolRequest(
                        tool="face.detect",
                        arguments={
                            "camera_index": idx,
                            "path": vout.get("path"),
                        },
                        agent_id="ChatService",
                    )
                )
                fout = faces.output if isinstance(faces.output, dict) else {}
                break

        if vision is None or (not vision.ok and (faces is None or not faces.ok)):
            err = vout.get("error") or fout.get("error") or (vision.error if vision else None)
            msg = (
                f"Kamera/analīze neizdevās: {err}. "
                "Pārbaudi, vai kamera nav aizņemta citā programmā, "
                "un palaid scripts\\install_sense.ps1"
            )
            return self._finish(
                session,
                history,
                msg,
                speak_text="Kamera nestrādā. Pārbaudi atļaujas un OpenCV instalāciju.",
                user_msg=user_msg,
            )
        face_n = int(fout.get("face_count") or 0)
        notes = str(vout.get("notes") or "").strip()
        path = fout.get("annotated_path") or vout.get("path") or fout.get("path")
        if face_n > 0:
            spoken = f"Es redzu {face_n} sejas. {notes}".strip()
        else:
            spoken = f"Kamerā sejas neredzu. {notes or 'Kadrs saglabāts.'}".strip()
        reply = (
            f"{spoken}\n"
            f"Kadrs: {path or '—'}.\n"
            "Ja gribi programmu: «izveido sejas atpazīšanas programmu»."
        )
        return self._finish(
            session,
            history,
            reply,
            mode="act",
            ui_action="open_path",
            open_path=path,
            focus="live",
            speak_text=spoken,
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
        *,
        learn: bool = False,
    ) -> ChatResponse:
        """UZREIZ: fakti + saglabā. Desktop PiP jau rāda DDG — NEBLOĶĒJAM ar bridge."""
        q = (topic if topic else user_msg).strip() or user_msg
        # PERSON: meklē pēc vārda, nevis visas frāzes ar «sameklē»
        search_q = q if intent == Intent.PERSON else (topic or user_msg).strip() or user_msg
        if intent == Intent.PERSON and not q:
            search_q = user_msg

        url = duckduckgo_url(search_q)
        actor = self._actor()
        # NEIZSAUCAM browser.navigate caur pipe — tas deadlock'oja Desktop (gaida /chat).
        # PiP jau iestatīts no BeginVisibleAction. Sistēmas pārlūku var palaist fona pavedienā.
        opened: dict[str, Any] = {"url": url, "pip": "desktop"}
        if actor is not None:
            try:
                # Tikāi start "" url — bez bridge, bez gaidīšanas
                opened = actor.open_url(url, via_bridge=False)
                opened["url"] = url
            except Exception as exc:  # noqa: BLE001
                opened = {"url": url, "error": str(exc)}

        local_hits = self._search_local_knowledge(q) or self._search_local_knowledge(search_q)
        web_hits: list[str] = []
        wiki_bits: list[str] = []
        if self._internet_enabled():
            try:
                gathered = await asyncio.wait_for(
                    asyncio.gather(
                        self._search_web(search_q),
                        self._search_wikipedia(search_q),
                        return_exceptions=True,
                    ),
                    timeout=8.0,
                )
                wh, wi = gathered
                web_hits = wh if isinstance(wh, list) else []
                wiki_bits = wi if isinstance(wi, list) else []
            except Exception:  # noqa: BLE001
                web_hits, wiki_bits = [], []

        facts = [h for h in (wiki_bits + web_hits + local_hits) if h and not str(h).startswith("(")]
        spoken = self._facts_to_reply(q or search_q, facts)
        if not spoken:
            spoken = (
                f"Par «{q or search_q}» sameklēju internetā. "
                "Mazajā lodziņā bija DuckDuckGo rezultāti (piem. LinkedIn u.c.). "
                "Pilnu kopsavilkumu no avotiem šoreiz neizdevās salikt — bet meklēšana notika."
            )

        # Saglabā .md BEZ Notepad gaidīšanas (Desktop var atvērt pēc atbildes)
        saved_path = self._persist_findings(
            topic=q or search_q,
            spoken=spoken,
            facts=facts,
            url=url,
            learn=learn,
            actor=actor,
        )

        act_parts = [f"[Darbība] Meklēšana → {url}"]
        if isinstance(opened, dict) and opened.get("error"):
            act_parts.append(f"({opened.get('error')})")
        if saved_path:
            act_parts.append(f"Saglabāju failā: {saved_path}")
        if learn:
            self._remember(q or search_q, spoken, kind="learn")
            act_parts.append("[Iemācīts] Saglabāju arī atmiņā.")
        else:
            self._remember(q or search_q, spoken, kind="search")

        reply = spoken + "\n\n" + "\n".join(act_parts)
        return self._finish(
            session,
            history,
            reply,
            mode="act",
            ui_action="open_path" if saved_path else "open_browser",
            open_url=url,
            open_path=saved_path,
            focus="editor" if saved_path else "browser",
            speak_text=spoken,
            user_msg=user_msg,
        )

    def _persist_findings(
        self,
        *,
        topic: str,
        spoken: str,
        facts: list[str],
        url: str,
        learn: bool,
        actor: PhysicalActor | None,
    ) -> str | None:
        """Raksta atrastos faktus Documents/MainBrainOS/knowledge/*.md — bez Notepad bloķēšanas."""
        try:
            docs = Path.home() / "Documents" / "MainBrainOS" / "knowledge"
            docs.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^\wāčēģīķļņšūž\-]+", "_", (topic or "tema").strip(), flags=re.UNICODE)
            slug = (slug[:60] or "tema").strip("_") or "tema"
            path = docs / f"{slug}.md"
            kind = "IEMĀCĪTS" if learn else "MEKLĒŠANA"
            body_lines = [
                f"# {topic}",
                "",
                f"> {kind} · Main Brain · {utc_now().isoformat(timespec='seconds')}",
                "",
                "## Kopsavilkums",
                spoken,
                "",
                "## Avoti / fakti",
            ]
            for i, f in enumerate(facts[:8], 1):
                body_lines.append(f"{i}. {str(f).strip()[:800]}")
            body_lines.extend(["", "## Meklēšana", url, ""])
            content = "\n".join(body_lines)
            if actor is not None:
                result = actor.write_text_file(path, content)
                if result.get("write_ok"):
                    return str(path)
            path.write_text(content, encoding="utf-8")
            return str(path)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _facts_to_reply(topic: str, facts: list[str]) -> str:
        """Saviem vārdiem — ko atrada, nevis sausi linki."""
        if not facts:
            return ""
        cleaned: list[str] = []
        for f in facts[:4]:
            chunk = str(f).strip()
            # Noņem «Avots:» rindas no runājamā teksta (URL paliek žurnālā)
            chunk = re.sub(r"(?im)^\s*Avots:\s*\S+\s*$", "", chunk).strip()
            chunk = re.sub(r"\s+", " ", chunk)
            if len(chunk) > 380:
                chunk = chunk[:380].rsplit(" ", 1)[0] + "…"
            if chunk and chunk not in cleaned:
                cleaned.append(chunk)
        if not cleaned:
            return ""
        if len(cleaned) == 1:
            return f"Par «{topic}» atrada: {cleaned[0]}"
        body = " ".join(f"{i}) {c}" for i, c in enumerate(cleaned, 1))
        return f"Par «{topic}» atrada šādi. {body}"

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
        """Tikai JAUTĀJUMI par sevi — ne komanda «iemācies X» (to dara LEARN ceļš)."""
        t = (user_msg or "").strip()
        if not t:
            return None
        # Komanda «iemācies …» / «learn …» ar tēmu — NAV meta
        if re.match(r"(?i)^\s*(iemācies|iemāci|iemācīties|learn|teach)\b.+", t):
            return None
        if re.match(r"(?i)^\s*(iemācies|iemāci|learn)\s*$", t):
            return None

        about_learn = bool(
            re.search(
                r"(?i)("
                r"vai\s+tu\s+(pati?\s+)?māc|kā\s+tu\s+māc|vai\s+mācies|"
                r"pati?\s+māc|self[- ]?learn|"
                r"learn(s|ing)?\s+(by\s+itself|alone|automatically)|"
                r"do\s+you\s+learn|can\s+you\s+learn"
                r")",
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
        if about_learn:
            parts.append(
                "Jā — es mācos no mūsu sarunām: labās atbildes lieku atmiņā. "
                "Lai iegaumētu konkrētu tēmu UZREIZ, saki «iemācies …» — "
                "tad sameklēšu internetā, saglabāšu failā un atmiņā."
            )
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
        goal = req.message.strip()
        for prefix in ("izpildi:", "izpildīt:", "dari:", "run:", "/run"):
            if goal.lower().startswith(prefix):
                goal = goal[len(prefix) :].strip()
                break

        # Ātrais ceļš: vienkāršs Python / teksta fails — UZREIZ raksta + atver (redzams)
        quick = self._quick_build(goal, req.workspace_path)
        if quick is not None:
            reply, path, spoken = quick
            self._remember(goal[:120], reply, kind="execute")
            return self._finish(
                session,
                history,
                reply,
                mode="execute",
                goal_status="completed",
                ui_action="open_path",
                open_path=path,
                focus="editor",
                speak_text=spoken,
                user_msg=req.message,
            )

        ack_text = "Sapratu — sāku taisīt. Tagad rakstu failus un atvēršu tos, lai redzi ko daru."
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

        open_path = paths[0] if paths else None
        actor = self._actor()
        if actor is not None and open_path:
            try:
                # Preferē VS Code, ja ir; citādi Notepad — lietotājs REDZ darbu
                opened_with = actor.open_in_best_editor(open_path)
                parts.append(f"Atvēru ar {opened_with}: {open_path}")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"(Neizdevās atvērt failu: {exc})")

        summary = "\n".join(parts)
        self._remember(goal[:120], summary, kind="execute")
        if "iemāc" in goal.lower() or "learn" in goal.lower():
            parts.append("[Iemācīts] Saglabāju arī šo izpildi zināšanu bāzē.")
            summary = "\n".join(parts)
        spoken = f"Uzdevums {status}. " + (
            f"Izveidoju {Path(open_path).name}." if open_path else "Skaties rezultātu."
        )
        return self._finish(
            session,
            history,
            summary,
            mode="execute",
            goal_status=status,
            ui_action="open_path" if open_path else "none",
            open_path=open_path,
            focus="editor" if open_path else "home",
            speak_text=spoken,
            user_msg=req.message,
        )

    def _quick_build(
        self, goal: str, workspace_path: str | None
    ) -> tuple[str, str, str] | None:
        """Vienkārši «uzraksti python / hello / skriptu» — uzreiz fails + redaktors."""
        g = (goal or "").lower()
        wants_py = bool(
            re.search(r"(?i)\b(python|\.py|skript|script|hello\s*world|programma)\b", goal)
        )
        if not wants_py:
            return None
        # Lieli «sistēma / sejas» — atstāj aģentiem
        if re.search(r"(?i)\b(seja|face|sistēm|os\b|windows\s+app|pilnu?\s+projekt)", g):
            return None

        root = Path(workspace_path) if workspace_path else Path.home() / "Documents" / "MainBrainOS" / "projects"
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            root = Path.cwd()

        named = re.search(r"(?i)\b([\w\-]+)\.py\b", goal)
        if "hello" in g:
            fname = "hello.py"
            code = 'print("Hello, World!")\n'
        elif named:
            fname = named.group(1) + ".py"
            code = (
                f'"""{goal.strip()[:120]}"""\n\n'
                f"def main() -> None:\n"
                f'    print("OK: {fname}")\n\n'
                f'if __name__ == "__main__":\n'
                f"    main()\n"
            )
        else:
            fname = "script.py"
            code = (
                f'"""Auto: {goal.strip()[:100]}"""\n\n'
                f"def main() -> None:\n"
                f'    print("Main Brain skripts darbojas")\n\n'
                f'if __name__ == "__main__":\n'
                f"    main()\n"
            )

        path = root / fname
        actor = self._actor()
        steps = [
            f"1) Veidoju mapi: {root}",
            f"2) Rakstu failu: {path}",
            f"3) Saturs:\n```\n{code}```",
        ]
        try:
            if actor is not None:
                actor.create_and_open_text(path, code, open_with="auto")
                steps.append("4) Atvēru redaktorā (VS Code / Notepad) — skaties logu.")
            else:
                path.write_text(code, encoding="utf-8")
                steps.append("4) Fails saglabāts (redaktoru nevarēju atvērt).")
        except Exception as exc:  # noqa: BLE001
            try:
                path.write_text(code, encoding="utf-8")
            except OSError:
                return None
            steps.append(f"4) Fails saglabāts; atvēršana: {exc}")

        reply = "Taisu Python skriptu — lūk, ko daru:\n" + "\n".join(steps)
        spoken = f"Izveidoju failu {fname} un atvēru to redaktorā."
        return reply, str(path), spoken

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
