"""CLI entry point — argparse commands for okit."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from okit import __version__
from okit import config as okit_config
from okit.core import (
    ArtifactKind,
    InstallRecord,
    check_update_available,
    clone_repo,
    discover_agents,
    discover_all,
    discover_skills,
    get_repo_commit,
    install_artifact,
    load_manifest,
    manifest_key,
    remove_artifact,
    validate_agent,
    validate_skill,
)
from okit.providers import ALL_PROVIDERS, PROVIDERS_BY_ID
from okit.selector import interactive_select, interactive_select_grouped
from okit.setup import run_setup


# --- Display helpers ---

_BOX_WIDTH = 50
_STATUS_ICONS: dict[str, str] = {
    "ok": "✓",
    "skip": "→",
    "up": "✓",
    "err": "✗",
    "miss": "✗",
    "dry": "○",
}
_KIND_LABELS: dict[str, str] = {
    "skill": "Skills",
    "agent": "Agents",
    "multi-agent": "Multi-Agents",
}


@dataclass
class ArtifactResult:
    name: str
    status: str  # ok | skip | up | err | miss | dry
    detail: str = ""
    kind: str = ""


@dataclass
class RepoResults:
    repo: str
    results: list[ArtifactResult] = field(default_factory=list)


def _repo_label(repo: str) -> str:
    """Shorten a repo URL to a readable label."""
    return repo.rstrip("/").split("/")[-1] or repo


def _print_repo_header(repo: str) -> None:
    label = f" {_repo_label(repo)} "
    fill = max(0, _BOX_WIDTH - len(label) - 2)
    print(f"┌─{label}{'─' * fill}┐")


def _print_kind_header(kind: str, count: int) -> None:
    label = _KIND_LABELS.get(kind, kind.capitalize())
    print(f"├─ {label} ({count})")


def _print_artifact_result(result: ArtifactResult) -> None:
    icon = _STATUS_ICONS.get(result.status, "?")
    detail = f" ({result.detail})" if result.detail else ""
    print(f"│  {icon} {result.name}{detail}")


def _print_repo_footer() -> None:
    print(f"└{'─' * (_BOX_WIDTH)}┘")


def _print_summary(installed: int, skipped: int, errors: int) -> None:
    parts = [f"{installed} installed", f"{skipped} up to date", f"{errors} error(s)"]
    print("\n" + ", ".join(parts) + ".")


def _render_repo_results(repo_results: RepoResults) -> None:
    """Print all results for one repo in clustered box-drawing format."""
    _print_repo_header(repo_results.repo)

    by_kind: dict[str, list[ArtifactResult]] = {}
    for r in repo_results.results:
        by_kind.setdefault(r.kind, []).append(r)

    for kind in ("skill", "agent", "multi-agent"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        _print_kind_header(kind, len(items))
        for item in items:
            _print_artifact_result(item)

    _print_repo_footer()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="okit",
        description="Manage OpenCode skills and agents from Git repositories.",
    )
    parser.add_argument("--version", action="version", version=f"okit {__version__}")
    sub = parser.add_subparsers(dest="command")

    # --- list ---
    p_list = sub.add_parser("list", help="List available skills/agents in a repository")
    p_list.add_argument("repo", help="Git repo URL or user/repo shorthand")
    p_list.add_argument("--branch", help="Branch to clone")
    p_list.add_argument("--kind", choices=["skill", "agent", "all"], default="all")
    p_list.add_argument("--detail", action="store_true", help="Show descriptions")

    # --- install ---
    p_install = sub.add_parser("install", help="Install skills/agents from a repository")
    p_install.add_argument("repo", nargs="?", help="Git repo URL or user/repo shorthand")
    p_install.add_argument("--branch", help="Branch to clone")
    p_install.add_argument("--all", action="store_true", dest="install_all", help="Install everything")
    p_install.add_argument("--skills", help="Comma-separated skill names to install")
    p_install.add_argument("--agents", help="Comma-separated agent names to install")
    p_install.add_argument("--manifest", metavar="FILE", help="Install all artifacts from a manifest file")
    p_install.add_argument("--project", action="store_true", help="Install to .opencode/ in current project")
    p_install.add_argument("--force", action="store_true", help="Overwrite existing")
    p_install.add_argument("--dry-run", action="store_true", help="Preview without installing")

    # --- remove ---
    p_remove = sub.add_parser("remove", help="Remove installed skills/agents")
    p_remove.add_argument("--skills", help="Comma-separated skill names to remove")
    p_remove.add_argument("--agents", help="Comma-separated agent names to remove")
    p_remove.add_argument("--all", action="store_true", dest="remove_all", help="Remove all tracked artifacts")
    p_remove.add_argument("--project", action="store_true", help="Remove from project .opencode/")
    p_remove.add_argument("--force", action="store_true", help="Skip confirmation")

    # --- installed ---
    p_installed = sub.add_parser("installed", help="Show installed skills/agents")
    p_installed.add_argument("--detail", action="store_true", help="Show source tracking info")
    p_installed.add_argument("--kind", choices=["skill", "agent", "all"], default="all")

    # --- validate ---
    p_validate = sub.add_parser("validate", help="Validate skills/agents in a repo or directory")
    p_validate.add_argument("path", nargs="?", default=".", help="Local path to validate")
    p_validate.add_argument("--repo", help="Remote repo to validate")
    p_validate.add_argument("--branch", help="Branch (with --repo)")

    # --- update ---
    p_update = sub.add_parser("update", help="Re-install artifacts that have changed upstream")
    p_update.add_argument("--skills", help="Comma-separated skill names to update (default: all tracked)")
    p_update.add_argument("--agents", help="Comma-separated agent names to update (default: all tracked)")
    p_update.add_argument("--dry-run", action="store_true", help="Preview without installing")

    # --- sync ---
    p_sync = sub.add_parser(
        "sync",
        help="Update existing artifacts and offer new ones from tracked repos",
    )
    p_sync.add_argument("--all", action="store_true", dest="sync_all", help="Install all updated + new artifacts")
    p_sync.add_argument("--force", action="store_true", help="Overwrite existing")
    p_sync.add_argument("--dry-run", action="store_true", help="Preview without installing")

    # --- doctor ---
    sub.add_parser("doctor", help="Check OpenCode directory structure and config")

    # --- setup ---
    sub.add_parser("setup", help="Configure okit (providers, etc.)")

    args = parser.parse_args()

    # Auto-init the config on first contact, regardless of which command runs.
    # Detection writes a default config enabling every CLI we find on PATH.
    okit_config.ensure_initialized()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "list": cmd_list,
        "install": cmd_install,
        "remove": cmd_remove,
        "installed": cmd_installed,
        "update": cmd_update,
        "sync": cmd_sync,
        "validate": cmd_validate,
        "doctor": cmd_doctor,
        "setup": cmd_setup,
    }
    commands[args.command](args)


# --- Command implementations ---


def cmd_list(args: argparse.Namespace) -> None:
    repo_path, is_temp = _resolve_source(args.repo, args.branch)
    try:
        artifacts = _filter_by_kind(discover_all(repo_path), args.kind)
        if not artifacts:
            print("No artifacts found.")
            return

        _print_artifact_table(artifacts, detail=args.detail)
    finally:
        _cleanup_source(repo_path, is_temp)


def cmd_install(args: argparse.Namespace) -> None:
    if args.manifest:
        _cmd_install_from_manifest(args)
        return

    is_bare_install = not args.repo and not args.install_all and not args.skills and not args.agents
    if is_bare_install:
        _cmd_reinstall_from_active_manifest(args)
        return

    if not args.repo:
        print("Error: repo argument is required when not using --manifest")
        sys.exit(1)

    repo_path, is_temp = _resolve_source(args.repo, args.branch)
    try:
        commit = get_repo_commit(repo_path)
        all_artifacts = discover_all(repo_path)

        uses_filter_flags = args.install_all or args.skills or args.agents
        if not uses_filter_flags:
            all_artifacts = _apply_interactive_selection(all_artifacts, args.repo)
            if all_artifacts is None:
                print("Cancelled.")
                return

        to_install = _select_artifacts(all_artifacts, args) if uses_filter_flags else all_artifacts
        if not to_install:
            print("No matching artifacts found.")
            return

        project_dir = Path.cwd() if args.project else None
        repo_result = RepoResults(repo=args.repo)

        for artifact in to_install:
            if args.dry_run:
                target = _describe_target(artifact, args.project, project_dir)
                repo_result.results.append(
                    ArtifactResult(name=artifact.name, status="dry", detail=target, kind=artifact.kind)
                )
            else:
                ok, msg = install_artifact(
                    artifact,
                    project=args.project,
                    project_dir=project_dir,
                    repo_url=args.repo,
                    commit=commit,
                    force=args.force,
                )
                status = "ok" if ok else "skip"
                repo_result.results.append(
                    ArtifactResult(name=artifact.name, status=status, detail="" if ok else msg, kind=artifact.kind)
                )

        _render_repo_results(repo_result)
    finally:
        _cleanup_source(repo_path, is_temp)


def _cmd_install_from_manifest(args: argparse.Namespace) -> None:
    if args.repo:
        print("Error: --manifest cannot be combined with a repo argument")
        sys.exit(1)
    if args.skills or args.agents:
        print("Error: --manifest cannot be combined with --skills or --agents")
        sys.exit(1)

    manifest_file = Path(args.manifest)
    if not manifest_file.exists():
        print(f"Error: manifest file not found: {manifest_file}")
        sys.exit(1)

    records = _load_external_manifest(manifest_file)
    if not records:
        print("Manifest is empty — nothing to install.")
        return

    by_repo: dict[str, list[InstallRecord]] = {}
    for rec in records.values():
        by_repo.setdefault(rec.repo, []).append(rec)

    project_dir = Path.cwd() if args.project else None
    installed = skipped = errors = 0

    for repo_url, recs in by_repo.items():
        repo_path, is_temp = _resolve_source(repo_url, args.branch)
        try:
            commit = get_repo_commit(repo_path)
            available = {a.name: a for a in discover_all(repo_path)}
            repo_result = RepoResults(repo=repo_url)

            for rec in recs:
                artifact = available.get(rec.name)
                if artifact is None:
                    repo_result.results.append(
                        ArtifactResult(name=rec.name, status="miss", detail=f"not found in {repo_url}", kind=rec.kind)
                    )
                    errors += 1
                    continue

                if args.dry_run:
                    target = _describe_target(artifact, args.project, project_dir)
                    repo_result.results.append(
                        ArtifactResult(name=artifact.name, status="dry", detail=target, kind=artifact.kind)
                    )
                else:
                    ok, msg = install_artifact(
                        artifact,
                        project=args.project,
                        project_dir=project_dir,
                        repo_url=repo_url,
                        commit=commit,
                        force=args.force,
                    )
                    status = "ok" if ok else "skip"
                    repo_result.results.append(
                        ArtifactResult(name=artifact.name, status=status, detail="" if ok else msg, kind=artifact.kind)
                    )
                    if ok:
                        installed += 1
                    else:
                        skipped += 1

            _render_repo_results(repo_result)
        finally:
            _cleanup_source(repo_path, is_temp)

    if not args.dry_run:
        _print_summary(installed, skipped, errors)
    if errors:
        sys.exit(1)


def _cmd_reinstall_from_active_manifest(args: argparse.Namespace) -> None:
    records = load_manifest()
    if not records:
        print("Nothing tracked in manifest. Install from a repo first.")
        return

    by_repo: dict[str, list[InstallRecord]] = {}
    for rec in records.values():
        by_repo.setdefault(rec.repo, []).append(rec)

    project_dir = Path.cwd() if args.project else None
    installed = skipped = errors = 0

    for repo_url, recs in by_repo.items():
        try:
            repo_path, is_temp = _resolve_source(repo_url, args.branch)
        except Exception as exc:
            print(f"  [ERR] Cannot reach {repo_url}: {exc}")
            errors += len(recs)
            continue

        try:
            commit = get_repo_commit(repo_path)
            available = {a.name: a for a in discover_all(repo_path)}
            repo_result = RepoResults(repo=repo_url)

            for rec in recs:
                artifact = available.get(rec.name)
                if artifact is None:
                    repo_result.results.append(
                        ArtifactResult(name=rec.name, status="miss", detail=f"not found in {repo_url}", kind=rec.kind)
                    )
                    errors += 1
                    continue

                if args.dry_run:
                    target = _describe_target(artifact, args.project, project_dir)
                    repo_result.results.append(
                        ArtifactResult(name=artifact.name, status="dry", detail=target, kind=artifact.kind)
                    )
                    installed += 1
                else:
                    ok, msg = install_artifact(
                        artifact,
                        project=args.project,
                        project_dir=project_dir,
                        repo_url=repo_url,
                        commit=commit,
                        force=args.force,
                    )
                    status = "ok" if ok else "skip"
                    repo_result.results.append(
                        ArtifactResult(name=artifact.name, status=status, detail="" if ok else msg, kind=artifact.kind)
                    )
                    if ok:
                        installed += 1
                    else:
                        skipped += 1

            _render_repo_results(repo_result)
        finally:
            _cleanup_source(repo_path, is_temp)

    _print_summary(installed, skipped, errors)
    if errors:
        sys.exit(1)


def _build_remove_selector_data(records: dict) -> list[dict]:
    """Build grouped selector structure from manifest records, grouped by repo → kind."""
    by_repo: dict[str, dict[str, list[tuple[int, str]]]] = {}
    for idx, rec in enumerate(records.values()):
        by_repo.setdefault(rec.repo, {}).setdefault(rec.kind, []).append((idx, rec.name))

    groups = []
    for repo_url, by_kind in by_repo.items():
        children = [
            {"label": _KIND_LABELS.get(kind, kind.capitalize()), "items": items}
            for kind, items in by_kind.items()
        ]
        groups.append({"label": repo_url, "children": children})
    return groups


def _resolve_remove_items_interactive(records: dict) -> list[tuple[str, str]] | None:
    """Show grouped selector for removal; return selected (kind, name) pairs or None on cancel."""
    all_records = list(records.values())
    groups = _build_remove_selector_data(records)
    selected_indices = interactive_select_grouped(groups, header="Select artifacts to remove")
    if selected_indices is None:
        return None
    return [(all_records[i].kind, all_records[i].name) for i in selected_indices]


def _collect_remove_items(args: argparse.Namespace) -> list[tuple[str, str]] | None:
    """Resolve which artifacts to remove; return (kind, name) pairs or None on cancel.

    Returns None if the user cancels the interactive selector.
    """
    if args.remove_all:
        records = load_manifest()
        return [(rec.kind, rec.name) for rec in records.values()]

    if args.skills or args.agents:
        items: list[tuple[str, str]] = []
        if args.skills:
            for name in args.skills.split(","):
                items.append(("skill", name.strip()))
        if args.agents:
            for name in args.agents.split(","):
                items.append(("agent", name.strip()))
        return items

    # Interactive path: no flags given
    if not sys.stdin.isatty():
        print("Error: specify artifacts to remove or use --all")
        sys.exit(1)

    records = load_manifest()
    if not records:
        print("Nothing tracked in manifest.")
        return []

    return _resolve_remove_items_interactive(records)


def _confirm_removal(items: list[tuple[str, str]], records: dict) -> bool:
    """Print a grouped removal summary and prompt for confirmation.

    Returns True if the user confirms, False otherwise.
    """
    by_repo: dict[str, list[tuple[str, str]]] = {}
    rec_lookup = {(r.kind, r.name): r for r in records.values()}
    for kind, name in items:
        rec = rec_lookup.get((kind, name))
        repo = rec.repo if rec else "unknown"
        by_repo.setdefault(repo, []).append((kind, name))

    for repo_url, repo_items in by_repo.items():
        _print_repo_header(repo_url)
        by_kind: dict[str, list[str]] = {}
        for kind, name in repo_items:
            by_kind.setdefault(kind, []).append(name)
        for kind in ("skill", "agent", "multi-agent"):
            names = by_kind.get(kind, [])
            if not names:
                continue
            _print_kind_header(kind, len(names))
            for name in names:
                print(f"│    {name}")
        _print_repo_footer()

    answer = input(f"\nRemove {len(items)} artifact(s)? [y/N] ").strip().lower()
    return answer == "y"


def _apply_removals(
    items: list[tuple[str, str]],
    args: argparse.Namespace,
    project_dir: Path | None,
    records: dict,
) -> None:
    """Execute removal and render clustered box-drawing output per repo."""
    by_repo: dict[str, list[tuple[str, str]]] = {}
    rec_lookup = {(r.kind, r.name): r for r in records.values()}
    for kind, name in items:
        rec = rec_lookup.get((kind, name))
        repo = rec.repo if rec else "unknown"
        by_repo.setdefault(repo, []).append((kind, name))

    for repo_url, repo_items in by_repo.items():
        repo_result = RepoResults(repo=repo_url)
        for kind, name in repo_items:
            ok, msg = remove_artifact(kind, name, project=args.project, project_dir=project_dir)
            status = "ok" if ok else "err"
            repo_result.results.append(ArtifactResult(name=name, status=status, detail=msg if not ok else "", kind=kind))
        _render_repo_results(repo_result)


def cmd_remove(args: argparse.Namespace) -> None:
    project_dir = Path.cwd() if args.project else None

    items = _collect_remove_items(args)
    if items is None:
        print("Cancelled.")
        return
    if not items:
        print("Nothing to remove.")
        return

    records = load_manifest()

    if not args.force and not _confirm_removal(items, records):
        print("Aborted.")
        return

    _apply_removals(items, args, project_dir, records)


def _print_artifact_detail(rec: "InstallRecord") -> None:
    """Print indented detail lines for an installed artifact."""
    hash_short = rec.content_hash[:12] if rec.content_hash else "n/a"
    print(f"│     hash: {hash_short}")
    print(f"│     installed: {rec.installed_at}")


def _render_installed_repo(repo_results: RepoResults, detail_map: dict[str, "InstallRecord"]) -> None:
    """Print installed artifacts for one repo with optional detail lines."""
    _print_repo_header(repo_results.repo)

    by_kind: dict[str, list[ArtifactResult]] = {}
    for r in repo_results.results:
        by_kind.setdefault(r.kind, []).append(r)

    for kind in ("skill", "agent", "multi-agent"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        _print_kind_header(kind, len(items))
        for item in items:
            _print_artifact_result(item)
            rec = detail_map.get(item.name)
            if rec is not None:
                _print_artifact_detail(rec)

    _print_repo_footer()


def _build_installed_repo_results(repo: str, recs: list["InstallRecord"]) -> RepoResults:
    """Convert manifest records for one repo into a RepoResults for display."""
    repo_results = RepoResults(repo=repo)
    for rec in sorted(recs, key=lambda r: r.name):
        detail = rec.description[:60] if rec.description else ""
        repo_results.results.append(
            ArtifactResult(name=rec.name, status="ok", detail=detail, kind=rec.kind)
        )
    return repo_results


def cmd_installed(args: argparse.Namespace) -> None:
    records = load_manifest()
    if not records:
        print("No artifacts installed via okit.")
        return

    filtered = {
        k: v for k, v in records.items()
        if args.kind == "all" or v.kind == args.kind
    }
    if not filtered:
        print(f"No {args.kind}s installed via okit.")
        return

    by_repo: dict[str, list] = {}
    for rec in filtered.values():
        by_repo.setdefault(rec.repo, []).append(rec)

    detail_map = {rec.name: rec for rec in filtered.values()} if args.detail else {}

    for repo_url in sorted(by_repo):
        repo_results = _build_installed_repo_results(repo_url, by_repo[repo_url])
        _render_installed_repo(repo_results, detail_map)


def cmd_update(args: argparse.Namespace) -> None:
    records = load_manifest()
    if not records:
        print("No artifacts tracked in manifest. Install something first.")
        return

    filter_skills = {n.strip() for n in args.skills.split(",")} if args.skills else None
    filter_agents = {n.strip() for n in args.agents.split(",")} if args.agents else None

    to_update = {
        key: rec for key, rec in records.items()
        if (filter_skills is None and filter_agents is None)
        or (rec.kind == "skill" and filter_skills and rec.name in filter_skills)
        or (rec.kind == "agent" and filter_agents and rec.name in filter_agents)
    }

    if not to_update:
        print("No matching tracked artifacts found.")
        return

    by_repo: dict[str, list] = {}
    for rec in to_update.values():
        by_repo.setdefault(rec.repo, []).append(rec)

    # First pass: clone repos, discover artifacts, collect updatable items
    updateable, repo_cache = _collect_updateable(by_repo)

    if not updateable:
        print("All up to date.")
        _cleanup_repo_cache(repo_cache)
        return

    has_filter_flags = bool(args.skills or args.agents)
    updateable = _apply_update_interactive_selection(updateable, has_filter_flags)
    if updateable is None:
        print("Cancelled.")
        _cleanup_repo_cache(repo_cache)
        return

    # Second pass: apply updates to selected items
    updated, skipped, errors = _apply_updates(updateable, repo_cache, args)
    _cleanup_repo_cache(repo_cache)

    _print_summary(updated, skipped, errors)
    if errors:
        sys.exit(1)


# Type alias for the updateable item tuple
_UpdateableItem = tuple["InstallRecord", object, "Path", str]  # (record, artifact, repo_path, repo_url)


def _collect_updateable(
    by_repo: dict[str, list],
) -> tuple[list[_UpdateableItem], dict[str, tuple["Path", bool]]]:
    """Clone repos and collect items that have content changes.

    Returns (updateable_items, repo_cache) where repo_cache maps repo_url → (path, is_temp).
    Caller is responsible for cleaning up repo_cache.
    """
    updateable: list[_UpdateableItem] = []
    repo_cache: dict[str, tuple[Path, bool]] = {}

    for repo_url, recs in by_repo.items():
        repo_path, is_temp = _resolve_source(repo_url, None)
        repo_cache[repo_url] = (repo_path, is_temp)
        available = {a.name: a for a in discover_all(repo_path)}

        for rec in recs:
            artifact = available.get(rec.name)
            if artifact is not None and check_update_available(rec, artifact.path):
                updateable.append((rec, artifact, repo_path, repo_url))

    return updateable, repo_cache


def _build_update_grouped_selector_data(updateable: list[_UpdateableItem]) -> list[dict]:
    """Build grouped selector structure from updateable items, grouped by repo → kind."""
    by_repo: dict[str, dict[str, list[tuple[int, str]]]] = {}
    for idx, (rec, _, _, repo_url) in enumerate(updateable):
        by_repo.setdefault(repo_url, {}).setdefault(rec.kind, []).append((idx, rec.name))

    groups = []
    for repo_url, by_kind in by_repo.items():
        children = [
            {"label": _KIND_LABELS.get(kind, kind.capitalize()), "items": items}
            for kind, items in by_kind.items()
        ]
        groups.append({"label": repo_url, "children": children})
    return groups


def _apply_update_interactive_selection(
    updateable: list[_UpdateableItem],
    has_filter_flags: bool,
) -> list[_UpdateableItem] | None:
    """Show interactive selector when appropriate; return filtered or full list.

    Returns None if the user cancels.
    """
    if has_filter_flags or not sys.stdin.isatty():
        return updateable

    groups = _build_update_grouped_selector_data(updateable)
    selected_indices = interactive_select_grouped(groups, header="Select artifacts to update")
    if selected_indices is None:
        return None
    return [updateable[i] for i in selected_indices]


def _apply_updates(
    updateable: list[_UpdateableItem],
    repo_cache: dict[str, tuple["Path", bool]],
    args: argparse.Namespace,
) -> tuple[int, int, int]:
    """Perform actual update installs and render results per-repo.

    Returns (updated, skipped, errors) counts.
    """
    updated = skipped = errors = 0

    by_repo_items: dict[str, list[_UpdateableItem]] = {}
    for item in updateable:
        by_repo_items.setdefault(item[3], []).append(item)

    all_repo_urls = {item[3] for item in updateable}
    for repo_url in all_repo_urls:
        repo_path, _ = repo_cache[repo_url]
        repo_result = RepoResults(repo=repo_url)

        for item in by_repo_items.get(repo_url, []):
            rec, artifact, _, _ = item

            if args.dry_run:
                repo_result.results.append(
                    ArtifactResult(name=rec.name, status="dry", detail="content changed", kind=rec.kind)
                )
                updated += 1
            else:
                new_commit = get_repo_commit(repo_path)
                ok, msg = install_artifact(
                    artifact,
                    repo_url=repo_url,
                    commit=new_commit,
                    force=True,
                )
                status = "up" if ok else "err"
                repo_result.results.append(
                    ArtifactResult(name=rec.name, status=status, detail="updated" if ok else msg, kind=rec.kind)
                )
                if ok:
                    updated += 1
                else:
                    errors += 1

        _render_repo_results(repo_result)

    return updated, skipped, errors


def _cleanup_repo_cache(repo_cache: dict[str, tuple["Path", bool]]) -> None:
    """Clean up all temporary repo clones from a repo cache."""
    for repo_path, is_temp in repo_cache.values():
        _cleanup_source(repo_path, is_temp)


# ---------------------------------------------------------------------------
# cmd_sync helpers
# ---------------------------------------------------------------------------

_SYNC_UPDATED = "updated"
_SYNC_NEW = "new"
_SYNC_UP_TO_DATE = "up-to-date"

_SyncItem = tuple[object, str, str, str]  # (artifact, repo_url, status, kind)


def _categorize_artifact(artifact, manifest_records: dict, repo_url: str) -> str:
    """Return the sync status for one discovered artifact."""
    record = manifest_records.get(manifest_key(artifact.kind, artifact.name))
    if record is None:
        return _SYNC_NEW
    if check_update_available(record, artifact.path):
        return _SYNC_UPDATED
    return _SYNC_UP_TO_DATE


def _collect_sync_items(
    by_repo: dict[str, list],
    manifest_records: dict,
) -> tuple[list[_SyncItem], dict[str, tuple["Path", bool]]]:
    """Clone each repo, discover all artifacts, and categorize each one.

    Returns (sync_items, repo_cache).  Caller cleans up repo_cache.
    Items are tuples of (artifact, repo_url, status, kind).
    Up-to-date items are included so callers can report totals.
    """
    sync_items: list[_SyncItem] = []
    repo_cache: dict[str, tuple[Path, bool]] = {}

    for repo_url in by_repo:
        repo_path, is_temp = _resolve_source(repo_url, None)
        repo_cache[repo_url] = (repo_path, is_temp)
        for artifact in discover_all(repo_path):
            status = _categorize_artifact(artifact, manifest_records, repo_url)
            sync_items.append((artifact, repo_url, status, artifact.kind))

    return sync_items, repo_cache


def _build_sync_selector_data(
    sync_items: list[_SyncItem],
) -> tuple[list[dict], set[int]]:
    """Build grouped selector data with status labels; return (groups, preselected_indices).

    Updated items are pre-checked; new items are unchecked; up-to-date items are excluded.
    """
    selectable = [
        (idx, item)
        for idx, item in enumerate(sync_items)
        if item[2] != _SYNC_UP_TO_DATE
    ]

    by_repo: dict[str, dict[str, list[tuple[int, str]]]] = {}
    preselected: set[int] = set()

    for selector_idx, (original_idx, (artifact, repo_url, status, kind)) in enumerate(selectable):
        label = f"{artifact.name} ({status})"
        by_repo.setdefault(repo_url, {}).setdefault(kind, []).append((selector_idx, label))
        if status == _SYNC_UPDATED:
            preselected.add(selector_idx)

    groups = []
    for repo_url, by_kind in by_repo.items():
        children = [
            {"label": _KIND_LABELS.get(kind, kind.capitalize()), "items": items}
            for kind, items in by_kind.items()
        ]
        groups.append({"label": repo_url, "children": children})

    return groups, preselected


def _resolve_sync_selection(
    sync_items: list[_SyncItem],
    apply_all: bool,
) -> list[_SyncItem] | None:
    """Return the items to install, applying interactive selection when appropriate.

    Returns None if the user cancels.
    """
    selectable = [item for item in sync_items if item[2] != _SYNC_UP_TO_DATE]
    if not selectable:
        return []

    if apply_all or not sys.stdin.isatty():
        return selectable

    groups, preselected = _build_sync_selector_data(sync_items)
    selected_indices = interactive_select_grouped(
        groups,
        header="Select artifacts to sync",
        preselected=preselected,
    )
    if selected_indices is None:
        return None

    return [selectable[i] for i in selected_indices]


def _apply_sync_installs(
    chosen: list[_SyncItem],
    repo_cache: dict[str, tuple["Path", bool]],
    args: argparse.Namespace,
) -> tuple[int, int, int]:
    """Install the chosen sync items and render results per-repo.

    Returns (installed, skipped, errors) counts.
    """
    installed = skipped = errors = 0

    by_repo: dict[str, list[_SyncItem]] = {}
    for item in chosen:
        _, repo_url, _, _ = item
        by_repo.setdefault(repo_url, []).append(item)

    for repo_url, items in by_repo.items():
        repo_path, _ = repo_cache[repo_url]
        repo_result = RepoResults(repo=repo_url)

        for artifact, _, status, kind in items:
            if args.dry_run:
                repo_result.results.append(
                    ArtifactResult(name=artifact.name, status="dry", detail=status, kind=kind)
                )
                installed += 1
                continue

            new_commit = get_repo_commit(repo_path)
            ok, msg = install_artifact(artifact, repo_url=repo_url, commit=new_commit, force=args.force)
            result_status = "ok" if ok else "skip"
            repo_result.results.append(
                ArtifactResult(name=artifact.name, status=result_status, detail=status if ok else msg, kind=kind)
            )
            if ok:
                installed += 1
            else:
                errors += 1

        _render_repo_results(repo_result)

    return installed, skipped, errors


def cmd_sync(args: argparse.Namespace) -> None:
    """Sync tracked repos: update existing artifacts and offer new ones."""
    manifest_records = load_manifest()
    if not manifest_records:
        print("Nothing tracked in manifest. Use 'okit install' to add a repo first.")
        return

    unique_repos = {rec.repo: [] for rec in manifest_records.values()}
    sync_items, repo_cache = _collect_sync_items(unique_repos, manifest_records)

    if not sync_items:
        print("No artifacts found in tracked repos.")
        _cleanup_repo_cache(repo_cache)
        return

    up_to_date_count = sum(1 for item in sync_items if item[2] == _SYNC_UP_TO_DATE)
    actionable_count = len(sync_items) - up_to_date_count

    if actionable_count == 0:
        print(f"All {up_to_date_count} artifact(s) up to date.")
        _cleanup_repo_cache(repo_cache)
        return

    apply_all = args.sync_all
    chosen = _resolve_sync_selection(sync_items, apply_all)

    if chosen is None:
        print("Cancelled.")
        _cleanup_repo_cache(repo_cache)
        return

    if not chosen:
        print("Nothing selected.")
        _cleanup_repo_cache(repo_cache)
        return

    installed, skipped, errors = _apply_sync_installs(chosen, repo_cache, args)
    _cleanup_repo_cache(repo_cache)

    _print_summary(installed, skipped, errors)
    if errors:
        sys.exit(1)


def cmd_validate(args: argparse.Namespace) -> None:
    if args.repo:
        root, is_temp = _resolve_source(args.repo, args.branch)
    else:
        root = Path(args.path).resolve()
        is_temp = False

    try:
        total_issues = 0

        skills = discover_skills(root)
        for skill in skills:
            issues = validate_skill(skill.path)
            if issues:
                print(f"  FAIL skill/{skill.name}:")
                for issue in issues:
                    print(f"    - {issue}")
                total_issues += len(issues)
            else:
                print(f"  OK   skill/{skill.name}")

        agents = discover_agents(root)
        for agent in agents:
            issues = validate_agent(agent.path)
            if issues:
                print(f"  FAIL agent/{agent.name}:")
                for issue in issues:
                    print(f"    - {issue}")
                total_issues += len(issues)
            else:
                print(f"  OK   agent/{agent.name}")

        if not skills and not agents:
            print("No skills or agents found at this path.")
            sys.exit(1)

        if total_issues:
            print(f"\n{total_issues} issue(s) found.")
            sys.exit(1)
        else:
            print(f"\nAll {len(skills) + len(agents)} artifact(s) valid.")
    finally:
        _cleanup_source(root, is_temp)


def cmd_doctor(args: argparse.Namespace) -> None:
    checks = []

    # Check git is available
    git_ok = shutil.which("git") is not None
    checks.append(("git available", git_ok))

    # Config + enabled providers
    cfg = okit_config.load()
    cfg_path = okit_config.config_path()
    checks.append((f"okit config exists ({cfg_path})", cfg_path.exists()))
    checks.append(
        (
            f"Enabled providers: {', '.join(cfg.enabled_providers) or '(none)'}",
            bool(cfg.enabled_providers),
        )
    )

    # Per-provider directory + binary checks
    for provider in ALL_PROVIDERS:
        enabled = cfg.is_enabled(provider.id)
        if not enabled:
            checks.append((f"[{provider.id}] disabled (run 'okit setup' to enable)", True))
            continue

        binary_ok = provider.is_available()
        checks.append((f"[{provider.id}] CLI '{provider.detect_command}' on PATH", binary_ok))

        s_dir = provider.skills_dir(None)
        a_dir = provider.agents_dir(None)
        checks.append((f"[{provider.id}] skills dir ({s_dir})", s_dir.is_dir()))
        checks.append((f"[{provider.id}] agents dir ({a_dir})", a_dir.is_dir()))

    # Manifest
    from okit.core import manifest_path as mp

    mpath = mp()
    checks.append((f"Manifest exists ({mpath})", mpath.exists()))

    print("okit doctor\n")
    all_ok = True
    for label, ok in checks:
        icon = "OK" if ok else "!!"
        print(f"  [{icon}] {label}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\nSome checks failed. Run 'okit setup' to configure providers, "
              "or 'okit install' to populate directories.")
        sys.exit(1)
    print("\nAll checks passed.")


def cmd_setup(args: argparse.Namespace) -> None:
    run_setup()


# --- Helpers ---


def _load_external_manifest(path: Path) -> dict[str, InstallRecord]:
    """Parse an external manifest file (v1 flat dict or v2 versioned format)."""
    raw = json.loads(path.read_text())
    artifacts = raw.get("artifacts", raw) if "version" in raw else raw
    return {
        key: InstallRecord(
            kind=val["kind"],
            name=val["name"],
            repo=val["repo"],
            commit=val.get("commit", ""),
            installed_at=val.get("installed_at", ""),
            description=val.get("description", ""),
            content_hash=val.get("content_hash", ""),
        )
        for key, val in artifacts.items()
    }


def _resolve_source(repo: str, branch: str | None) -> tuple[Path, bool]:
    """Resolve a repo arg to a local path. Returns (path, is_temp_clone)."""
    local = Path(repo).resolve()
    if local.is_dir():
        return local, False
    print(f"Fetching {repo}...")
    return clone_repo(repo, branch), True


def _cleanup_source(repo_path: Path, is_temp: bool) -> None:
    """Remove the temp clone directory if it was a clone."""
    if not is_temp:
        return
    tmp_root = repo_path
    while tmp_root.name != "repo" and tmp_root != tmp_root.parent:
        tmp_root = tmp_root.parent
    if tmp_root.parent.name.startswith("okit-"):
        shutil.rmtree(tmp_root.parent, ignore_errors=True)
    elif tmp_root.name == "repo":
        shutil.rmtree(tmp_root.parent, ignore_errors=True)


def _filter_by_kind(artifacts: list, kind: str) -> list:
    if kind == "all":
        return artifacts
    return [a for a in artifacts if a.kind == kind]


def _build_grouped_selector_data(artifacts: list, repo: str) -> list[dict]:
    """Build grouped selector structure from a flat artifact list for one repo."""
    by_kind: dict[str, list[tuple[int, str]]] = {}
    for idx, artifact in enumerate(artifacts):
        by_kind.setdefault(artifact.kind, []).append((idx, artifact.name))

    children = [
        {"label": _KIND_LABELS.get(kind, kind.capitalize()), "items": items}
        for kind, items in by_kind.items()
    ]
    return [{"label": repo, "children": children}]


def _apply_interactive_selection(artifacts: list, repo: str) -> list | None:
    """Show interactive selector if stdin is a TTY; return all artifacts otherwise.

    Returns None if the user cancels (Escape), or a list of chosen artifacts.
    """
    if not sys.stdin.isatty():
        return artifacts

    groups = _build_grouped_selector_data(artifacts, repo)
    selected_indices = interactive_select_grouped(groups, header=f"Select from {repo}")
    if selected_indices is None:
        return None
    return [artifacts[i] for i in selected_indices]


def _select_artifacts(artifacts: list, args: argparse.Namespace) -> list:
    if args.install_all:
        return artifacts

    selected = []
    if args.skills:
        names = {n.strip() for n in args.skills.split(",")}
        selected += [a for a in artifacts if a.kind == "skill" and a.name in names]
    if args.agents:
        names = {n.strip() for n in args.agents.split(",")}
        selected += [a for a in artifacts if a.kind == "agent" and a.name in names]
    return selected


def _describe_target(artifact, project: bool, project_dir: Path | None) -> str:
    """Render provider:path entries for dry-run output."""
    project_root = project_dir if project else None
    providers = okit_config.enabled_providers()
    parts = []
    for p in providers:
        for path in p.installed_paths(artifact.kind, artifact.name, project_dir=project_root):
            parts.append(f"{p.id}:{path}")
    return ", ".join(parts) if parts else "(no enabled provider)"


def _print_artifact_table(artifacts: list, *, detail: bool = False) -> None:
    skills = [a for a in artifacts if a.kind == "skill"]
    agents = [a for a in artifacts if a.kind == "agent"]

    if skills:
        print(f"\nSkills ({len(skills)}):")
        for a in skills:
            if detail:
                print(f"  {a.name}")
                print(f"    {a.description[:100]}")
            else:
                print(f"  {a.name}")

    if agents:
        print(f"\nAgents ({len(agents)}):")
        for a in agents:
            if detail:
                print(f"  {a.name}")
                print(f"    {a.description[:100]}")
            else:
                print(f"  {a.name}")

    print(f"\nTotal: {len(artifacts)} artifact(s)")


if __name__ == "__main__":
    main()
