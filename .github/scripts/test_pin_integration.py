#!/usr/bin/env python3

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

import add_actions_from_issue
import update_pins
import validate_actions_source
import validate_pins_pr


class IssueActionsTest(unittest.TestCase):
    def test_parses_gh_pin_issue_body(self) -> None:
        body = """### Actions

These actions were resolved live by `gh pin`.

- `owner/action@v4`
- `owner/workflows/.github/workflows/reusable.yml@main`
"""

        self.assertEqual(
            add_actions_from_issue.parse_issue_actions(body),
            [
                update_pins.ActionSource("owner/action", "v4"),
                update_pins.ActionSource(
                    "owner/workflows/.github/workflows/reusable.yml", "main"
                ),
            ],
        )

    def test_rejects_conflicting_refs_for_one_action(self) -> None:
        body = """### Actions

- `owner/action@v1`
- `owner/action@v2`
"""

        with self.assertRaisesRegex(SystemExit, "multiple refs"):
            add_actions_from_issue.parse_issue_actions(body)

    def test_deduplicates_exact_action_ref(self) -> None:
        body = """### Actions

- `owner/action/subpath@v1`
- `owner/action/subpath@v1`
"""

        self.assertEqual(
            add_actions_from_issue.parse_issue_actions(body),
            [update_pins.ActionSource("owner/action/subpath", "v1")],
        )

    def test_ignores_full_sha_refs(self) -> None:
        sha = "a" * 40
        body = f"""### Actions

- `owner/action@{sha}`
"""

        self.assertEqual(add_actions_from_issue.parse_issue_actions(body), [])

    def test_rejects_malformed_action_bullet(self) -> None:
        body = """### Actions

- owner/action@v1
"""

        with self.assertRaisesRegex(SystemExit, "backtick references"):
            add_actions_from_issue.parse_issue_actions(body)

    def test_adds_source_and_pin_using_reported_ref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            actions_file = Path(directory, "actions.csv")
            pins_file = Path(directory, "pins.json")
            actions_file.write_text("actions/checkout,\n")
            pins_file.write_text('{"actions": []}\n')
            metadata = {
                "action": "owner/action",
                "tag": "v4",
                "sha": "a" * 40,
                "published_at": "2026-07-10T10:00:00Z",
            }

            with mock.patch.object(
                add_actions_from_issue,
                "resolve_action_metadata",
                return_value=metadata,
            ) as resolve:
                changed = add_actions_from_issue.update_from_issue(
                    "### Actions\n\n- `owner/action@v4`\n",
                    actions_file,
                    pins_file,
                )

            self.assertEqual(changed, ["owner/action"])
            self.assertEqual(
                actions_file.read_text(),
                "actions/checkout,\nowner/action,v4\n",
            )
            self.assertEqual(
                json.loads(pins_file.read_text()),
                {"actions": [metadata]},
            )
            resolve.assert_called_once_with("owner/action", "v4")

    def test_restores_source_when_pin_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            actions_file = Path(directory, "actions.csv")
            pins_file = Path(directory, "pins.json")
            actions_file.write_text("")
            metadata = {
                "action": "owner/action",
                "tag": "v4",
                "sha": "a" * 40,
                "published_at": "2026-07-10T10:00:00Z",
            }
            pins_file.write_text(json.dumps({"actions": [metadata]}))

            changed = add_actions_from_issue.update_from_issue(
                "### Actions\n\n- `owner/action@v4`\n",
                actions_file,
                pins_file,
            )

            self.assertEqual(changed, ["owner/action"])
            self.assertEqual(actions_file.read_text(), "owner/action,v4\n")

    def test_preserves_multiple_paths_from_one_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            actions_file = Path(directory, "actions.csv")
            pins_file = Path(directory, "pins.json")
            actions_file.write_text("")
            pins_file.write_text('{"actions": []}\n')
            body = """### Actions

- `owner/repo/action-a@v1`
- `owner/repo/.github/workflows/build.yml@v2`
"""

            def metadata(action: str, ref: str) -> dict[str, str]:
                return {
                    "action": action,
                    "tag": ref,
                    "sha": ("a" if ref == "v1" else "b") * 40,
                    "published_at": "2026-07-10T10:00:00Z",
                }

            with mock.patch.object(
                add_actions_from_issue,
                "resolve_action_metadata",
                side_effect=metadata,
            ) as resolve:
                changed = add_actions_from_issue.update_from_issue(
                    body, actions_file, pins_file
                )

            self.assertEqual(
                changed,
                [
                    "owner/repo/action-a",
                    "owner/repo/.github/workflows/build.yml",
                ],
            )
            self.assertEqual(
                actions_file.read_text(),
                "owner/repo/.github/workflows/build.yml,v2\n"
                "owner/repo/action-a,v1\n",
            )
            self.assertEqual(
                [
                    entry["action"]
                    for entry in json.loads(pins_file.read_text())["actions"]
                ],
                [
                    "owner/repo/.github/workflows/build.yml",
                    "owner/repo/action-a",
                ],
            )
            self.assertEqual(
                resolve.call_args_list,
                [
                    mock.call("owner/repo/action-a", "v1"),
                    mock.call(
                        "owner/repo/.github/workflows/build.yml", "v2"
                    ),
                ],
            )


