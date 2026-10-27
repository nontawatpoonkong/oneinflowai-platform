"""Evidence-based claim and topic eligibility for offline evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.evaluation.retrieval import RankedResult


class TopicState(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class ClaimState(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONFLICTING = "CONFLICTING"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    chunk_id: str
    document_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ClaimTopicEligibilityInput:
    original_query: str
    transformed_queries: tuple[str, ...]
    recent_messages: tuple[str, ...]
    recognized_intents: tuple[str, ...]
    entity_state: str
    candidates: tuple[RankedResult, ...]


@dataclass(frozen=True, slots=True)
class ClaimTopicEligibilityDecision:
    eligible: bool
    topic: str | None
    topic_state: TopicState
    claim_state: ClaimState
    reasons: tuple[str, ...]
    evidence: tuple[EvidenceReference, ...]


class ClaimTopicEligibilityEvaluator:
    """Validate topic and explicit numeric claims against retrieved evidence."""

    _TOPICS = {
        "INVESTMENT": (
            ("หุ้น", "ลงทุน", "investment", "stock"),
            ("หุ้น", "ลงทุน", "investment", "stock"),
        ),
        "PRICE": (
            ("ราคา", "กี่บาท", "cost", "price", "budget", "งบ"),
            ("ราคา", "บาท", "thb", "costs", "price"),
        ),
        "PROMOTION": (
            ("โปร", "ส่วนลด", "ลด ", "promotion", "discount", "deal"),
            ("โปรโมชั่น", "promotion", "discount", "free"),
        ),
        "WARRANTY": (
            ("รับประกัน", "warranty", "sla"),
            ("รับประกัน", "warranty", "sla"),
        ),
        "PAYMENT": (
            ("จ่าย", "ชำระ", "payment", "pay", "bitcoin", "ethereum"),
            ("ชำระ", "payment", "credit card", "bank transfer", "promptpay"),
        ),
        "FEATURE": (
            (
                "รองรับ",
                "ต่อ line",
                "line",
                "facebook",
                "tiktok",
                "shopify",
                "feature",
            ),
            ("รองรับ", "includes", "supports", "line oa", "facebook"),
        ),
    }
    _QUALITATIVE_CLAIMS = ("ซื้อหนึ่งแถมหนึ่ง", "buy one get one")

    def evaluate(
        self, value: ClaimTopicEligibilityInput
    ) -> ClaimTopicEligibilityDecision:
        query = value.original_query.casefold()
        topic = next(
            (
                name
                for name, (query_terms, _) in self._TOPICS.items()
                if any(term in query for term in query_terms)
            ),
            None,
        )
        topic_candidates = list(value.candidates)
        if topic:
            evidence_terms = self._TOPICS[topic][1]
            topic_candidates = [
                result
                for result in value.candidates
                if any(term in result.chunk.text.casefold() for term in evidence_terms)
            ]
            topic_state = (
                TopicState.SUPPORTED if topic_candidates else TopicState.UNSUPPORTED
            )
        else:
            topic_state = TopicState.UNKNOWN

        numeric_claims = (
            ()
            if "BUDGET" in value.recognized_intents
            else tuple(self._numbers(value.original_query))
        )
        evidence_text = " ".join(
            result.chunk.text.casefold() for result in topic_candidates
        )
        qualitative_claims = tuple(
            claim for claim in self._QUALITATIVE_CLAIMS if claim in query
        )
        if qualitative_claims and not all(
            claim in evidence_text for claim in qualitative_claims
        ):
            claim_state = ClaimState.UNSUPPORTED
        elif numeric_claims and topic_state is TopicState.SUPPORTED:
            evidence_numbers = set(self._numbers(evidence_text))
            claim_state = (
                ClaimState.SUPPORTED
                if all(number in evidence_numbers for number in numeric_claims)
                else ClaimState.CONFLICTING
                if evidence_numbers
                else ClaimState.UNSUPPORTED
            )
        elif numeric_claims:
            claim_state = ClaimState.UNSUPPORTED
        else:
            claim_state = ClaimState.UNKNOWN

        reasons: list[str] = []
        if topic_state is TopicState.UNSUPPORTED:
            reasons.append("TOPIC_NOT_IN_EVIDENCE")
        if claim_state is ClaimState.CONFLICTING:
            reasons.append("CLAIM_CONFLICTS_WITH_EVIDENCE")
        elif claim_state is ClaimState.UNSUPPORTED:
            reasons.append("CLAIM_NOT_IN_EVIDENCE")
        evidence = tuple(
            EvidenceReference(
                result.chunk.chunk_id,
                result.chunk.document_id,
                result.chunk.content_hash,
            )
            for result in topic_candidates
        )
        eligible = (
            value.entity_state != "UNKNOWN"
            and topic_state is not TopicState.UNSUPPORTED
            and claim_state not in {ClaimState.CONFLICTING, ClaimState.UNSUPPORTED}
        )
        return ClaimTopicEligibilityDecision(
            eligible, topic, topic_state, claim_state, tuple(reasons), evidence
        )

    @staticmethod
    def _numbers(text: str) -> list[str]:
        matches = re.findall(r"\d[\d,]*(?:\.\d+)?%?", text)
        return [match.replace(",", "") for match in matches]
