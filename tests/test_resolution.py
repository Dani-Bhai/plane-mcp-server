from __future__ import annotations

import unittest

from plane_mcp.resolution import (
    AmbiguousMatchError,
    MalformedItemError,
    MalformedResolutionItemError,
    MissingMatchError,
    ResolutionInputError,
    ResolvedItem,
    normalize_value,
    resolve_item,
)


def project_items() -> dict[str, list[dict[str, str]]]:
    return {
        "results": [
            {"id": "project-1", "identifier": "ENG", "name": "Engineering"},
            {"id": "project-2", "identifier": "OPS", "name": "Operations"},
        ]
    }


class ResolutionTest(unittest.TestCase):
    def test_exact_uuid_identifier_and_name_matching(self) -> None:
        payload = project_items()

        by_id = resolve_item(payload, " project-1 ", kind="project")
        by_identifier = resolve_item(payload, "OPS", kind="project")
        by_name = resolve_item(payload, "Operations", kind="project")

        self.assertIsInstance(by_id, ResolvedItem)
        self.assertEqual("project-1", by_id.resolved_id)
        self.assertEqual(("id", "project-1"), (by_id.matched_by, by_id.matched_value))
        self.assertEqual(("identifier", "OPS"), (by_identifier.matched_by, by_identifier.matched_value))
        self.assertEqual(("name", "Operations"), (by_name.matched_by, by_name.matched_value))

    def test_identity_match_takes_precedence_over_name_match(self) -> None:
        payload = {
            "results": [
                {"id": "project-1", "identifier": "ENG", "name": "OPS"},
                {"id": "project-2", "identifier": "OPS", "name": "Other"},
            ]
        }

        result = resolve_item(payload, "OPS", kind="project")

        self.assertEqual("project-2", result.resolved_id)
        self.assertEqual("identifier", result.matched_by)

    def test_name_matching_is_case_insensitive_after_normalization(self) -> None:
        payload = {"results": [{"id": "project-1", "name": "Customer Success"}]}

        result = resolve_item(payload, "  CUSTOMER SUCCESS  ", kind="project")

        self.assertEqual("project-1", result.resolved_id)
        self.assertEqual("name", result.matched_by)
        self.assertEqual("Customer Success", result.matched_value)

    def test_exact_name_wins_over_case_insensitive_duplicate(self) -> None:
        payload = {
            "results": [
                {"id": "project-1", "name": "Platform"},
                {"id": "project-2", "name": "platform"},
            ]
        }

        result = resolve_item(payload, "Platform", kind="project")

        self.assertEqual("project-1", result.resolved_id)

    def test_missing_match_is_deterministic_and_exposes_available_ids(self) -> None:
        with self.assertRaises(MissingMatchError) as raised:
            resolve_item(project_items(), "missing", kind="project")

        error = raised.exception
        self.assertEqual("missing", error.query)
        self.assertEqual("project", error.kind)
        self.assertEqual(("project-1", "project-2"), error.available)
        self.assertEqual(
            "No project matched 'missing'. No available project values: project-1, project-2.",
            str(error),
        )

    def test_ambiguous_exact_name_raises_without_arbitrary_selection(self) -> None:
        payload = {
            "results": [
                {"id": "project-1", "name": "Platform"},
                {"id": "project-2", "name": "Platform"},
            ]
        }

        with self.assertRaises(AmbiguousMatchError) as raised:
            resolve_item(payload, "Platform", kind="project")

        error = raised.exception
        self.assertEqual(("project-1", "project-2"), tuple(match.resolved_id for match in error.matches))
        self.assertEqual(
            "More than one project matched 'Platform': index 0 (project-1), index 1 (project-2).",
            str(error),
        )

    def test_ambiguous_case_insensitive_name_is_deterministic(self) -> None:
        payload = {
            "results": [
                {"id": "project-1", "name": "Platform"},
                {"id": "project-2", "name": "PLATFORM"},
            ]
        }

        with self.assertRaises(AmbiguousMatchError) as raised:
            resolve_item(payload, "platform", kind="project")

        self.assertEqual((0, 1), tuple(match.index for match in raised.exception.matches))

    def test_malformed_payload_and_items_are_rejected(self) -> None:
        malformed_payloads: tuple[object, str] = (
            ({}, "contain a 'results' list"),
            ({"results": "not a list"}, "must be a list"),
            ({"results": ["not an object"]}, "index 0 must be an object"),
            ({"results": [{"name": "Missing UUID"}]}, "must contain a usable id or uuid"),
            ({"results": [{"id": "id", "name": " "}]}, "name"),
            ({"results": [{"id": 1, "name": "Invalid ID"}]}, "id"),
        )

        for payload, message in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(MalformedItemError, message):
                    resolve_item(payload, "anything")  # type: ignore[arg-type]

    def test_direct_iterable_and_custom_result_key_are_supported(self) -> None:
        items = (
            {"uuid": "module-1", "title": "Billing"},
            {"uuid": "module-2", "title": "Support"},
        )

        result = resolve_item(items, "billing", kind="module")
        custom_result = resolve_item(
            {"items": list(items)},
            "module-2",
            kind="module",
            result_key="items",
        )

        self.assertEqual("module-1", result.resolved_id)
        self.assertEqual("title", result.matched_by)
        self.assertEqual("module-2", custom_result.resolved_id)

    def test_project_scope_requires_explicit_matching_boundary(self) -> None:
        payload = {
            "results": [
                {"id": "item-1", "project_id": "project-a", "name": "Shared"},
                {"id": "item-2", "project_id": "project-b", "name": "Shared"},
            ]
        }

        result = resolve_item(payload, "Shared", project_id=" project-a ")

        self.assertEqual("item-1", result.resolved_id)
        with self.assertRaises(MissingMatchError) as raised:
            resolve_item(payload, "Shared", project_id="project-c")
        self.assertEqual((), raised.exception.available)

        with self.assertRaisesRegex(MalformedItemError, "project_id"):
            resolve_item({"results": [{"id": "item-1", "name": "Shared"}]}, "Shared", project_id="project-a")

    def test_project_scope_supports_nested_project_identity(self) -> None:
        payload = {"results": [{"id": "item-1", "project": {"id": "project-a"}, "name": "Task"}]}

        result = resolve_item(payload, "Task", project_id="project-a", project_field="project")

        self.assertEqual("item-1", result.resolved_id)

    def test_normalization_and_input_validation_are_explicit(self) -> None:
        self.assertEqual("Café", normalize_value("  Cafe\u0301  "))
        self.assertEqual("A-1", normalize_value("  Ａ-１ "))

        invalid_calls: tuple[tuple[object, str], ...] = (
            (None, "values must be strings"),
            (" ", "must not be empty"),
        )
        for query, message in invalid_calls:
            with self.subTest(query=query):
                with self.assertRaisesRegex(ResolutionInputError, message):
                    resolve_item(project_items(), query)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ResolutionInputError, "kind"):
            resolve_item(project_items(), "ENG", kind=" ")
        with self.assertRaisesRegex(ResolutionInputError, "result_key"):
            resolve_item(project_items(), "ENG", result_key=" ")
        with self.assertRaisesRegex(ResolutionInputError, "project_field"):
            resolve_item(project_items(), "ENG", project_field=" ")
        with self.assertRaisesRegex(ResolutionInputError, "id_fields"):
            resolve_item(project_items(), "ENG", id_fields=())
        with self.assertRaisesRegex(ResolutionInputError, "non-empty strings"):
            resolve_item(project_items(), "ENG", name_fields=("name", " "))

    def test_custom_identity_fields_and_aliases_remain_safe(self) -> None:
        payload = {"results": [{"uid": "x-1", "code": "X", "label": "Example"}]}

        result = resolve_item(
            payload,
            "Example",
            id_fields=("uid",),
            identifier_fields=("code",),
            name_fields=("label",),
        )

        self.assertEqual("x-1", result.resolved_id)
        self.assertIs(MalformedItemError, MalformedResolutionItemError)

    def test_field_options_deduplicate_and_reject_string_sequences(self) -> None:
        payload = {"results": [{"id": "project-1", "name": "Engineering"}]}

        result = resolve_item(payload, "project-1", id_fields=("id", "id"))
        self.assertEqual("project-1", result.resolved_id)

        with self.assertRaisesRegex(ResolutionInputError, "id_fields"):
            resolve_item(payload, "project-1", id_fields="id")  # type: ignore[arg-type]

    def test_project_scope_rejects_invalid_project_values(self) -> None:
        with self.assertRaisesRegex(MalformedItemError, "invalid 'project_id'"):
            resolve_item(
                {"results": [{"id": "item-1", "project_id": 1, "name": "Task"}]},
                "Task",
                project_id="project-a",
            )


if __name__ == "__main__":
    unittest.main()
