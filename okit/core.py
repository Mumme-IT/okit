"""Core library: git operations, artifact discovery, install/remove logic."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

SKILL_FILENAME = "SKILL.md"
FRONTMATTER_FENCE = "---"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ArtifactKind = Literal["skill", "agent", "multi-agent"]


@dataclass
class Artifact:
    kind: ArtifactKind
    name: str
    description: str
    path: Path
    metadata: dict = field(default_factory=dict)


@dataclass
class InstallRecord:
    kind: ArtifactKind
    name: str
    repo: str
    commit: str
    installed_at: str
    description: str
    content_hash: str = ""
    # Providers this artifact was installed into. Empty list = legacy record
    # from before multi-provider support; treated as ["opencode"] for compat.
    providers: list[str] = field(default_factory=list)


# --- Paths ---


def opencode_global_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "opencode"


def global_skills_dir() -> Path:
    return opencode_global_dir() / "skills"


def global_agents_dir() -> Path:
    return opencode_global_dir() / "agents"


def project_skills_dir(project: Path) -> Path:
    return project / ".opencode" / "skills"


def project_agents_dir(project: Path) -> Path:
    return project / ".opencode" / "agents"


def manifest_path() -> Path:
    env_path = os.environ.get("OKIT_MANIFEST", "")
    if env_path:
        return Path(env_path)
    from okit.config import config_dir

    return config_dir() / "manifest.json"


def project_manifest_path(project_dir: Path) -> Path:
    return project_dir / ".okit-manifest.json"


# --- Manifest (source tracking) ---


def load_manifest(project_dir: Path | None = None) -> dict[str, InstallRecord]:
    path = project_manifest_path(project_dir) if project_dir else manifest_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    artifacts = raw.get("artifacts", raw) if "version" in raw else raw
    return {key: _record_from_dict(val) for key, val in artifacts.items()}


def _record_from_dict(val: dict) -> InstallRecord:
    return InstallRecord(
        kind=val["kind"],
        name=val["name"],
        repo=val["repo"],
        commit=val["commit"],
        installed_at=val["installed_at"],
        description=val["description"],
        content_hash=val.get("content_hash", ""),
        providers=list(val.get("providers", [])),
    )


def save_manifest(records: dict[str, InstallRecord], project_dir: Path | None = None) -> None:
    path = project_manifest_path(project_dir) if project_dir else manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {
        key: {
            "kind": rec.kind,
            "name": rec.name,
            "repo": rec.repo,
            "commit": rec.commit,
            "installed_at": rec.installed_at,
            "description": rec.description,
            "content_hash": rec.content_hash,
            "providers": list(rec.providers),
        }
        for key, rec in records.items()
    }
    payload = {"version": 2, "artifacts": artifacts}
    path.write_text(json.dumps(payload, indent=2) + "\n")


def manifest_key(kind: ArtifactKind, name: str) -> str:
    return f"{kind}:{name}"


# --- Frontmatter parsing ---


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-ish frontmatter from markdown. Stdlib-only, no PyYAML."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return {}, text

    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == FRONTMATTER_FENCE:
            end_idx = i
            break
    if end_idx == -1:
        return {}, text

    fm_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :])
    meta = _parse_yaml_simple(fm_lines)
    return meta, body


def _parse_yaml_simple(lines: list[str]) -> dict:
    """Minimal YAML parser for flat key-value pairs and simple nested structures."""
    result = {}
    current_key = None
    current_value_lines: list[str] = []
    multiline = False

    for line in lines:
        if not line.strip():
            if multiline:
                current_value_lines.append("")
            continue

        # Check if this is a top-level key
        if not line[0].isspace() and ":" in line:
            # Save previous multiline value
            if multiline and current_key:
                result[current_key] = "\n".join(current_value_lines).strip()
                multiline = False

            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            if value == "" or value == ">":
                current_key = key
                current_value_lines = []
                multiline = True
            elif value == "true":
                result[key] = True
            elif value == "false":
                result[key] = False
            else:
                # Strip quotes
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                result[key] = value
        elif multiline and current_key:
            stripped = line.strip()
            # Handle list items
            if stripped.startswith("- "):
                item = stripped[2:].strip()
                if (item.startswith('"') and item.endswith('"')) or (
                    item.startswith("'") and item.endswith("'")
                ):
                    item = item[1:-1]
                if current_key not in result:
                    result[current_key] = []
                if isinstance(result.get(current_key), list):
                    result[current_key].append(item)
                else:
                    current_value_lines.append(stripped)
            else:
                current_value_lines.append(stripped)

    # Final multiline value
    if multiline and current_key and current_key not in result:
        result[current_key] = "\n".join(current_value_lines).strip()

    return result


# --- Discovery ---


def discover_skills(root: Path) -> list[Artifact]:
    """Find all valid skills in a directory tree."""
    skills_dir = root / "skills" if (root / "skills").is_dir() else root
    artifacts = []

    if not skills_dir.is_dir():
        return artifacts

    for skill_file in sorted(skills_dir.rglob(SKILL_FILENAME)):
        entry = skill_file.parent
        text = skill_file.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        name = meta.get("name", entry.name)
        desc = meta.get("description", "")
        if isinstance(desc, list):
            desc = " ".join(desc)
        artifacts.append(
            Artifact(kind="skill", name=name, description=desc, path=entry, metadata=meta)
        )
    return artifacts


def _extract_multi_agent_description(dir_path: Path) -> str:
    """Extract description from README.md or first .md file's frontmatter in a directory."""
    candidates = [dir_path / "README.md"] + sorted(
        p for p in dir_path.iterdir() if p.is_file() and p.suffix == ".md" and p.name != "README.md"
    )
    for md_file in candidates:
        if not md_file.exists():
            continue
        meta, _ = parse_frontmatter(md_file.read_text(encoding="utf-8"))
        desc = meta.get("description", "")
        if isinstance(desc, list):
            desc = " ".join(desc)
        if desc:
            return desc
    return f"Multi-agent group: {dir_path.name}"


