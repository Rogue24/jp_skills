#!/usr/bin/env python3
"""Manage the saved project instruction-file source for instruction-source-switcher."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIG_ENV = "AGENT_INSTRUCTION_FILES_CONFIG"
PROJECT_ENV = "AGENT_INSTRUCTION_FILES_PROJECT"
DEFAULT_CONFIG = Path.home() / ".codex" / "state" / "agent-instruction-files.json"
ENTRY_FILE = "AGENTS.md"
PROFILE_VERSION = 2


class ProfileError(Exception):
    """Raised when a profile command cannot be completed."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def config_path() -> Path:
    raw = os.environ.get(CONFIG_ENV)
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_CONFIG


def project_root() -> Path:
    raw = os.environ.get(PROJECT_ENV)
    if raw:
        return Path(raw).expanduser().resolve(strict=False)
    return Path.cwd().resolve(strict=False)


def normalize_source(raw_path: str) -> Path:
    if not raw_path or not raw_path.strip():
        raise ProfileError("empty path is not a valid instruction-file source")

    path = Path(raw_path).expanduser()
    if path.name == ENTRY_FILE:
        path = path.parent
    return path.resolve(strict=False)


def validate_source(raw_path: str) -> Path:
    source = normalize_source(raw_path)
    if not source.exists():
        raise ProfileError(f"instruction-file source does not exist: {source}")
    if not source.is_dir():
        raise ProfileError(f"instruction-file source is not a directory: {source}")

    entry = source / ENTRY_FILE
    if not entry.is_file():
        raise ProfileError(f"instruction-file source must contain {ENTRY_FILE}: {source}")
    return source


def load_profile() -> dict[str, Any] | None:
    path = config_path()
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"invalid profile JSON: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileError(f"profile must be a JSON object: {path}")
    return data


def project_entry(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    if not profile:
        return None

    projects = profile.get("projects")
    if isinstance(projects, dict):
        entry = projects.get(str(project_root()))
        return entry if isinstance(entry, dict) else None

    # Backward compatibility for the old single-source profile shape.
    if isinstance(profile.get("source"), str):
        return profile
    return None


def saved_source() -> Path:
    profile = load_profile()
    entry = project_entry(profile)
    if not entry:
        raise ProfileError(
            "no instruction-file source is saved for this project; ask the user for a directory containing AGENTS.md",
            exit_code=2,
        )

    raw = entry.get("source")
    if not isinstance(raw, str) or not raw.strip():
        raise ProfileError(
            f"profile is missing a valid source for this project: {config_path()}",
            exit_code=2,
        )
    return validate_source(raw)


def write_profile(source: Path) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    existing = load_profile() or {}
    projects = existing.get("projects")
    if not isinstance(projects, dict):
        projects = {}

    root = str(project_root())
    projects[root] = {
        "source": str(source),
        "entry_file": ENTRY_FILE,
        "updated_at": now,
    }

    data = {"version": PROFILE_VERSION, "projects": projects, "updated_at": now}

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def print_result(kind: str, source: Path | None = None) -> None:
    if source is None:
        print(kind)
        return
    print(f"project: {project_root()}")
    print(f"{kind}: {source}")
    print(f"entry: {source / ENTRY_FILE}")


def command_get(_: argparse.Namespace) -> int:
    source = saved_source()
    print_result("saved", source)
    return 0


def command_set(args: argparse.Namespace) -> int:
    source = validate_source(args.path)
    write_profile(source)
    print_result("saved", source)
    return 0


def command_temp(args: argparse.Namespace) -> int:
    source = validate_source(args.path)
    print_result("temporary", source)
    return 0


def command_validate(args: argparse.Namespace) -> int:
    if args.path:
        source = validate_source(args.path)
    else:
        source = saved_source()
    print_result("valid", source)
    return 0


def command_clear(_: argparse.Namespace) -> int:
    path = config_path()
    profile = load_profile()
    projects = profile.get("projects") if profile else None
    if isinstance(projects, dict) and str(project_root()) in projects:
        del projects[str(project_root())]
        if projects:
            now = datetime.now(timezone.utc).isoformat()
            data = {"version": PROFILE_VERSION, "projects": projects, "updated_at": now}
            temp_path = path.with_suffix(path.suffix + ".tmp")
            temp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(path)
        else:
            path.unlink()
        print(f"cleared: {path}")
    elif profile and isinstance(profile.get("source"), str):
        path.unlink()
        print(f"cleared: {path}")
    else:
        print(f"already clear: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the saved project instruction-file source for instruction-source-switcher."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("get", "show", "use"):
        subparser = subparsers.add_parser(name, help="show and validate the saved project source")
        subparser.set_defaults(func=command_get)

    for name in ("set", "switch"):
        subparser = subparsers.add_parser(name, help="save a project source directory")
        subparser.add_argument("path", help="directory containing AGENTS.md, or AGENTS.md itself")
        subparser.set_defaults(func=command_set)

    subparser = subparsers.add_parser("temp", help="validate a temporary source without saving")
    subparser.add_argument("path", help="directory containing AGENTS.md, or AGENTS.md itself")
    subparser.set_defaults(func=command_temp)

    subparser = subparsers.add_parser("validate", help="validate a path, or the saved project source")
    subparser.add_argument("path", nargs="?", help="optional source path to validate")
    subparser.set_defaults(func=command_validate)

    subparser = subparsers.add_parser("clear", help="clear the saved project source")
    subparser.set_defaults(func=command_clear)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.func(args))
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
