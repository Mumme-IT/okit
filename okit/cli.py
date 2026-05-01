"""CLI entry point — argparse commands for okit."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from okit import __version__
from okit.core import (
    ArtifactKind,
    clone_repo,
    discover_agents,
    discover_all,
    discover_skills,
    get_repo_commit,
    global_agents_dir,
    global_skills_dir,
    install_artifact,
    load_manifest,
    opencode_global_dir,
    remove_artifact,
    validate_agent,
    validate_skill,
)


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
    p_install.add_argument("repo", help="Git repo URL or user/repo shorthand")
    p_install.add_argument("--branch", help="Branch to clone")
    p_install.add_argument("--all", action="store_true", dest="install_all", help="Install everything")
    p_install.add_argument("--skills", help="Comma-separated skill names to install")
    p_install.add_argument("--agents", help="Comma-separated agent names to install")
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

    # --- doctor ---
    sub.add_parser("doctor", help="Check OpenCode directory structure and config")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "list": cmd_list,
        "install": cmd_install,
        "remove": cmd_remove,
        "installed": cmd_installed,
        "update": cmd_update,
        "validate": cmd_validate,
        "doctor": cmd_doctor,
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
    if not args.install_all and not args.skills and not args.agents:
        print("Error: specify --all, --skills, or --agents")
        sys.exit(1)

    repo_path, is_temp = _resolve_source(args.repo, args.branch)
    try:
        commit = get_repo_commit(repo_path)
        all_artifacts = discover_all(repo_path)

        to_install = _select_artifacts(all_artifacts, args)
        if not to_install:
            print("No matching artifacts found.")
            return

        project_dir = Path.cwd() if args.project else None

        for artifact in to_install:
            if args.dry_run:
                target = _describe_target(artifact, args.project, project_dir)
                print(f"  [dry-run] Would install {artifact.kind}: {artifact.name} → {target}")
            else:
                ok, msg = install_artifact(
                    artifact,
                    project=args.project,
                    project_dir=project_dir,
                    repo_url=args.repo,
                    commit=commit,
                    force=args.force,
                )
                status = "OK" if ok else "SKIP"
                print(f"  [{status}] {msg}")
    finally:
        _cleanup_source(repo_path, is_temp)


def cmd_remove(args: argparse.Namespace) -> None:
    if not args.remove_all and not args.skills and not args.agents:
        print("Error: specify --all, --skills, or --agents")
        sys.exit(1)

    project_dir = Path.cwd() if args.project else None
    items: list[tuple[ArtifactKind, str]] = []

    if args.remove_all:
        records = load_manifest()
        for key, rec in records.items():
            items.append((rec.kind, rec.name))
    else:
        if args.skills:
            for name in args.skills.split(","):
                items.append(("skill", name.strip()))
        if args.agents:
            for name in args.agents.split(","):
                items.append(("agent", name.strip()))

    if not items:
        print("Nothing to remove.")
        return

    if not args.force:
        print(f"Will remove {len(items)} artifact(s):")
        for kind, name in items:
            print(f"  {kind}: {name}")
        answer = input("Continue? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    for kind, name in items:
        ok, msg = remove_artifact(kind, name, project=args.project, project_dir=project_dir)
        status = "OK" if ok else "SKIP"
        print(f"  [{status}] {msg}")


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

    for key, rec in sorted(filtered.items()):
        if args.detail:
            print(f"  {rec.kind}: {rec.name}")
            print(f"    desc: {rec.description[:80]}")
            print(f"    repo: {rec.repo}")
            print(f"    commit: {rec.commit[:12]}")
            print(f"    installed: {rec.installed_at}")
        else:
            print(f"  {rec.kind}: {rec.name} — {rec.description[:60]}")


def cmd_update(args: argparse.Namespace) -> None:
    records = load_manifest()
    if not records:
        print("No artifacts tracked in manifest. Install something first.")
        return

    # Filter to requested names if provided
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

    # Group by source repo to avoid re-cloning the same repo multiple times
    by_repo: dict[str, list] = {}
    for rec in to_update.values():
        by_repo.setdefault(rec.repo, []).append(rec)

    updated = skipped = errors = 0

    for repo_url, recs in by_repo.items():
        repo_path, is_temp = _resolve_source(repo_url, None)
        try:
            new_commit = get_repo_commit(repo_path)
            available = {a.name: a for a in discover_all(repo_path)}

            for rec in recs:
                artifact = available.get(rec.name)
                if artifact is None:
                    print(f"  [MISS] {rec.kind}: {rec.name} — not found in {repo_url}")
                    errors += 1
                    continue

                if new_commit == rec.commit and new_commit != "unknown":
                    print(f"  [----] {rec.kind}: {rec.name} — already up to date ({new_commit[:12]})")
                    skipped += 1
                    continue

                if args.dry_run:
                    print(f"  [dry-run] Would update {rec.kind}: {rec.name} ({rec.commit[:12]} → {new_commit[:12]})")
                    updated += 1
                else:
                    ok, msg = install_artifact(
                        artifact,
                        repo_url=repo_url,
                        commit=new_commit,
                        force=True,
                    )
                    status = "UP" if ok else "ERR"
                    commit_range = f"{rec.commit[:12]} → {new_commit[:12]}"
                    print(f"  [{status}] {rec.kind}: {rec.name} ({commit_range})")
                    if ok:
                        updated += 1
                    else:
                        errors += 1
        finally:
            _cleanup_source(repo_path, is_temp)

    print(f"\n{updated} updated, {skipped} up to date, {errors} error(s).")
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

    # Check OpenCode config dir
    oc_dir = opencode_global_dir()
    checks.append((f"Config dir exists ({oc_dir})", oc_dir.is_dir()))

    # Check skills dir
    s_dir = global_skills_dir()
    checks.append((f"Skills dir exists ({s_dir})", s_dir.is_dir()))

    # Check agents dir
    a_dir = global_agents_dir()
    checks.append((f"Agents dir exists ({a_dir})", a_dir.is_dir()))

    # Check manifest
    from okit.core import manifest_path as mp

    mpath = mp()
    checks.append((f"Manifest exists ({mpath})", mpath.exists()))

    # Count installed
    skill_count = len(list(s_dir.iterdir())) if s_dir.is_dir() else 0
    agent_count = len([f for f in a_dir.iterdir() if f.suffix == ".md"]) if a_dir.is_dir() else 0
    checks.append((f"Skills installed: {skill_count}", True))
    checks.append((f"Agents installed: {agent_count}", True))

    print("okit doctor\n")
    all_ok = True
    for label, ok in checks:
        icon = "OK" if ok else "!!"
        print(f"  [{icon}] {label}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\nSome checks failed. Run 'okit install' to set up missing components.")
        sys.exit(1)
    print("\nAll checks passed.")


# --- Helpers ---


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
    if artifact.kind == "skill":
        base = global_skills_dir() if not project else project_dir / ".opencode" / "skills"
        return str(base / artifact.name)
    else:
        base = global_agents_dir() if not project else project_dir / ".opencode" / "agents"
        return str(base / f"{artifact.name}.md")


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