class PinsContractTest(unittest.TestCase):
    def valid_payload(self) -> dict:
        return {
            "actions": [
                {
                    "action": "owner/action",
                    "tag": "v1",
                    "sha": "a" * 40,
                    "published_at": "2026-07-10T10:00:00Z",
                }
            ]
        }

    def test_accepts_extension_contract(self) -> None:
        entries = update_pins.parse_pin_entries(json.dumps(self.valid_payload()))
        self.assertEqual(list(entries), ["owner/action"])

    def test_accepts_uppercase_hex_sha(self) -> None:
        payload = self.valid_payload()
        payload["actions"][0]["sha"] = "A" * 40

        entries = update_pins.parse_pin_entries(json.dumps(payload))

        self.assertEqual(entries["owner/action"]["sha"], "A" * 40)

    def test_rejects_missing_entry_field(self) -> None:
        payload = self.valid_payload()
        del payload["actions"][0]["published_at"]

        with self.assertRaisesRegex(SystemExit, "contain exactly"):
            update_pins.parse_pin_entries(json.dumps(payload))

    def test_rejects_invalid_sha(self) -> None:
        payload = self.valid_payload()
        payload["actions"][0]["sha"] = "not-a-sha"

        with self.assertRaisesRegex(SystemExit, "40-character hex"):
            update_pins.parse_pin_entries(json.dumps(payload))

    def test_rejects_invalid_timestamp(self) -> None:
        payload = self.valid_payload()
        payload["actions"][0]["published_at"] = "yesterday"

        with self.assertRaisesRegex(SystemExit, "RFC3339"):
            update_pins.parse_pin_entries(json.dumps(payload))

    def test_rejects_duplicate_actions(self) -> None:
        payload = self.valid_payload()
        payload["actions"].append(payload["actions"][0].copy())

        with self.assertRaisesRegex(SystemExit, "duplicates owner/action"):
            update_pins.parse_pin_entries(json.dumps(payload))

    def test_prunes_entries_removed_from_source(self) -> None:
        entries = {
            "owner/kept": {"action": "owner/kept"},
            "owner/removed": {"action": "owner/removed"},
        }

        self.assertEqual(
            update_pins.prune_pin_entries(entries, {"owner/kept"}),
            {"owner/kept": {"action": "owner/kept"}},
        )

    def test_resolves_subpath_ref_against_root_repository(self) -> None:
        with mock.patch.object(
            update_pins,
            "github_get_json",
            return_value={"sha": "a" * 40},
        ) as github_get_json:
            update_pins.resolve_commit_for_ref(
                "owner/repo/.github/workflows/build.yml", "v1"
            )

        github_get_json.assert_called_once_with(
            "/repos/owner/repo/commits/v1"
        )


class SourceValidationTest(unittest.TestCase):
    def test_recognizes_reusable_workflow_subpath(self) -> None:
        self.assertTrue(
            validate_actions_source.is_reusable_workflow_subpath(
                ".github/workflows/reusable.yaml"
            )
        )
        self.assertFalse(
            validate_actions_source.is_reusable_workflow_subpath(
                "action/action.yml"
            )
        )

    def test_validates_reusable_workflow_file(self) -> None:
        with mock.patch.object(
            validate_actions_source,
            "github_get_json",
            return_value={"full_name": "owner/workflows"},
        ), mock.patch.object(
            validate_actions_source,
            "github_path_exists",
            return_value=True,
        ) as path_exists:
            validate_actions_source.validate_action_exists(
                "owner/workflows/.github/workflows/reusable.yml"
            )

        path_exists.assert_called_once_with(
            "/repos/owner/workflows/contents/.github/workflows/reusable.yml"
        )


class PullRequestValidationTest(unittest.TestCase):
    def test_rejects_source_removal_without_pin_removal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            actions_file = Path(directory, "actions.csv")
            pins_file = Path(directory, "pins.json")
            actions_file.write_text("")
            pins_file.write_text(
                update_pins.serialize_pins(
                    {
                        "owner/removed": {
                            "action": "owner/removed",
                            "tag": "v1",
                            "sha": "a" * 40,
                            "published_at": "2026-07-10T10:00:00Z",
                        }
                    }
                )
            )
            args = mock.Mock(
                actions_file=str(actions_file),
                pins_file=str(pins_file),
                base_ref="HEAD",
            )

            with mock.patch.object(
                validate_pins_pr, "parse_args", return_value=args
            ), mock.patch.object(
                validate_pins_pr,
                "changed_files",
                return_value=[str(actions_file)],
            ), self.assertRaisesRegex(SystemExit, "not present"):
                validate_pins_pr.main()


if __name__ == "__main__":
    unittest.main()
