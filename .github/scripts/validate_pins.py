#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from update_pins import load_action_sources, load_pin_entries, serialize_pins


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the published pins artifact contract."
    )
    parser.add_argument("--actions-file", required=True)
    parser.add_argument("--pins-file", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    actions_file = Path(args.actions_file)
    pins_file = Path(args.pins_file)

    allowed_actions = {
        action_source.action for action_source in load_action_sources(actions_file)
    }
    entries = load_pin_entries(pins_file)
    unknown_actions = sorted(set(entries) - allowed_actions)
    if unknown_actions:
        raise SystemExit(
            f"{args.pins_file} contains actions not present in "
            f"{args.actions_file}: "
            + ", ".join(unknown_actions)
        )

    if pins_file.read_text() != serialize_pins(entries):
        raise SystemExit(
            f"{args.pins_file} must use the canonical sorted JSON format."
        )

    print(f"Validated {len(entries)} published pin entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
