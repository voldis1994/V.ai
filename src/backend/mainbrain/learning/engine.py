from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainbrain.contracts.schemas import LearningMetric
from mainbrain.core.ids import utc_now
from mainbrain.memory.store import MemoryStore


class LearningEngine:
    """Izmērīta aģentu izvēles optimizācija + neobligāta LoRA eksporta sagatavošana."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def record_outcome(
        self,
        agent_id: str,
        *,
        success: bool,
        duration_ms: int,
        retries: int = 0,
        test_passed: bool | None = None,
        manual_approval: bool = False,
        resource_usage: dict[str, float] | None = None,
    ) -> LearningMetric:
        existing = self.store.get_json("agent_metrics", agent_id)
        if existing:
            metric = LearningMetric.model_validate(existing)
        else:
            metric = LearningMetric(agent_id=agent_id)
        n = metric.samples
        metric.samples = n + 1
        metric.success_rate = ((metric.success_rate * n) + (1.0 if success else 0.0)) / (n + 1)
        metric.avg_duration_ms = ((metric.avg_duration_ms * n) + duration_ms) / (n + 1)
        metric.retry_count += retries
        if test_passed is not None:
            # vienkāršota testa proporcija
            prev_pass = metric.test_pass_rate * n
            metric.test_pass_rate = (prev_pass + (1.0 if test_passed else 0.0)) / (n + 1)
        if manual_approval:
            metric.manual_approvals += 1
        if resource_usage:
            metric.resource_usage = resource_usage
        metric.updated_at = utc_now()
        self.store.upsert_metric(metric)
        return metric

    def rank_agents(self, candidate_ids: list[str]) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        for agent_id in candidate_ids:
            raw = self.store.get_json("agent_metrics", agent_id)
            if not raw:
                scored.append((agent_id, 0.5))
                continue
            metric = LearningMetric.model_validate(raw)
            # panākumi + testa kvalitāte − atkārtojumi
            score = (
                0.6 * metric.success_rate
                + 0.3 * metric.test_pass_rate
                - 0.01 * metric.retry_count
            )
            scored.append((agent_id, max(0.0, min(1.0, score))))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def export_training_dataset(
        self,
        samples: list[dict[str, Any]],
        target: Path,
        *,
        approved: bool,
    ) -> dict[str, Any]:
        if not approved:
            return {"ok": False, "error": "Nepieciešama lietotāja atļauja"}
        target.parent.mkdir(parents=True, exist_ok=True)
        cleaned = []
        for sample in samples:
            text = json.dumps(sample, ensure_ascii=False)
            # vienkārša sensitīvo lauku attīrīšana
            if any(k in text.lower() for k in ("password", "api_key", "secret_token")):
                continue
            cleaned.append(sample)
        target.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "dataset_path": str(target),
            "redacted_count": len(samples) - len(cleaned),
            "count": len(cleaned),
            "lora_status": "Nav pieejams — nepieciešams saderīgs modelis, licence, aparatūra un bibliotēkas",
        }

    def training_prerequisites(self) -> dict[str, Any]:
        return {
            "status": "Nav pieejams",
            "requires": [
                "Saderīgs bāzes modelis ar apmācības licenci",
                "GPU/VRAM vai pietiekama RAM",
                "LoRA/QLoRA bibliotēkas (piem., peft/transformers)",
                "Lietotāja apstiprināti anonimizēti paraugi",
            ],
        }
