"""Strict, read-only loader for the versioned APEX knowledge registry."""
from __future__ import annotations

import json
from pathlib import Path

from .models import KnowledgeDocument, KnowledgeDomain, KnowledgeRegistry, KnowledgeStatus


_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_REGISTRY = Path(__file__).resolve().parent / "data" / "registry-v1.json"


def _document(raw: dict[str, object]) -> KnowledgeDocument:
    try:
        domain = KnowledgeDomain(str(raw["domain"]))
        status = KnowledgeStatus(str(raw.get("status", KnowledgeStatus.ACTIVE.value)))
    except (KeyError, ValueError) as error:
        raise ValueError("invalid knowledge domain or status") from error
    tags = raw.get("tags", ())
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("knowledge document tags must be a list of strings")
    return KnowledgeDocument(
        document_id=str(raw.get("document_id", "")), domain=domain,
        version=str(raw.get("version", "")), title=str(raw.get("title", "")),
        content=str(raw.get("content", "")), tags=tuple(tags),
        source_document=str(raw.get("source_document", "")),
        source_section=str(raw.get("source_section", "")), status=status,
    )


def _validate_provenance(documents: tuple[KnowledgeDocument, ...]) -> None:
    for document in documents:
        if document.status is KnowledgeStatus.UNAVAILABLE:
            continue
        source = _ROOT / document.source_document
        if not source.is_file():
            raise ValueError(f"knowledge source is unavailable: {document.document_id}")
        if document.source_section not in source.read_text(encoding="utf-8"):
            raise ValueError(f"knowledge source section is unavailable: {document.document_id}")


def load_registry_file(path: str | Path) -> KnowledgeRegistry:
    """Load and validate one registry artifact without mutation or caching."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        version = str(payload["registry_version"])
        rows = payload["documents"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid knowledge registry artifact") from error
    if not isinstance(rows, list):
        raise ValueError("knowledge registry documents must be a list")
    documents = tuple(_document(row) for row in rows if isinstance(row, dict))
    if len(documents) != len(rows):
        raise ValueError("knowledge registry document is invalid")
    _validate_provenance(documents)
    return KnowledgeRegistry(version=version, documents=documents)


def load_default_registry() -> KnowledgeRegistry:
    return load_registry_file(_DEFAULT_REGISTRY)
