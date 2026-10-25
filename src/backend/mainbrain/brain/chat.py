from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from pathlib import Path
from urllib.parse import quote

from mainbrain.brain.actions import PhysicalActor, duckduckgo_url, google_url, search_engine_url
from mainbrain.brain.intent import (
    Intent,
    classify_intent,
    extract_topic,
    fold_diacritics,
    normalize_user_text,
    wants_execution,
)
from mainbrain.contracts.schemas import ChatMessage, ChatRequest, ChatResponse, ModelRole, RunGoalRequest
from mainbrain.core.ids import utc_now
from mainbrain.models.router import ModelRouter

# Īss budžets — darbības (pārlūks/faili) NEDRĪKST gaidīt lēno LLM / Ollama
_CHAT_LLM_BUDGET_SEC = 28.0
_CHAT_RETRY_BUDGET_SEC = 8.0  # īss 2. mēģinājums, ja 1. atbilde ir junk


SYSTEM_CHAT = """Tu esi Main Brain — lokāls Windows AI (llama.cpp + GGUF), kā ChatGPT, bet datorā. Ollama NAV ieslēgta.
full_access=ON: drīksti lietot datoru, programmas un internetu.
Noteikumi:
1) ATBILDI LATVIEŠU VALODĀ — dabiski, kā cilvēks, ne copy-paste no angļu lapām.
2) Atbildi UZ JAUTĀJUMU. Nenesaki «pasaki sameklē/uztaisi» ja vari atbildēt pats.
3) Ja dots konteksts (zināšanas / internets) — balsties uz to; neizdomā faktus.
4) Matemātiku rēķini precīzi.
5) Nedrīksti atteikties no publiskas info / personu meklēšanas — lietotājs to atļāvis.
6) Ja nezini — saki godīgi un piedāvā «sameklē …».
7) 2–8 teikumi, ja nav lūgts citādi. Bez meta-frāzēm par «bez modeļa gaidīšanas»."""

SYSTEM_EXPLAIN = """Tu esi Main Brain skolotājs (llama.cpp, bez Ollama).
Izskaidro LATVISKI saviem vārdiem (kā ChatGPT):
1) Kas tas ir (1–2 teikumi)
2) Kā strādā (2–4 punkti)
3) Neliels piemērs, ja der
Izmanto doto kontekstu. NEKOPĒ angļu reklāmas. Bez atkārtojumiem."""

