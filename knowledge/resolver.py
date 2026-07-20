"""Deterministic, read-only retrieval over the immutable knowledge registry."""
from __future__ import annotations

from dataclasses import dataclass

from .models import KnowledgeDocument, KnowledgeDomain, KnowledgeRegistry, KnowledgeStatus


_DOMAIN_FOR_RECOMMENDATION = {
    "workout": KnowledgeDomain.TRAINING,
    "nutrition": KnowledgeDomain.NUTRITION,
    "recovery": KnowledgeDomain.RECOVERY,
    "supplementation": KnowledgeDomain.SUPPLEMENTATION,
}


@dataclass(frozen=True)
class KnowledgeResolution:
    registry_version: str
    domain: KnowledgeDomain
    documents: tuple[KnowledgeDocument, ...]
    domain_available: bool


class KnowledgeResolver:
    """A pure resolver. It does not call models, databases, or network services."""
    def __init__(self, registry: KnowledgeRegistry):
        self._registry = registry

    @property
    def registry_version(self) -> str:
        return self._registry.version

    def resolve(self, domain: KnowledgeDomain | str, *, tags: tuple[str, ...] = ()) -> KnowledgeResolution:
        selected_domain = KnowledgeDomain(domain)
        requested_tags = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
        domain_documents = tuple(document for document in self._registry.documents
                                 if document.domain is selected_domain)
        available = any(document.status is KnowledgeStatus.ACTIVE for document in domain_documents)
        documents = tuple(
            document for document in domain_documents
            if document.status is KnowledgeStatus.ACTIVE
            and (not requested_tags or requested_tags.intersection(document.tags))
        )
        return KnowledgeResolution(self._registry.version, selected_domain, documents, available)

    def resolve_for_recommendation(self, kind: str) -> KnowledgeResolution | None:
        domain = _DOMAIN_FOR_RECOMMENDATION.get(str(kind).lower())
        return self.resolve(domain) if domain is not None else None