def _discover_agent_file(entry: Path) -> Artifact:
    """Build an Artifact for a standalone agent .md file."""
    text = entry.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(text)
    desc = meta.get("description", "")
    if isinstance(desc, list):
        desc = " ".join(desc)
    return Artifact(kind="agent", name=entry.stem, description=desc, path=entry, metadata=meta)


def _discover_multi_agent_dir(entry: Path) -> Artifact | None:
    """Build an Artifact for a subdirectory containing at least one .md file."""
    md_files = [p for p in entry.iterdir() if p.is_file() and p.suffix == ".md"]
    if not md_files:
        return None
    desc = _extract_multi_agent_description(entry)
    return Artifact(kind="multi-agent", name=entry.name, description=desc, path=entry)


def discover_agents(root: Path) -> list[Artifact]:
    """Find all valid agent artifacts (standalone .md files and multi-agent subdirs)."""
    agents_dir = root / "agents" if (root / "agents").is_dir() else root
    artifacts = []

    if not agents_dir.is_dir():
        return artifacts

    for entry in sorted(agents_dir.iterdir()):
        if entry.is_file() and entry.name.endswith(".md"):
            artifacts.append(_discover_agent_file(entry))
        elif entry.is_dir():
            artifact = _discover_multi_agent_dir(entry)
            if artifact:
                artifacts.append(artifact)

    return artifacts


def discover_all(root: Path) -> list[Artifact]:
    return discover_skills(root) + discover_agents(root)


# --- Git operations ---


