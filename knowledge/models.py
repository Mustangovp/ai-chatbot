"""Immutable domain models for authoritative, versioned coaching knowledge."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KnowledgeDomain(str, Enum):
    TRAINING = "training"
    NUTRITION = "nutrition"
    RECOVERY = "recovery"
    SUPPLEMENTATION = "supplementation"


class KnowledgeStatus(str, Enum):
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class KnowledgeDocument:
    """One source-traceable statement. It has no user, request, or delivery state."""
    document_id: str
    domain: KnowledgeDomain
    version: str
    title: str
    content: str
    tags: tuple[str, ...]
    source_document: str
    source_section: str
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.document_id or not self.version or not self.title:
            raise ValueError("knowledge document identity is required")
        if self.status is KnowledgeStatus.ACTIVE:
            if not self.content or not self.source_document or not self.source_section:
                raise ValueError("active knowledge requires content and source provenance")
        elif self.content or self.source_document or self.source_section:
            raise ValueError("unavailable knowledge cannot contain coaching content")
        normalized_tags = tuple(sorted({str(tag).strip().lower() for tag in self.tags if str(tag).strip()}))
        object.__setattr__(self, "tags", normalized_tags)


@dataclass(frozen=True)
class KnowledgeRegistry:
    """The complete immutable registry for one knowledge release."""
    version: str
    documents: tuple[KnowledgeDocument, ...]

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("knowledge registry version is required")
        seen = set()
        domains = set()
        for document in self.documents:
            if document.document_id in seen:
                raise ValueError(f"duplicate knowledge document: {document.document_id}")
            seen.add(document.document_id)
            domains.add(document.domain)
        required = set(KnowledgeDomain)
        if domains != required:
            missing = ", ".join(sorted(domain.value for domain in required - domains))
            raise ValueError(f"knowledge registry domain coverage is incomplete: {missing}")