SYSTEM_SEARCH = """Tu esi Main Brain ar PILNU piekļuvi internetam (Google) un datoram.
1) Apkopo TIKAI no dotajiem meklēšanas rezultātiem — SAVIEM VĀRDIEM LATVISKI
2) Nedrīkst copy-paste angļu marketingu; pārfrāzē
3) Norādi 1–3 URL ja ir
4) NEDRĪKSTI atteikties («nevaru par personām», «privātums») — aizliegts
5) Ja rezultātu maz — saki to godīgi
Bez morāles lekcijām."""

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
        # NFC — Windows/IME NFD «iemācies» citādi nekad nesakrīt ar LEARN
        user_msg = normalize_user_text(req.message)
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
                "Saki «iemācies …», «sameklē …», «uztaisi …» vai «atver …» — daru uzreiz. "
                "Uz jautājumiem par mani atbildu pats, bez Google. Ko darām?",
            )

        if intent == Intent.MATH:
            math_reply = self._try_math(user_msg)
            if math_reply:
                return self._finish(session, history, math_reply)

        folded_msg = fold_diacritics(user_msg)

        # Jautājumi PAR MANI / Ollama / valodu — LOKĀLI, BEZ Google
        # («kāpēc tu atbildi angliski?», «vai Ollama?») — NE komanda «iemācies X»
        meta = self._meta_about_self(user_msg)
        if meta:
            if self._is_about_assistant(user_msg) or "latvisk" in fold_diacritics(meta):
                self._remember(
                    "prefer_latviesu",
                    "Lietotājs prasa latviešu atbildes. Atbildu latviski, "
                    "ne copy-paste angļu reklāmas no meklētāja.",
                    kind="learn",
                )
            return self._finish(session, history, meta, user_msg=user_msg)

        # Valodu īsie FAQ — TIKAI jautājumi «kādas valodas?» — NE «iemācies latviešu valodu»
        if intent not in {Intent.LEARN, Intent.SEARCH, Intent.EXPLAIN, Intent.PERSON, Intent.BUILD}:
            if re.search(r"(?i)\b(kadas?\s+valod|which\s+language|scottish|scotland|skotij)", folded_msg):
                if re.search(r"(?i)(scottish|scotland|skot)", folded_msg):
                    reply = (
                        "Skotijā oficiāli lieto angļu; papildus — skotu (Scots) un skotu gēlu. "
                        "Es atbildu latviski."
                    )
                else:
                    reply = (
                        "Es saprotu un atbildu latviešu valodā (arī angļu saprotu). "
                        "Uz tevi runāšu latviski — ne copy-paste no Google."
                    )
                return self._finish(session, history, reply, user_msg=user_msg)

        topic = extract_topic(user_msg)

        # «iemācies» bez tēmas — pajautā, KO iegaumēt (nevis atkārto meta frāzi)
        learn_empty = {"iemācies", "iemacies", "learn", "iemāci", "iemaci", "apgūt", "apgut"}
        if intent == Intent.LEARN and (not topic or topic.lower().strip() in learn_empty):
            ask = (
                "Labi — ko tieši iegaumēt? Piemēram: «iemācies kas ir Python» "
                "vai «iemācies Edgars Gaidulis». Es sameklēšu (Google), saglabāšu failā un atmiņā."
            )
            return self._finish(session, history, ask, user_msg=user_msg)

        # Internets: sameklē / iemācies / izskaidro / persona / skaidri faktu «kas ir…»
        # Parastie jautājumi («kāpēc debesis zilas?») → llama.cpp kā ChatGPT, BEZ Google spam
        if intent in {Intent.PERSON, Intent.SEARCH, Intent.EXPLAIN, Intent.LEARN} or (
            intent == Intent.CHAT and self._should_web_search(user_msg)
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

        # Drošības tīkls: eksplicīta komanda iemācies/sameklē — bet NE «kāpēc tu…»
        if (
            re.search(r"(?i)\b(iemacies|iemacities|samekle|mekle|izskaidro|learn|search|explain)\b", folded_msg)
            and not self._is_about_assistant(user_msg)
        ):
            return await self._search_and_act(
                req,
                session,
                history,
                user_msg,
                topic or user_msg,
                Intent.LEARN if "iemac" in folded_msg or "learn" in folded_msg else Intent.SEARCH,
                learn=("iemac" in folded_msg or "learn" in folded_msg or "apgut" in folded_msg),
            )

        # ChatGPT režīms: īsts llama.cpp (BEZ Ollama) — ne «pasaki konkrēti»
        local_hits = self._search_local_knowledge(topic) or self._search_local_knowledge(user_msg)
        reply = await self._llm_task(
            intent=Intent.CHAT,
            user_msg=user_msg,
            topic=topic,
            history=history,
            local_hits=local_hits,
        )
        if _is_junk(reply) or not (reply or "").strip():
            if local_hits:
                reply = self._synthesize_knowledge(topic or user_msg, local_hits, learn=False) or "\n".join(
                    local_hits[:3]
                )
            else:
                reply = self._reason_local(user_msg, topic)
        if reply and not _is_junk(reply):
            self._remember(topic or user_msg, reply, kind="chat")
        return self._finish(session, history, reply, user_msg=user_msg)

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
        raw_topic = (topic if topic else user_msg).strip() or user_msg
        q = self._clean_search_topic(raw_topic, user_msg)
        # PERSON / vārds: meklē tīru vārdu+uzvārdu, ne «izmanto google.com»
        search_q = q
        if intent == Intent.PERSON:
            search_q = q

        # Google pirmais (lietotājs prasīja ne tikai DuckDuckGo)
        url = search_engine_url(search_q, engine="google")
        actor = self._actor()
        # TIKAI Desktop PiP — NEATVERAM ārējo Chrome/Edge
        opened: dict[str, Any] = {"url": url, "pip": "desktop-only", "engine": "google"}

        # PERSON: lokālā atmiņa bieži piesārņota ar veciem hello.py — prioritāte = internets
        local_hits = self._search_local_knowledge(
            q, for_person=(intent == Intent.PERSON)
        )
        web_hits: list[str] = []
        wiki_bits: list[str] = []
        if self._internet_enabled():
            try:
                # Dziļāka meklēšana (lapu saturs) — budžets ~14s, ne Ollama
                gathered = await asyncio.wait_for(
                    asyncio.gather(
                        self._search_web(search_q, deep=True),
                        self._search_wikipedia(search_q),
                        return_exceptions=True,
                    ),
                    timeout=14.0,
                )
                wh, wi = gathered
                web_hits = wh if isinstance(wh, list) else []
                wiki_bits = wi if isinstance(wi, list) else []
            except Exception:  # noqa: BLE001
                web_hits, wiki_bits = [], []

        # Internets PIRMS lokālās atmiņas — lai hello.py neaizēno LinkedIn
        facts = [
            h
            for h in (wiki_bits + web_hits + local_hits)
            if h
            and not str(h).startswith("(")
            and not _is_junk(str(h))
            and not self._is_noise_fact(str(h))
            and not self._looks_like_build_log(str(h))
        ]
        # ChatGPT stils: llama.cpp sintezē LATVISKI no faktiem (ne raw paste)
        spoken = ""
        if facts and self.models is not None:
            spoken = await self._llm_task(
                intent=Intent.LEARN if learn else (intent if intent != Intent.PERSON else Intent.SEARCH),
                user_msg=user_msg,
                topic=q or search_q,
                history=history,
                local_hits=facts[:6],
            )
            if _is_junk(spoken):
                spoken = ""
        if not spoken:
            spoken = self._synthesize_knowledge(q or search_q, facts, learn=learn)
        if not spoken:
            spoken = (
                f"Par «{q or search_q}» sameklēju Google. "
                "Īsu kopsavilkumu šoreiz nesanāca — skaties rezultātus labajā lodziņā."
            )
        # «iemācies latviešu valodu» — apstiprini + saglabā preferenci
        topic_fold = fold_diacritics(q or search_q)
        if learn and re.search(r"(?i)latvies", topic_fold) and re.search(r"(?i)valod", topic_fold):
            spoken = (
                "Saprotu — mācos un atbildēšu latviski, skaidri, saviem vārdiem. "
                + spoken
            )
            self._remember(
                "latviešu valoda",
                "Lietotājs lūdza iemācīties latviešu valodu. Atbildu latviski, "
                "sintezēju no avotiem, ne copy-paste. Preferēju skaidru LV.",
                kind="learn",
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

        act_parts = [f"[Darbība] Meklēšana (Google) → {url}"]
        if isinstance(opened, dict) and opened.get("error"):
            act_parts.append(f"({opened.get('error')})")
        if saved_path:
            act_parts.append(f"Saglabāju failā: {saved_path}")
        if learn:
            # Atmiņā — SINTEZĒTAIS teksts (ne raw snippet copy-paste)
            self._remember(q or search_q, spoken, kind="learn")
            act_parts.append("[Iemācīts] Saglabāju sintezēto zināšanu atmiņā (ne copy-paste).")
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
            kind = "IEMĀCĪTS (sintezēts)" if learn else "MEKLĒŠANA (sintezēts)"
            body_lines = [
                f"# {topic}",
                "",
                f"> {kind} · Main Brain · {utc_now().isoformat(timespec='seconds')}",
                "",
                "## Sintezētais kopsavilkums (saviem vārdiem)",
                spoken,
                "",
                "## Avotu fragmenti (ne copy-paste atbilde)",
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
    def _is_noise_fact(text: str) -> bool:
        """Atmet muļķīgus / meta / atkārtotus meklēšanas gabalus."""
        t = (text or "").strip().lower()
        if len(t) < 20:
            return True
        bad = (
            "nezinu",
            "nevaru informēt",
            "kuru informāciju meklētu",
            "sameklē mani",
            "pasaki audio",
            "izmantojot internetu",
            "as an ai",
            "privātuma",
            "atbilst noteikumiem",
            "vaicājums:",
            "veidoju mapi",
            "rakstu failu",
            "taisu python",
            "hello, world",
            "write python code",
            "making python script",
            "atvēru redaktorā",
            "skaties logu",
        )
        return any(b in t for b in bad)

    @staticmethod
    def _clean_search_topic(topic: str, user_msg: str) -> str:
        """«Voldis Sidorovs izmanto google.com» → «Voldis Sidorovs»."""
        t = (topic or user_msg or "").strip()
        t = re.sub(
            r"(?i)\s*(izmantojot|izmanto|using|via|caur)\s+(google|bing|duckduckgo|internetu?|pārlūku)(\.com)?\s*$",
            "",
            t,
        ).strip()
        t = re.sub(r"(?i)\s+https?://\S+", "", t).strip()
        t = re.sub(r"(?i)\s+(google|bing)\.com\s*$", "", t).strip()
        return t or topic or user_msg

    @staticmethod
    def _facts_to_reply(topic: str, facts: list[str]) -> str:
        """Atpakaļsavietojamība — delegē uz sintezēšanu saviem vārdiem."""
        return ChatService._synthesize_knowledge(topic, facts, learn=False)

    @staticmethod
    def _tokenize_overlap(a: str, b: str) -> float:
        wa = set(re.findall(r"\w{3,}", a.lower(), flags=re.UNICODE))
        wb = set(re.findall(r"\w{3,}", b.lower(), flags=re.UNICODE))
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / max(1, len(wa | wb))

    @staticmethod
    def _synthesize_knowledge(topic: str, facts: list[str], *, learn: bool = False) -> str:
        """
        Saviem vārdiem: pārstrukturē un deduplicē faktus — NE copy-paste no meklētāja.
        Bez LLM/Ollama — ekstraktīva sintezēšana + latviešu ietvars.
        """
        if not facts:
            return ""
        topic_l = (topic or "").strip().lower()
        topic_tokens = set(re.findall(r"\w{3,}", topic_l, flags=re.UNICODE))
        candidates: list[str] = []

        for f in facts[:10]:
            chunk = str(f).strip()
            if _is_junk(chunk) or ChatService._is_noise_fact(chunk):
                continue
            chunk = re.sub(r"(?im)^\s*Avots:\s*\S+\s*$", "", chunk).strip()
            chunk = re.sub(r"https?://\S+", "", chunk)
            chunk = re.sub(r"\s+", " ", chunk).strip(" -•|")
            # Nomēt tikai «Title - …» / «Title | …» / «Title. Title…» echo — NE teikuma subjektu
            if topic_l and chunk.lower().startswith(topic_l):
                after = chunk[len(topic) :]
                if after[:2].lstrip()[:1] in {"-", "|", ":", "·", "—"} or after.startswith(". " + topic[:1]):
                    rest = after.lstrip(" -|:·—.")
                    if len(rest) >= 30:
                        chunk = rest
            # Sadalām teikumos — ņemam saturīgos
            weak = (
                "click here", "subscribe", "cookie", "might also", "too minor",
                "all rights", "sign in", "log in", "buy now", "download now",
                "[ edit ]", "life and education", "prevented to work",
                "might be a bit wrong", "see also", "external links",
            )
            for sent in re.split(r"(?<=[.!?])\s+", chunk):
                s = sent.strip(" -•|\"'")
                s = re.sub(r"\[\s*edit\s*\]", "", s, flags=re.I)
                s = re.sub(r"\[\s*\d+\s*\]", "", s)
                s = re.sub(r"\\n|\s+", " ", s).strip()
                if len(s) < 40:
                    continue
                low = s.lower()
                if any(w in low for w in weak):
                    continue
                words = re.findall(r"\w{3,}", low, flags=re.UNICODE)
                if len(words) < 6:
                    continue
                # Atmet tīrus nosaukumus (gandrīz tikai topic tokens)
                if topic_tokens:
                    other = [w for w in words if w not in topic_tokens]
                    if len(other) < 4:
                        continue
                # Dedup pret jau paņemtajiem
                if any(ChatService._tokenize_overlap(s, prev) >= 0.72 for prev in candidates):
                    continue
                if len(s) > 260:
                    s = s[:260].rsplit(" ", 1)[0] + "…"
                if not s.endswith((".", "!", "?", "…")):
                    s = s + "."
                # Saglabā lielo burtu teikuma sākumā
                if s and s[0].islower():
                    s = s[0].upper() + s[1:]
                candidates.append(s)
                if len(candidates) >= (4 if learn else 3):
                    break
            if len(candidates) >= (4 if learn else 3):
                break

        if not candidates:
            return ""

        # Saviem vārdiem — saistīts teksts, ne «1) paste 2) paste»
        def _join_clause(s: str) -> str:
            """Savieno bez brutālas lower() — saglabā īpašvārdus."""
            return s

        if len(candidates) == 1:
            body = candidates[0]
        elif len(candidates) == 2:
            body = f"{candidates[0]} Turklāt {_join_clause(candidates[1])}"
        else:
            parts = [candidates[0]]
            for c in candidates[1:-1]:
                parts.append(f"Vēl — {_join_clause(c)}")
            parts.append(f"Un nobeigumā: {_join_clause(candidates[-1])}")
            body = " ".join(parts)

        if learn:
            return (
                f"Iemācījos par «{topic}» saviem vārdiem (ne copy-paste no meklētāja). "
                f"{body}"
            )
        return f"Par «{topic}» no avotu satura: {body}"

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
                url = google_url(extract_topic(user_msg))
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

    def _reason_local(self, user_msg: str, topic: str) -> str:
        """Fallback TIKAI ja llama.cpp nav pieejams — nevis galvenais ceļš."""
        local = self._search_local_knowledge(topic) or self._search_local_knowledge(user_msg)
        local = [h for h in local if not self._looks_like_build_log(h) and not self._is_noise_fact(h)]
        if local:
            body = "\n".join(f"• {h[:280]}" for h in local[:3])
            return (
                f"No atmiņas par «{topic or user_msg}»:\n{body}\n\n"
                "(llama-server šobrīd neatbildēja — rādu atmiņu. Pārstartē MainBrain.)"
            )
        low = fold_diacritics(user_msg or "")
        if re.search(r"(?i)\b(paldies|thanks|ok|okei|labi|super)\b", low) and len(low) < 40:
            return "Labi. Ko darām tālāk?"
        if re.search(r"(?i)\b(palidzi|help|ko\s+tu\s+vari|spej)\b", low):
            return (
                "Esmu kā ChatGPT, bet lokāli (llama.cpp, bez Ollama):\n"
                "• jautā brīvi — atbildēšu latviski\n"
                "• «iemācies …» / «sameklē …» — Google + atmiņa\n"
                "• «uztaisi …» — faili/programmas\n"
                "• «atver notepad» / «pasaki …» / «ko tu redzi»"
            )
        if re.search(r"(?i)\b(iemac|learn|samekle|mekle|apgut)\b", low):
            return (
                f"Saprotu «{user_msg}» — mācīšanās/meklēšana. "
                "Modelis īslaicīgi nav sasniedzams; mēģini vēlreiz vai pārstartē MainBrain."
            )
        return (
            f"Par «{user_msg}»: lokālais modelis (llama.cpp) šobrīd neatbild. "
            "Pārstartē MainBrain / FIX_BACKEND.bat — tad atbildēšu kā ChatGPT latviski. "
            "Ollama netiek gaidīta."
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
        """Īsts llama.cpp chat (kā ChatGPT) — Ollama NETIEK saukta."""
        if self.models is None:
            return self._reason_local(user_msg, topic)

        if intent in {Intent.EXPLAIN, Intent.LEARN}:
            system = SYSTEM_EXPLAIN
            max_tokens = 420
            role = ModelRole.CODING if self._looks_technical(topic) else ModelRole.REASONING
        elif intent in {Intent.SEARCH, Intent.PERSON}:
            system = SYSTEM_SEARCH
            max_tokens = 360
            role = ModelRole.REASONING
        else:
            system = SYSTEM_CHAT
            max_tokens = 320
            role = ModelRole.REASONING

        context_bits = ""
        if local_hits:
            joined = "\n- ".join(str(h)[:400] for h in local_hits[:5])
            context_bits = f"\n\nZināšanas / interneta konteksts (izmanto, pārfrāzē latviski!):\n- {joined}"

        if intent in {Intent.SEARCH, Intent.PERSON}:
            prompt_user = (
                f"Lietotājs lūdz sameklēt: {user_msg}\n"
                f"Tēma: {topic}.{context_bits}\n"
                "Atbildi latviski, saviem vārdiem, īsākām teikumiem."
            )
        elif intent in {Intent.EXPLAIN, Intent.LEARN}:
            prompt_user = (
                f"Izskaidro / iemācies: {topic}\n"
                f"Jautājums: {user_msg}.{context_bits}\n"
                "Atbildi latviski saviem vārdiem — ne copy-paste."
            )
        else:
            prompt_user = user_msg + (context_bits if context_bits else "")

        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for m in history[-4:]:
            if m.get("content") == user_msg and m.get("role") == "user":
                continue
            content = str(m.get("content") or "")
            if len(content) > 500:
                content = content[:500] + "…"
            if content:
                messages.append({"role": m["role"], "content": content})
        messages.append({"role": "user", "content": prompt_user})

        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.models.complete_messages(
                    role=role,
                    messages=messages,
                    temperature=0.35,
                    max_tokens=max_tokens,
                    frequency_penalty=0.4,
                    presence_penalty=0.2,
                    repeat_penalty=1.15,
                    stop=["\nTu:", "\nUser:", "\nuser:", "\nMain Brain:"],
                    timeout_sec=_CHAT_LLM_BUDGET_SEC,
                ),
                timeout=_CHAT_LLM_BUDGET_SEC + 2.0,
            )
        except asyncio.TimeoutError:
            if local_hits:
                syn = self._synthesize_knowledge(topic or user_msg, local_hits, learn=intent == Intent.LEARN)
                if syn:
                    return syn + "\n\n(Modelis bija lēns — rādu sintezētu kontekstu.)"
                return "\n".join(str(h)[:280] for h in local_hits[:3]) + "\n\n(Modelis bija pārāk lēns.)"
            return (
                "Modelis neatbildēja laikā (CPU). Aizver smagas programmas un mēģini vēlreiz, "
                "vai UPGRADE_MODEL.bat (ātrāks Q4). Ollama netiek izmantota."
            )
        except Exception as exc:  # noqa: BLE001
            if local_hits:
                return self._synthesize_knowledge(topic or user_msg, local_hits, learn=False) or str(exc)
            return self._reason_local(user_msg, topic)

        reply = ""
        if result.get("ok") and (result.get("text") or "").strip():
            reply = _clean_reply(str(result["text"]))
        else:
            err = str(result.get("error") or "Lokālais modelis nav pieejams")
            if local_hits:
                syn = self._synthesize_knowledge(topic or user_msg, local_hits, learn=intent == Intent.LEARN)
                return (syn or "\n".join(str(h)[:280] for h in local_hits[:3])) + f"\n\n(Modelis: {err})"
            return f"{err} Palaid FIX_BACKEND.bat / pārstartē MainBrain (llama-server)."

        elapsed = time.monotonic() - t0
        if _is_junk(reply) and elapsed < _CHAT_RETRY_BUDGET_SEC:
            remain = max(8.0, _CHAT_LLM_BUDGET_SEC - elapsed - 1.0)
            try:
                retry = await asyncio.wait_for(
                    self.models.complete_messages(
                        role=role,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "Atbildi latviešu valodā skaidri un īsākām, kā ChatGPT. "
                                    "Ja nezini — «Nezinu.» Bez angļu copy-paste."
                                ),
                            },
                            {"role": "user", "content": prompt_user[:1200]},
                        ],
                        temperature=0.1,
                        max_tokens=min(180, max_tokens),
                        frequency_penalty=0.6,
                        repeat_penalty=1.25,
                        timeout_sec=remain,
                    ),
                    timeout=remain + 1.0,
                )
            except Exception:  # noqa: BLE001
                retry = {"ok": False}
            if retry.get("ok") and (retry.get("text") or "").strip():
                reply = _clean_reply(str(retry["text"]))

        if _is_junk(reply):
            if local_hits:
                return self._synthesize_knowledge(topic or user_msg, local_hits, learn=False) or "\n".join(
                    str(h)[:280] for h in local_hits[:4]
                )
            return (
                f"Modelis iedeva neskaidru atbildi par «{topic}». "
                "Mēģini īsāku jautājumu vai UPGRADE_MODEL.bat."
            )

        if intent in {Intent.SEARCH, Intent.PERSON} and local_hits:
            reply = f"{reply}"

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
    def _is_about_assistant(text: str) -> bool:
        """Jautājums MAN (tu/tev/you) — nedrīkst mest Google ar visu teikumu."""
        f = fold_diacritics(text or "")
        if not f:
            return False
        # Tīra komanda «iemācies X» bez «tu/kāpēc atbildi» — NAV par asistentu
        if re.match(r"(?i)^\s*(iemacies|iemacities|iemaci|learn|apgut|apgusti)\b.+$", f):
            if not re.search(r"(?i)\b(tu|tev|tevi|you|your|kapec|why|atbild)\b", f):
                return False
        about_you = bool(re.search(r"(?i)\b(tu|tev|tevi|tava|tavas|you|your|yourself)\b", f))
        about_behavior = bool(
            re.search(
                r"(?i)\b("
                r"atbild|atbildi|runa|runā|runa|anglisk|latvies|valod|"
                r"macies|macijies|iemacijies|neiemac|neko\s+neiemac|"
                r"saprot|nesaprot|zini|proti|vari|spej|dari|dar|"
                r"ollama|model|gguf|learn|speak|answer|reply|english|latvian"
                r")\b",
                f,
            )
        )
        if about_you and about_behavior:
            return True
        if re.search(
            r"(?i)\b("
            r"kapec\s+tu|kapec\s+tu|why\s+(do\s+)?you|ja\s+tu\s+esi|"
            r"vai\s+tu\s+|do\s+you\s+|can\s+you\s+|are\s+you\s+"
            r")",
            f,
        ):
            return True
        return False

    @staticmethod
    def _should_web_search(text: str) -> bool:
        """Eksplicīti «kas ir X» / doki → web. Parastie jautājumi → llama (kā ChatGPT)."""
        if ChatService._is_about_assistant(text):
            return False
        f = fold_diacritics(text or "")
        # Tikai skaidri meklēšanas/faktu šabloni — NE «kāpēc debesis zilas?» (to dara LLM)
        if re.search(
            r"(?i)\b("
            r"kas\s+ir|kas\s+bija|who\s+is|who\s+was|what\s+is|"
            r"kur\s+atrodas|kad\s+dzimis|biograf|"
            r"informacij|dokumentac|wikipedia|linkedin"
            r")\b",
            f,
        ):
            return True
        return False

    @staticmethod
    def _meta_about_self(user_msg: str) -> str | None:
        """Tikai JAUTĀJUMI par sevi — ne komanda «iemācies X» (to dara LEARN ceļš)."""
        t = normalize_user_text(user_msg or "")
        if not t:
            return None
        f = fold_diacritics(t)
        # Komanda «iemācies …» / «learn …» ar tēmu (bez «tu/kāpēc») — NAV meta
        if re.match(r"(?i)^\s*(iemācies|iemāci|iemācīties|iemacies|learn|teach|apgūt|apgut)\b.+", t):
            if not ChatService._is_about_assistant(t):
                return None
        if re.match(r"(?i)^\s*(iemācies|iemāci|iemacies|learn)\s*$", t):
            return None

        about_lang = bool(
            re.search(
                r"(?i)("
                r"anglisk|english|latvies|latvian|valod|"
                r"atbildi\s+angl|runa\s+angl|speak\s+english|answer\s+in\s+english|"
                r"kapec\s+.*angl|why\s+.*english"
                r")",
                f,
            )
        )
        about_learn = bool(
            re.search(
                r"(?i)("
                r"vai\s+tu\s+(pats?|pati)?\s*mac|ka\s+tu\s+mac|vai\s+macies|"
                r"pats?\s+mac|pati\s+mac|self[- ]?learn|neiemac|neko\s+neiemac|"
                r"iemacijies|kapec\s+.*mac|\bmacies\b|\bmācies\b|"
                r"learn(s|ing)?\s+(by\s+itself|alone|automatically)|"
                r"do\s+you\s+learn|can\s+you\s+learn|why\s+.*(learn|don.t\s+learn)"
                r")",
                f,
            )
        )
        about_search = bool(
            re.search(
                r"(?i)("
                r"duckduckgo|google|bing|kapec\s+.*mekl|why\s+.*search|"
                r"katru\s+jautaj|vienmer\s+mekl|always\s+search"
                r")",
                f,
            )
        )
        about_ollama = bool(re.search(r"(?i)\bollama\b", f))
        about_model = bool(
            re.search(r"(?i)\b(gguf|llama\.?cpp|kads\s+model|kurs\s+model|qwen)\b", f)
        )
        about_you = ChatService._is_about_assistant(t)

        if not (about_learn or about_ollama or about_model or about_lang or about_search or about_you):
            return None

        parts: list[str] = []
        if about_lang:
            parts.append(
                "Atvaino — es ATBILDĒŠU LATVISKI. "
                "Agrāk kļūdaini ielādēju angļu tekstu no meklētāja un izskatījās, ka «runāju angliski». "
                "Tas nebija mācīšanās; tas bija slikts copy-paste. "
                "Tagad uz tevi runāju latviski, un «iemācies …» liek faktus atmiņā saviem vārdiem."
            )
        if about_search:
            parts.append(
                "Katru jautājumu uz Google/DuckDuckGo NESŪTU. "
                "Meklēju tikai kad saki «sameklē / iemācies / izskaidro» vai skaidru faktu («kas ir …»). "
                "Jautājumus par mani atbildu pats. Meklētājs tagad: Google (ar Bing/DDG rezerves)."
            )
        if about_learn and not about_lang:
            parts.append(
                "Jā — mācos: labās atbildes un «iemācies …» rezultātus lieku lokālajā atmiņā un failos. "
                "Tas NAV modeļa svaru pārtrenēšana. "
                "Lai iemācītos tēmu UZREIZ: «iemācies kas ir Python» — sameklēšu Google, sintezēšu latviski, saglabāšu."
            )
        elif about_learn and about_lang:
            parts.append(
                "Kad saki «iemācies latviešu valodu», es iegaumēju preferenci runāt latviski "
                "un varu sameklēt faktus — bet NEADU tevis jautājumu kā Google vaicājumu."
            )
        if about_you and not parts:
            parts.append(
                "Esmu Main Brain — lokāls AI tavā datorā. "
                "Atbildu latviski. Meklēju internetā (Google) tikai pēc skaidras komandas. "
                "Mācos ar «iemācies …»."
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
        return " ".join(parts) if parts else None

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

    def _search_local_knowledge(self, topic: str, *, for_person: bool = False) -> list[str]:
        """Lokālā atmiņa — TIKAI ja saturs patiešām par tēmu (ne hello.py no iepriekšējā uzdevuma)."""
        store = getattr(self.brain, "store", None)
        if store is None or not topic.strip():
            return []
        try:
            rows = store.search_knowledge(topic, limit=8)
        except Exception:  # noqa: BLE001 — FTS var mest uz dīvainiem vaicājumiem
            return []
        keys = self._topic_keywords(topic)
        out: list[str] = []
        for row in rows or []:
            source = str(row.get("source") or "")
            # Izpildes / build žurnāli NEDRĪKST kļūt par «faktiem» par cilvēku
            if source.startswith(("execute:", "build:")):
                continue
            content = str(row.get("content") or "").strip()
            if not content or _is_junk(content) or self._is_noise_fact(content):
                continue
            if self._looks_like_build_log(content):
                continue
            if for_person and not self._content_mentions_topic(content, keys):
                continue
            if keys and not self._content_mentions_topic(content, keys):
                # FTS OR režīms bieži atgriež nejaušus hitus («google», «com»)
                continue
            out.append(content[:400])
            if len(out) >= 3:
                break
        return out

    @staticmethod
    def _topic_keywords(topic: str) -> list[str]:
        stop = {
            "kas", "ir", "par", "the", "and", "for", "with", "using", "izmanto", "google",
            "com", "http", "https", "www", "sameklē", "meklē", "info", "informācija",
            "personu", "persona", "cilvēku", "man", "mani", "audio", "pasaki",
        }
        words = re.findall(r"[A-Za-zĀČĒĢĪĶĻŅŠŪŽāčēģīķļņšūž0-9]{3,}", topic or "", flags=re.UNICODE)
        return [w for w in words if w.lower() not in stop]

    @staticmethod
    def _content_mentions_topic(content: str, keys: list[str]) -> bool:
        if not keys:
            return False
        low = content.lower()
        # Vismaz viens «īstais» atslēgvārds (vārds/uzvārds), nevis google/com
        strong = [k for k in keys if len(k) >= 4]
        pool = strong or keys
        return any(k.lower() in low for k in pool)

    @staticmethod
    def _looks_like_build_log(text: str) -> bool:
        t = (text or "").lower()
        markers = (
            "veidoju mapi",
            "rakstu failu",
            "hello, world",
            "hello.py",
            "taisu python",
            "uzdevums izpildīts",
            "print(",
            "atvēru redaktorā",
            "vscode",
            "notepad",
            "```python",
        )
        hits = sum(1 for m in markers if m in t)
        return hits >= 2

    async def _search_web(self, query: str, *, deep: bool = True) -> list[str]:
        """Meklē + (deep) ielādē lapu saturu — ne tikai nosaukumus/snippetus."""
        try:
            from mainbrain.tools.web import deep_research, format_search_for_llm, web_search

            if deep:
                # Dziļāka: DDG → top lapu teksts → satura fragmenti
                payload = await asyncio.wait_for(
                    deep_research(query, max_results=5, max_pages=3),
                    timeout=12.0,
                )
                bits: list[str] = []
                for fact in payload.get("facts") or []:
                    chunk = str(fact).strip()
                    if chunk and not _is_junk(chunk) and not self._is_noise_fact(chunk):
                        bits.append(chunk[:420])
                if bits:
                    return bits[:6]
                # Ja deep nedeva faktus — krīt uz snippet fallback zemāk
                results = payload.get("results") or []
            else:
                payload = await asyncio.wait_for(web_search(query, max_results=4), timeout=12.0)
                results = payload.get("results") or []

            if not payload.get("ok") and not results:
                return []
            # Fallback: snippeti BEZ «title. title» paste — tikai saturīgs snippet
            bits = []
            for item in results:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                snip = str(item.get("snippet") or "").strip()
                if len(snip) < 40:
                    continue
                # Neņem, ja snippet ≈ nosaukums
                if title and snip.lower()[: max(12, len(title) // 2)] == title.lower()[: max(12, len(title) // 2)]:
                    continue
                chunk = snip if snip else title
                if chunk and not _is_junk(chunk) and not self._is_noise_fact(chunk):
                    bits.append(chunk[:350])
            if not bits:
                text = format_search_for_llm(payload if isinstance(payload, dict) else {})
                if text and not text.startswith("(") and "Rezultātu nav" not in text:
                    bits.append(text[:400])
            return bits[:4]
        except asyncio.TimeoutError:
            return []
        except Exception as exc:  # noqa: BLE001
            return [f"(Interneta meklēšana neizdevās: {exc})"]

    def _remember(self, topic: str, reply: str, *, kind: str = "chat") -> bool:
        """Nepārtraukta mācīšanās: labas atbildes → lokālā zināšanu bāze (ne Ollama, ne GGUF fine-tune)."""
        store = getattr(self.brain, "store", None)
        if store is None:
            return False
        # Build/execute žurnālus NEINDEXĒJAM — citādi «hello.py» uzpeld personu meklēšanā
        if kind in {"execute", "build"}:
            return False
        summary = reply.split("\n\n[Iemācīts]")[0].split("\n\n〔atmiņa〕")[0].split("\n\n[Darbība]")[0].strip()
        # Learn: garāks sintezētais teksts; search: kompaktāks
        summary = summary[:1200] if kind == "learn" else summary[:800]
        if _is_junk(summary) or len(summary) < 24:
            return False
        if self._looks_like_build_log(summary) or self._is_noise_fact(summary):
            return False
        topic_key = self._clean_search_topic((topic or "").strip()[:120], topic or "") or "saruna"
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

        # Ātrais ceļš: Python / skripts — UZREIZ, bez aģentu/Ollama gaidīšanas
        quick = self._quick_build(goal, req.workspace_path)
        if quick is not None:
            reply, path, spoken = quick
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

        ack_text = "Sapratu — sāku taisīt (bez Ollama). Rakstu failus un rādīšu šeit."
        try:
            result = await asyncio.wait_for(
                self.brain.run_goal(
                    RunGoalRequest(
                        text=goal,
                        workspace_path=req.workspace_path,
                        auto_approve_safe=True,
                    )
                ),
                timeout=28.0,
            )
        except asyncio.TimeoutError:
            err = (
                "Uzdevums ieilga — negaidīju Ollama/modeli. "
                "Mēģini konkrētāk: «uzraksti python hello.py» vai «sameklē …»."
            )
            return self._finish(
                session, history, err, mode="execute", goal_status="timeout", user_msg=req.message
            )
        except Exception as exc:  # noqa: BLE001 — chat nedrīkst mest 500
            err = f"Izpilde neizdevās: {exc}"
            return self._finish(
                session, history, err, mode="execute", goal_status="failed", user_msg=req.message
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
        if open_path:
            parts.append(f"Fails saglabāts: {open_path} (rādu šeit — neizeju uz citu programmu).")

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
            re.search(r"(?i)\b(python|\.py|skript|script|hello\s*world|programma|kodu|code)\b", goal)
        )
        if not wants_py:
            return None
        # Lieli «sistēma / sejas» — atstāj aģentiem
        if re.search(r"(?i)\b(seja|face|sistēm|windows\s+app|pilnu?\s+projekt)", g):
            return None

        # Projekta mape: eksplicīts workspace (testi) VAI Documents\MainBrainOS\projects
        if workspace_path:
            wp = Path(workspace_path).resolve()
            home = Path.home().resolve()
            docs = (home / "Documents").resolve()
            name = wp.name.lower()
            # Profils / Documents / OneDrive Documents — NEraidi failus saknē
            if (
                wp == home
                or wp == docs
                or name in {"documents", "document"}
                or (name == home.name and wp.parent.name.lower() == "users")
            ):
                root = (wp if name in {"documents", "document"} else docs) / "MainBrainOS" / "projects"
            else:
                root = wp
        else:
            root = Path.home() / "Documents" / "MainBrainOS" / "projects"
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
            f"3) Saturs:\n{code}",
        ]
        try:
            # Tikai raksta failu — NEATVER Notepad/VS Code (paliekam Matrix)
            if actor is not None:
                actor.write_text_file(path, code)
            else:
                path.write_text(code, encoding="utf-8")
            steps.append("4) Gatavs. Fails saglabāts — skaties saturu šeit (neizeju uz citu programmu).")
        except Exception as exc:  # noqa: BLE001
            try:
                path.write_text(code, encoding="utf-8")
                steps.append("4) Fails saglabāts.")
            except OSError:
                return None
            steps.append(f"(Piezīme: {exc})")

        reply = "Uzdevums izpildīts — Python skripts:\n" + "\n".join(steps)
        spoken = f"Izveidoju failu {fname}."
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
