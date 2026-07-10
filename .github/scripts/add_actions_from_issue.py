#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

from update_pins import (
    ACTION_NAME_RE,
    REF_OVERRIDE_RE,
    ActionSource,
    load_action_sources,
    load_pin_entries,
    resolve_action_metadata,
    serialize_action_sources,
    serialize_pins,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add action references from a gh-pin issue."
    )
    parser.add_argument("--event-file", required=True)
    parser.add_argument("--actions-file", required=True)
    parser.add_argument("--pins-file", required=True)
    return parser.parse_args()


def parse_action_reference(reference: str) -> ActionSource:
    action, separator, ref = reference.rpartition("@")
    if not separator:
        raise SystemExit(f"Action reference must contain @ref: {reference!r}")
    if ACTION_NAME_RE.fullmatch(action) is None:
        raise SystemExit(
            f"Action must match org/repo or org/repo/subpath: {action!r}"
        )
    if REF_OVERRIDE_RE.fullmatch(ref) is None:
        raise SystemExit(f"Action reference contains an invalid ref: {reference!r}")

    return ActionSource(action=action, ref_override=ref)


def parse_issue_actions(body: str) -> list[ActionSource]:
    in_actions_section = False
    action_sources: list[ActionSource] = []
    seen_by_action: dict[str, ActionSource] = {}

    for line in body.splitlines():
        if line.strip() == "### Actions":
            in_actions_section = True
            continue
        if in_actions_section and line.startswith("#"):
            break
        if not in_actions_section:
            continue

        stripped = line.strip()
        if not stripped.startswith("- "):
            continue

        item = stripped[2:].strip()
        if len(item) < 3 or not item.startswith("`") or not item.endswith("`"):
            raise SystemExit("Actions section bullets must contain backtick references.")

        action_source = parse_action_reference(item[1:-1])
        previous = seen_by_action.get(action_source.action)
        if previous is not None and previous != action_source:
            raise SystemExit(
                f"Issue contains multiple refs for {action_source.action}."
            )
        if previous is not None:
            continue

        seen_by_action[action_source.action] = action_source
        action_sources.append(action_source)

    if not in_actions_section:
        raise SystemExit("Issue body must contain an '### Actions' section.")
    if not action_sources:
        raise SystemExit("Issue Actions section must contain at least one action.")

    return action_sources


def update_from_issue(
    body: str, actions_file: Path, pins_file: Path
) -> list[str]:
    requested_sources = parse_issue_actions(body)
    current_sources = load_action_sources(actions_file)
    current_by_action = {source.action: source for source in current_sources}
    current_entries = load_pin_entries(pins_file)
    changed_actions: list[str] = []

    for requested_source in requested_sources:
        action_name = requested_source.action
        source = current_by_action.get(action_name)
        if source is None:
            source = requested_source
            current_sources.append(source)
            current_by_action[action_name] = source
            changed_actions.append(action_name)

        if action_name in current_entries:
            continue

        current_entries[action_name] = resolve_action_metadata(
            action_name, source.ref_override
        )
        if action_name not in changed_actions:
            changed_actions.append(action_name)

    if not changed_actions:
        return []

    actions_file.write_text(serialize_action_sources(current_sources))
    pins_file.write_text(serialize_pins(current_entries))
    return changed_actions


def main() -> int:
    args = parse_args()
    event = json.loads(Path(args.event_file).read_text())
    issue = event.get("issue")
    if not isinstance(issue, dict) or not isinstance(issue.get("body"), str):
        raise SystemExit("GitHub event must contain an issue body.")

    changed_actions = update_from_issue(
        issue["body"], Path(args.actions_file), Path(args.pins_file)
    )
    if changed_actions:
        print("Added " + ", ".join(changed_actions) + ".")
    else:
        print("All requested actions are already pinned.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
