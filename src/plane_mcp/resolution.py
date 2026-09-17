"""Safe, bounded resolution of Plane list results.

This module deliberately operates only on a collection supplied by its caller.
It does not call Plane, widen a project scope, or mutate any data.  Callers
resolving project-owned records should pass ``project_id`` so that records
without an explicit matching project boundary cannot be selected.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
import unicodedata


DEFAULT_RESULT_KEY = "results"
DEFAULT_ID_FIELDS = ("id", "uuid")
DEFAULT_IDENTIFIER_FIELDS = ("identifier", "key")
DEFAULT_NAME_FIELDS = ("name", "title", "display_name")
DEFAULT_PROJECT_FIELD = "project_id"

class ResolutionError(ValueError):
    """Base class for safe resolution failures."""


class ResolutionInputError(ResolutionError):
    """Raised when the query or resolver options are invalid."""


class MalformedItemError(ResolutionError):
    """Raised when a candidate item cannot safely be resolved."""


class MissingMatchError(ResolutionError):
    """Raised when no candidate matches the query."""

    def __init__(
        self,
        query: str,
        *,
        kind: str,
        available: Sequence[str] = (),
    ) -> None:
        self.query = query
        self.kind = kind
        self.available = tuple(available)
        detail = f" No available {kind} values: {', '.join(self.available)}." if self.available else ""
        super().__init__(f"No {kind} matched {query!r}.{detail}")


class AmbiguousMatchError(ResolutionError):
    """Raised when the safest resolution has more than one candidate."""

    def __init__(self, query: str, *, kind: str, matches: Sequence["ResolvedItem"]) -> None:
        self.query = query
        self.kind = kind
        self.matches = tuple(matches)
        descriptions = ", ".join(match.describe() for match in self.matches)
        super().__init__(f"More than one {kind} matched {query!r}: {descriptions}.")


# Descriptive aliases keep the public contract easy to discover without
# requiring callers to depend on one particular spelling.
ResolutionNotFoundError = MissingMatchError
MissingResolutionError = MissingMatchError
AmbiguousResolutionError = AmbiguousMatchError
ResolutionAmbiguousError = AmbiguousMatchError
MalformedResolutionItemError = MalformedItemError


@dataclass(frozen=True)
class ResolvedItem:
    """A selected item and the identity field that selected it.

    ``item`` is the original read-only mapping from the supplied payload.
    ``index`` is its position in that payload, which makes ambiguity reports
    deterministic.  The item is guaranteed to contain a non-empty ``id`` or
    ``uuid`` field under the default contract.
    """

    item: Mapping[str, Any]
    index: int
    matched_by: str
    matched_value: str
    resolved_id: str

    def describe(self) -> str:
        """Return a stable, non-sensitive description for error messages."""
        return f"index {self.index} ({self.resolved_id})"


@dataclass(frozen=True)
class _Match:
    result: ResolvedItem
    rank: int
    field_order: int


def normalize_value(value: str) -> str:
    """Normalize user-facing text by Unicode compatibility and whitespace."""
    if not isinstance(value, str):
        raise ResolutionInputError("Resolution values must be strings.")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ResolutionInputError("Resolution values must not be empty.")
    return normalized


def _normalize_field_names(fields: Iterable[str], option_name: str) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise ResolutionInputError(f"{option_name} must contain non-empty strings.")
    normalized: list[str] = []
    for field in fields:
        if not isinstance(field, str) or not field.strip():
            raise ResolutionInputError(f"{option_name} must contain non-empty strings.")
        final_field = field.strip()
        if final_field not in normalized:
            normalized.append(final_field)
    if not normalized:
        raise ResolutionInputError(f"{option_name} must contain at least one field.")
    return tuple(normalized)


def _items_from_payload(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    *,
    result_key: str,
    kind: str,
) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        if result_key not in payload:
            raise MalformedItemError(f"{kind} payload must contain a {result_key!r} list.")
        raw_items = payload[result_key]
    else:
        raw_items = payload

    if isinstance(raw_items, (str, bytes, bytearray)) or not isinstance(raw_items, Iterable):
        raise MalformedItemError(f"{kind} payload {result_key!r} must be a list of objects.")

    items: list[Mapping[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping):
            raise MalformedItemError(f"{kind} item at index {index} must be an object.")
        items.append(item)
    return items


def _validate_item(
    item: Mapping[str, Any],
    *,
    index: int,
    id_fields: Sequence[str],
    identifier_fields: Sequence[str],
    name_fields: Sequence[str],
) -> None:
    recognized_fields = (*id_fields, *identifier_fields, *name_fields)
    for field in recognized_fields:
        if field not in item:
            continue
        value = item[field]
        if not isinstance(value, str) or not value.strip():
            raise MalformedItemError(
                f"Item at index {index} has a non-empty string requirement for {field!r}."
            )
    if not any(field in item and isinstance(item[field], str) and item[field].strip() for field in id_fields):
        raise MalformedItemError(f"Item at index {index} must contain a usable id or uuid.")


def _project_scope_matches(item: Mapping[str, Any], project_id: str, project_field: str, index: int) -> bool:
    if project_field not in item:
        raise MalformedItemError(
            f"Item at index {index} must contain {project_field!r} when project_id is supplied."
        )
    value = item[project_field]
    if isinstance(value, Mapping):
        value = value.get("id", value.get("uuid"))
    if not isinstance(value, str) or not value.strip():
        raise MalformedItemError(f"Item at index {index} has an invalid {project_field!r}.")
    return normalize_value(value) == project_id


def resolve_item(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    query: str,
    *,
    kind: str = "item",
    result_key: str = DEFAULT_RESULT_KEY,
    project_id: str | None = None,
    project_field: str = DEFAULT_PROJECT_FIELD,
    id_fields: Sequence[str] = DEFAULT_ID_FIELDS,
    identifier_fields: Sequence[str] = DEFAULT_IDENTIFIER_FIELDS,
    name_fields: Sequence[str] = DEFAULT_NAME_FIELDS,
) -> ResolvedItem:
    """Resolve one item from a bounded Plane list payload.

    Matching is deterministic and ranked as follows: exact id/UUID, exact
    identifier, exact name, then case-insensitive name.  Matching identifiers
    are intentionally not case-folded; names are.  Whitespace and Unicode
    compatibility forms are normalized before matching.

    ``payload`` may be a Plane response containing ``result_key`` (normally
    ``results``), or an iterable of item mappings.  Every item must expose an
    id/UUID.  If ``project_id`` is supplied, every item must expose the named
    project field and only an exact project match is eligible; out-of-scope
    items are ignored without appearing in errors.
    """
    final_query = normalize_value(query)
    if not isinstance(kind, str) or not kind.strip():
        raise ResolutionInputError("kind must be a non-empty string.")
    final_kind = normalize_value(kind)
    if not isinstance(result_key, str) or not result_key.strip():
        raise ResolutionInputError("result_key must be a non-empty string.")
    final_result_key = result_key.strip()
    if not isinstance(project_field, str) or not project_field.strip():
        raise ResolutionInputError("project_field must be a non-empty string.")
    final_project_field = project_field.strip()

    final_id_fields = _normalize_field_names(id_fields, "id_fields")
    final_identifier_fields = _normalize_field_names(identifier_fields, "identifier_fields")
    final_name_fields = _normalize_field_names(name_fields, "name_fields")
    final_project_id = normalize_value(project_id) if project_id is not None else None
    items = _items_from_payload(payload, result_key=final_result_key, kind=final_kind)

    matches: list[_Match] = []
    available: list[str] = []
    for index, item in enumerate(items):
        _validate_item(
            item,
            index=index,
            id_fields=final_id_fields,
            identifier_fields=final_identifier_fields,
            name_fields=final_name_fields,
        )
        if final_project_id is not None and not _project_scope_matches(
            item, final_project_id, final_project_field, index
        ):
            continue

        canonical_id = next(
            normalize_value(item[field])
            for field in final_id_fields
            if field in item
        )
        candidate = ResolvedItem(
            item=item,
            index=index,
            matched_by=final_id_fields[0],
            matched_value="",
            resolved_id=canonical_id,
        )
        available.append(candidate.resolved_id)
        best: _Match | None = None

        for field_order, field in enumerate(final_id_fields):
            value = normalize_value(item[field]) if field in item else None
            if value == final_query:
                best = _Match(
                    ResolvedItem(item, index, field, value, canonical_id),
                    rank=0,
                    field_order=field_order,
                )
                break

        if best is None:
            for field_order, field in enumerate(final_identifier_fields):
                value = normalize_value(item[field]) if field in item else None
                if value == final_query:
                    best = _Match(
                        ResolvedItem(item, index, field, value, canonical_id),
                        rank=1,
                        field_order=field_order,
                    )
                    break

        if best is None:
            for field_order, field in enumerate(final_name_fields):
                value = normalize_value(item[field]) if field in item else None
                if value == final_query:
                    best = _Match(
                        ResolvedItem(item, index, field, value, canonical_id),
                        rank=2,
                        field_order=field_order,
                    )
                    break

        if best is None:
            folded_query = final_query.casefold()
            for field_order, field in enumerate(final_name_fields):
                value = normalize_value(item[field]) if field in item else None
                if value is not None and value.casefold() == folded_query:
                    best = _Match(
                        ResolvedItem(item, index, field, value, canonical_id),
                        rank=3,
                        field_order=field_order,
                    )
                    break

        if best is not None:
            matches.append(best)

    if not matches:
        raise MissingMatchError(final_query, kind=final_kind, available=available)

    best_rank = min(match.rank for match in matches)
    best_matches = [match for match in matches if match.rank == best_rank]
    if len(best_matches) > 1:
        raise AmbiguousMatchError(
            final_query,
            kind=final_kind,
            matches=[match.result for match in best_matches],
        )

    return best_matches[0].result


def resolve_named_item(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    query: str,
    kind: str = "item",
) -> Mapping[str, Any]:
    """Return the original mapping selected by :func:`resolve_item`."""
    return resolve_item(payload, query, kind=kind).item


__all__ = [
    "AmbiguousMatchError",
    "AmbiguousResolutionError",
    "DEFAULT_ID_FIELDS",
    "DEFAULT_IDENTIFIER_FIELDS",
    "DEFAULT_NAME_FIELDS",
    "DEFAULT_PROJECT_FIELD",
    "DEFAULT_RESULT_KEY",
    "MalformedItemError",
    "MalformedResolutionItemError",
    "MissingMatchError",
    "MissingResolutionError",
    "ResolutionAmbiguousError",
    "ResolutionError",
    "ResolutionInputError",
    "ResolutionNotFoundError",
    "ResolvedItem",
    "normalize_value",
    "resolve_item",
    "resolve_named_item",
]
