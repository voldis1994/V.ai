from __future__ import annotations

import re
from typing import Any

from mainbrain.contracts.schemas import ChatMessage, ChatRequest, ChatResponse, ModelRole, RunGoalRequest
from mainbrain.models.router import ModelRouter


SYSTEM_PROMPT = (
    "Tu esi Main Brain — lokāls Windows AI asistents. "
    "Atbildi latviešu valodā, īsi un precīzi uz lietotāja jautājumu. "
    "Nekad neatkārto vienu un to pašu frāzi. "
    "Nedod šabloniskas frāzes tipa «izveidojiet savu jautājumu». "
    "Ja nezini — saki godīgi. "
    "Ja lietotājs lūdz izpildīt darbu datorā (izveidot failu, kodu, palaist programmu), "
    "īsi apstiprini un saki, ka sāc izpildi."
)

_ACTION_RE = re.compile(
    r"(?i)\b("
    r"izveido|izveidot|uzraksti|uzrakstīt|izlabo|labot|palaid|palaist|"
    r"instalē|instalēt|kompilē|build|deploy|dzēs|izdzēs|"
    r"pārbaudi\s+test|uzraksti\s+kod|izveido\s+fail|"
    r"open\s+notepad|atver\s+notepad|atver\s+pārlūk"
    r")\b"
)

_BAD_REPLY = re.compile(
    r"(?i)(izveidojiet\s+savu\s+jautājumu|apstiprinām\s+jūsu\s+risinājumu|"
    r"lūdzu,\s*izveidojiet|riks,\s*ka\s*tev\s*ir)"
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


def _clean_reply(text: str) -> str:
    t = (text or "").strip()
    # often models echo "assistant:" prefixes
    for prefix in ("assistant:", "Assistant:", "ASSISTANT:"):
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
    # cut runaway repetition (same paragraph twice)
    parts = [p.strip() for p in re.split(r"\n{2,}", t) if p.strip()]
    if len(parts) >= 2 and parts[0] == parts[1]:
        t = parts[0]
    return t.strip()


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
        history.append({"role": "user", "content": req.message.strip()})
        if len(history) > 24:
            del history[:-24]

        execute = wants_execution(req.message, req.force_execute)
        if execute:
            return await self._execute(req, session, history)

        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history[-10:])

        result = await self.models.complete_messages(
            role=ModelRole.REASONING,
            messages=messages,
            temperature=0.35,
            max_tokens=512,
        )

        if result.get("ok") and (result.get("text") or "").strip():
            reply = _clean_reply(str(result["text"]))
            # junk / template → one retry with stricter system + only last user turn
            if not reply or _BAD_REPLY.search(reply) or len(reply) < 2:
                retry = await self.models.complete_messages(
                    role=ModelRole.REASONING,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Atbildi latviešu valodā uz lietotāja jautājumu vienā īsa teikumā. "
                                "Bez sveicieniem un bez šabloniem."
                            ),
                        },
                        {"role": "user", "content": req.message.strip()},
                    ],
                    temperature=0.1,
                    max_tokens=256,
                )
                if retry.get("ok") and (retry.get("text") or "").strip():
                    reply = _clean_reply(str(retry["text"]))
                if not reply or _BAD_REPLY.search(reply):
                    reply = self._offline_fact_reply(req.message.strip())
        else:
            err = result.get("error") or "Lokālais modelis nav pieejams."
            reply = f"Modelis neatbild ({err}). Pārbaudiet llama-server."

        history.append({"role": "assistant", "content": reply})
        return ChatResponse(
            reply=reply,
            mode="chat",
            session_id=session,
            messages=[ChatMessage(**m) for m in history[-12:]],
        )

    async def _execute(
        self,
        req: ChatRequest,
        session: str,
        history: list[dict[str, str]],
    ) -> ChatResponse:
        ack = await self.models.complete_messages(
            role=ModelRole.REASONING,
            messages=[
                {
                    "role": "system",
                    "content": "Lietotājs lūdz izpildi. 1–2 teikumi latviešu valodā: ko darīsi.",
                },
                {"role": "user", "content": req.message.strip()},
            ],
            temperature=0.2,
            max_tokens=128,
        )
        ack_text = _clean_reply(str(ack.get("text") or ""))
        if not ack.get("ok") or not ack_text or _BAD_REPLY.search(ack_text):
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
            messages=[ChatMessage(**m) for m in history[-12:]],
        )

    @staticmethod
    def _offline_fact_reply(message: str) -> str:
        """Minimal local fallback if the small GGUF returns junk."""
        m = message.lower().strip()
        math = re.fullmatch(r"cik\s+(ir\s+)?(\d+)\s*\+\s*(\d+)\s*\??", m)
        if math:
            a, b = int(math.group(2)), int(math.group(3))
            return f"{a} + {b} = {a + b}"
        if m in {"sveiks", "sveiki", "labdien", "hello", "hi"}:
            return "Sveiki! Kā varu palīdzēt?"
        return (
            "Modelis šobrīd dod neskaidru atbildi. "
            "Mēģiniet vienkāršāku jautājumu vai lielāku GGUF (standard profils)."
        )
