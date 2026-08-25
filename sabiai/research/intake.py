from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .evidence import Evidence, EvidenceStore


ALLOWED_RELIABILITY = {
    "official",
    "primary",
    "high",
    "strong",
    "medium",
    "fair",
    "low",
    "weak",
    "poor",
    "unverified",
    "unknown",
}


@dataclass(frozen=True, slots=True)
class EvidencePacketItem:
    id: str
    evidence_type: str
    summary: str
    subject: str | None
    source_name: str
    source_url: str | None
    observed_at: str | None
    freshness_seconds: int | None
    reliability: str
    raw: dict | list | None

    def as_evidence(self, *, event_id: str | None = None, sport_id: str | None = None) -> Evidence:
        return Evidence(
            id=self.id,
            event_id=event_id,
            sport_id=sport_id,
            evidence_type=self.evidence_type,
            subject=self.subject,
            summary=self.summary,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=self.observed_at,
            freshness_seconds=self.freshness_seconds,
            reliability=self.reliability,
            raw=self.raw,
        )

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "evidence_type": self.evidence_type,
            "subject": self.subject,
            "summary": self.summary,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "observed_at": self.observed_at,
            "freshness_seconds": self.freshness_seconds,
            "reliability": self.reliability,
            "raw": self.raw,
        }


@dataclass(frozen=True, slots=True)
class EvidencePacketResult:
    items: tuple[EvidencePacketItem, ...]
    rejected: tuple[dict, ...]
    persisted_ids: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return bool(self.items) and not self.rejected


class EvidencePacketService:
    """Normalize a browser/search/subagent evidence packet before Sabi Boy reasons from it."""

    def __init__(self, store: EvidenceStore | None = None):
        self.store = store

    def ingest(
        self,
        items: Iterable[dict],
        *,
        event_id: str | None = None,
        sport_id: str | None = None,
        default_source_name: str | None = None,
        default_source_url: str | None = None,
        default_observed_at: str | None = None,
        default_reliability: str = "unknown",
        default_freshness_seconds: int | None = None,
        persist: bool = False,
        case_scoped: bool = False,
    ) -> EvidencePacketResult:
        rows = list(items)
        if not rows:
            raise ValueError("Evidence packet needs at least one item.")
        if len(rows) > 100:
            raise ValueError("Evidence packet is limited to 100 items per intake.")
        if persist and self.store is None:
            raise ValueError("Evidence persistence requested but no EvidenceStore was provided.")
        if persist and not event_id and not case_scoped:
            raise ValueError(
                "Persisted evidence packet needs a canonical event_id or a durable research-case scope. "
                "Use persist=false while the event is still only known by name."
            )

        accepted: list[EvidencePacketItem] = []
        rejected: list[dict] = []
        persisted: list[str] = []

        for index, raw_item in enumerate(rows, start=1):
            try:
                item = self._normalize_item(
                    raw_item,
                    default_source_name=default_source_name,
                    default_source_url=default_source_url,
                    default_observed_at=default_observed_at,
                    default_reliability=default_reliability,
                    default_freshness_seconds=default_freshness_seconds,
                )
                accepted.append(item)
                if persist:
                    persisted.append(
                        self.store.save(item.as_evidence(event_id=event_id, sport_id=sport_id))  # type: ignore[union-attr]
                    )
            except Exception as exc:
                rejected.append(
                    {
                        "item_no": index,
                        "error": str(exc),
                        "item": dict(raw_item) if isinstance(raw_item, dict) else {"value": raw_item},
                    }
                )

        return EvidencePacketResult(
            items=tuple(accepted),
            rejected=tuple(rejected),
            persisted_ids=tuple(persisted),
        )

    def _normalize_item(
        self,
        value: dict,
        *,
        default_source_name: str | None,
        default_source_url: str | None,
        default_observed_at: str | None,
        default_reliability: str,
        default_freshness_seconds: int | None,
    ) -> EvidencePacketItem:
        if not isinstance(value, dict):
            raise ValueError("Evidence item must be an object.")
        evidence_type = str(value.get("evidence_type") or value.get("type") or "").strip()
        summary = str(value.get("summary") or value.get("finding") or "").strip()
        source_name = str(value.get("source_name") or default_source_name or "").strip()
        if not evidence_type:
            raise ValueError("Evidence item needs evidence_type.")
        if not summary:
            raise ValueError("Evidence item needs a plain-language summary.")
        if not source_name:
            raise ValueError("External evidence item needs a source_name.")

        reliability = str(value.get("reliability") or default_reliability or "unknown").casefold().strip()
        if reliability not in ALLOWED_RELIABILITY:
            raise ValueError(
                "reliability must be one of official, primary, high, strong, medium, fair, low, weak, poor, unverified or unknown."
            )

        freshness_value = (
            value.get("freshness_seconds")
            if value.get("freshness_seconds") is not None
            else default_freshness_seconds
        )
        freshness = None
        if freshness_value is not None:
            try:
                freshness = int(freshness_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("freshness_seconds must be an integer.") from exc
            if freshness < 0:
                raise ValueError("freshness_seconds cannot be negative.")

        source_url = str(value.get("source_url") or default_source_url or "").strip() or None
        observed_at = str(value.get("observed_at") or default_observed_at or "").strip() or None
        subject = str(value.get("subject") or "").strip() or None
        raw = value.get("raw")
        if raw is not None and not isinstance(raw, (dict, list)):
            raw = {"value": raw}

        supplied_id = str(value.get("id") or "").strip()
        evidence_id = supplied_id or self._stable_id(
            evidence_type=evidence_type,
            subject=subject,
            summary=summary,
            source_name=source_name,
            source_url=source_url,
            observed_at=observed_at,
        )
        return EvidencePacketItem(
            id=evidence_id,
            evidence_type=evidence_type,
            summary=summary,
            subject=subject,
            source_name=source_name,
            source_url=source_url,
            observed_at=observed_at,
            freshness_seconds=freshness,
            reliability=reliability,
            raw=raw,
        )

    @staticmethod
    def _stable_id(**parts) -> str:
        raw = "|".join(str(parts.get(key) or "").strip().casefold() for key in sorted(parts))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"evidence_external_{digest}"