def clone_repo(repo_url: str, branch: str | None = None) -> Path:
    """Clone a repo to a temp directory. Returns the path."""
    clone_url, subdir = _parse_repo_url(repo_url)
    tmp = Path(tempfile.mkdtemp(prefix="okit-"))
    cmd = ["git", "clone", "--depth=1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [clone_url, str(tmp / "repo")]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

    repo_path = tmp / "repo"
    if subdir:
        repo_path = repo_path / subdir

    return repo_path


def get_repo_commit(repo_path: Path) -> str:
    """Get the HEAD commit hash of a cloned repo."""
    git_dir = repo_path
    while git_dir != git_dir.parent:
        if (git_dir / ".git").exists():
            break
        git_dir = git_dir.parent

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=git_dir,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _parse_repo_url(url: str) -> tuple[str, str]:
    """Parse repo URL, extracting subdirectory if present (GitHub tree format)."""
    # Handle: https://github.com/user/repo/tree/branch/subdir
    tree_match = re.match(
        r"(https?://[^/]+/[^/]+/[^/]+)/tree/[^/]+/(.*)", url
    )
    if tree_match:
        base = tree_match.group(1)
        subdir = tree_match.group(2)
        return base + ".git", subdir

    # Handle shorthand: user/repo
    if re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", url):
        return f"https://github.com/{url}.git", ""

    # Handle full URLs without tree
    if not url.endswith(".git"):
        return url + ".git", ""

    return url, ""


def _hash_directory(path: Path) -> str:
    """sha256 over sorted relative-path:digest lines for all files in a directory tree."""
    file_hashes = []
    for file_path in sorted(path.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(path).as_posix()
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        file_hashes.append(f"{rel}:{digest}\n")
    combined = "".join(file_hashes).encode()
    return hashlib.sha256(combined).hexdigest()


def _hash_file(path: Path) -> str:
    """sha256 of a single file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_content_hash(path: Path, kind: ArtifactKind) -> str:
    """Deterministic content hash for an installed artifact."""
    if kind in ("skill", "multi-agent"):
        return _hash_directory(path)
    return _hash_file(path)


# --- Install / Remove ---


def install_artifact(
    artifact: Artifact,
    *,
    project: bool = False,
    project_dir: Path | None = None,
    repo_url: str = "",
    commit: str = "",
    force: bool = False,
    providers: "list | None" = None,
) -> tuple[bool, str]:
    """Install an artifact to every enabled provider's layout.

    Each provider owns the full story — paths, filenames, content transforms.
    The manifest tracks which providers received this artifact so removal can
    clean up exactly the right locations.

    ``providers`` defaults to whatever ``okit.config`` reports as enabled.
    Pass an explicit list to scope installation (used by tests and by the
    setup TUI when applying a freshly-changed provider list).
    """
    from okit.config import enabled_providers

    targets = providers if providers is not None else enabled_providers()
    if not targets:
        return False, f"No enabled provider: {artifact.kind}: {artifact.name}"

    project_root = project_dir if project else None
    installed_provider_ids: list[str] = []
    skipped_messages: list[str] = []

    for provider in targets:
        # Use installed_paths to check for prior install (pre-write, so no
        # scanning needed — just deterministic path calculation).
        prior_paths = provider.installed_paths(artifact.kind, artifact.name, project_dir=project_root)
        if prior_paths and any(p.exists() for p in prior_paths) and not force:
            skipped_messages.append(
                f"{provider.id}: already installed (use --force to overwrite)"
            )
            continue
        provider.install(artifact, project_dir=project_root)
        installed_provider_ids.append(provider.id)

    if not installed_provider_ids:
        return False, skipped_messages[0] if skipped_messages else "No providers installed"

    records = load_manifest(project_dir) if project else load_manifest()
    key = manifest_key(artifact.kind, artifact.name)
    existing = records.get(key)
    prior_providers = list(existing.providers) if existing else []
    merged_providers = sorted(set(prior_providers) | set(installed_provider_ids))
    records[key] = InstallRecord(
        kind=artifact.kind,
        name=artifact.name,
        repo=repo_url,
        commit=commit,
        installed_at=datetime.now(timezone.utc).isoformat(),
        description=artifact.description[:200],
        content_hash=compute_content_hash(artifact.path, artifact.kind),
        providers=merged_providers,
    )
    save_manifest(records, project_dir) if project else save_manifest(records)

    detail = f"{artifact.kind}: {artifact.name} → {', '.join(installed_provider_ids)}"
    return True, f"Installed {detail}"


def check_update_available(record: InstallRecord, new_artifact_path: Path) -> bool:
    """Return True if new_artifact_path differs from the installed record.

    Falls back to True for legacy records without a content_hash so that
    callers always attempt an update rather than silently skipping it.
    """
    if not record.content_hash:
        return True
    new_hash = compute_content_hash(new_artifact_path, record.kind)
    return new_hash != record.content_hash


def remove_artifact(
    kind: ArtifactKind,
    name: str,
    *,
    project: bool = False,
    project_dir: Path | None = None,
    providers: "list | None" = None,
) -> tuple[bool, str]:
    """Remove an installed artifact from every provider that holds it.

    For global removal, providers are taken from the manifest record (so we
    clean up exactly where we previously installed). For project removal,
    we ask every currently-enabled provider — there's no per-project record.
    """
    from okit.config import enabled_providers
    from okit.providers import PROVIDERS_BY_ID, Provider

    project_root = project_dir if project else None

    # Decide which providers to ask.
    record: InstallRecord | None = None
    manifest_project_dir = project_dir if project else None
    records = load_manifest(manifest_project_dir)
    if not project:
        record = records.get(manifest_key(kind, name))

    if providers is not None:
        targets: list[Provider] = providers
    elif record is not None and record.providers:
        targets = [PROVIDERS_BY_ID[pid] for pid in record.providers if pid in PROVIDERS_BY_ID]
    else:
        # Legacy record (pre-providers field) or project install: try all enabled.
        targets = enabled_providers()

    removed_any = False
    removed_count = 0
    for provider in targets:
        ok, paths = provider.remove(kind, name, project_dir=project_root)
        if ok:
            removed_any = True
            removed_count += len(paths)

    if not removed_any:
        return False, f"Not found: {kind} '{name}'"

    records.pop(manifest_key(kind, name), None)
    save_manifest(records, manifest_project_dir)

    return True, f"Removed {kind}: {name} ({removed_count} file(s) deleted)"


# --- Validation ---


def validate_skill(path: Path) -> list[str]:
    """Validate a skill directory. Returns list of issues."""
    issues = []
    skill_file = path / SKILL_FILENAME

    if not skill_file.exists():
        issues.append(f"Missing {SKILL_FILENAME}")
        return issues

    text = skill_file.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(text)

    if "name" not in meta:
        issues.append("Missing required frontmatter field: name")
    elif not NAME_PATTERN.match(meta["name"]):
        issues.append(f"Invalid name '{meta['name']}' — must be lowercase alphanumeric with hyphens")
    elif meta["name"] != path.name:
        issues.append(f"Name mismatch: frontmatter says '{meta['name']}' but directory is '{path.name}'")

    if "description" not in meta:
        issues.append("Missing required frontmatter field: description")
    elif isinstance(meta["description"], str) and len(meta["description"]) > 1024:
        issues.append("Description exceeds 1024 characters")

    return issues


def validate_agent(path: Path) -> list[str]:
    """Validate an agent markdown file. Returns list of issues."""
    issues = []

    if not path.exists():
        issues.append(f"File not found: {path}")
        return issues

    text = path.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(text)

    if "description" not in meta:
        issues.append("Missing required frontmatter field: description")

    return issues
