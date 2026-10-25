from __future__ import annotations

import re
from typing import Any

from mainbrain.contracts.schemas import ChatMessage, ChatRequest, ChatResponse, ModelRole, RunGoalRequest
from mainbrain.models.router import ModelRouter


SYSTEM_PROMPT = """Tu esi Main Brain — lokāls Windows AI asistents latviešu valodā.
Tu esi gudrs, draudzīgs un praktisks. Atbildi skaidri un īsi, bet ar saturu.
Tu vari brīvi sarunāties (jautājumi, skaidrojumi, plānošana).
Ja lietotājs skaidri lūdz KAUT KO IZPILDĪT datorā (izveidot failus, rakstīt kodu projektā, palaist programmas, labot kļūdas),
atbildē īsi apstiprini un norādi, ka sāksi izpildi — sistēma tad palaidīs aģentu orķestrāciju.
Nekad neizliecies, ka esi palaidis kodu, ja tas vēl nav noticis.
Ja lokālais modelis nav pieejams, godīgi to saki.
"""

# Strong action verbs / patterns → escalate to full brain
_ACTION_RE = re.compile(
    r"(?i)\b("
    r"izveido|izveidot|uzraksti|uzrakstīt|izlabo|labot|palaid|palaist|"
    r"instalē|instalēt|kompilē|build|deploy|dzēs|izdzēs|"
    r"pārbaudi\s+test|uzraksti\s+kod|izveido\s+fail|"
    r"open\s+notepad|atver\s+notepad|atver\s+pārlūk"
    r")\b"
)


def wants_execution(text: str, force_execute: bool | None = None) -> bool:
    if force_execute is True:
        return True
    if force_execute is False:
        return False
    t = (text or "").strip()
    if t.lower().startswith(("izpildi:", "izpildīt:", "dari:", "run:", "/run")):
        return True
    # Short greetings / questions → chat only
    if len(t) < 8:
        return False
    if t.endswith("?") and not _ACTION_RE.search(t):
        return False
    return bool(_ACTION_RE.search(t))


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
        history.append({"role": "user", "content": req.message})
        # keep last N turns
        if len(history) > 40:
            del history[:-40]

        execute = wants_execution(req.message, req.force_execute)
        if execute:
            # Brief ack via LLM if possible, then run orchestrator
            ack = await self.models.complete(
                role=ModelRole.REASONING,
                prompt=req.message,
                system=(
                    SYSTEM_PROMPT
                    + "\nLietotājs lūdz IZPILDI. Atbildi 1–3 teikumos latviešu valodā: "
                    "apstiprini, ko darīsi, un ka sāc orķestrāciju."
                ),
                temperature=0.3,
                max_tokens=256,
            )
            ack_text = (ack.get("text") or "").strip()
            if not ack.get("ok") or not ack_text:
                ack_text = "Sapratu — sāku izpildi ar aģentiem."

            goal = req.message
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

        # Pure conversation
        messages_for_prompt = "\n".join(f"{m['role']}: {m['content']}" for m in history[-12:])
        result = await self.models.complete(
            role=ModelRole.REASONING,
            prompt=messages_for_prompt + "\nassistant:",
            system=SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=800,
        )
        if result.get("ok") and (result.get("text") or "").strip():
            reply = result["text"].strip()
        else:
            err = result.get("error") or "Lokālais modelis nav pieejams."
            reply = (
                f"Esmu gatavs sarunai, bet AI modelis pašlaik neatbild.\n"
                f"({err})\n"
                "Pārbaudiet llama-server (http://127.0.0.1:8080) un GGUF modeļus. "
                "Tikmēr varat rakstīt uzdevumus ar 'Izpildi: ...' — aģenti joprojām var strādāt bez LLM plāna."
            )
        history.append({"role": "assistant", "content": reply})
        return ChatResponse(
            reply=reply,
            mode="chat",
            session_id=session,
            messages=[ChatMessage(**m) for m in history[-12:]],
        )
