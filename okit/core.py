"""Core library: git operations, artifact discovery, install/remove logic."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

SKILL_FILENAME = "SKILL.md"
FRONTMATTER_FENCE = "---"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ArtifactKind = Literal["skill", "agent"]


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
    return opencode_global_dir() / "okit-manifest.json"


# --- Manifest (source tracking) ---


def load_manifest() -> dict[str, InstallRecord]:
    path = manifest_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    records = {}
    for key, val in data.items():
        records[key] = InstallRecord(**val)
    return records


def save_manifest(records: dict[str, InstallRecord]) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for key, rec in records.items():
        data[key] = {
            "kind": rec.kind,
            "name": rec.name,
            "repo": rec.repo,
            "commit": rec.commit,
            "installed_at": rec.installed_at,
            "description": rec.description,
        }
    path.write_text(json.dumps(data, indent=2) + "\n")


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

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_file = entry / SKILL_FILENAME
        if not skill_file.exists():
            continue
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


def discover_agents(root: Path) -> list[Artifact]:
    """Find all valid agent markdown files in a directory tree."""
    agents_dir = root / "agents" if (root / "agents").is_dir() else root
    artifacts = []

    if not agents_dir.is_dir():
        return artifacts

    for entry in sorted(agents_dir.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        text = entry.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        desc = meta.get("description", "")
        if isinstance(desc, list):
            desc = " ".join(desc)
        name = entry.stem
        artifacts.append(
            Artifact(kind="agent", name=name, description=desc, path=entry, metadata=meta)
        )
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


# --- Install / Remove ---


def install_artifact(
    artifact: Artifact,
    *,
    project: bool = False,
    project_dir: Path | None = None,
    repo_url: str = "",
    commit: str = "",
    force: bool = False,
) -> tuple[bool, str]:
    """Install a single artifact to the target directory."""
    if artifact.kind == "skill":
        target_dir = (
            project_skills_dir(project_dir) if project and project_dir else global_skills_dir()
        )
        target = target_dir / artifact.name
    else:
        target_dir = (
            project_agents_dir(project_dir) if project and project_dir else global_agents_dir()
        )
        target = target_dir / f"{artifact.name}.md"

    if artifact.kind == "skill":
        if target.exists() and not force:
            return False, f"Already installed: {artifact.name} (use --force to overwrite)"
        target.mkdir(parents=True, exist_ok=True)
        # Copy entire skill directory
        for item in artifact.path.iterdir():
            dest = target / item.name
            if item.is_file():
                shutil.copy2(item, dest)
            elif item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
    else:
        if target.exists() and not force:
            return False, f"Already installed: {artifact.name} (use --force to overwrite)"
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact.path, target)

    # Update manifest
    if not project:
        records = load_manifest()
        key = manifest_key(artifact.kind, artifact.name)
        records[key] = InstallRecord(
            kind=artifact.kind,
            name=artifact.name,
            repo=repo_url,
            commit=commit,
            installed_at=datetime.now(timezone.utc).isoformat(),
            description=artifact.description[:200],
        )
        save_manifest(records)

    return True, f"Installed {artifact.kind}: {artifact.name}"


def remove_artifact(kind: ArtifactKind, name: str, *, project: bool = False, project_dir: Path | None = None) -> tuple[bool, str]:
    """Remove an installed artifact."""
    if kind == "skill":
        target_dir = project_skills_dir(project_dir) if project and project_dir else global_skills_dir()
        target = target_dir / name
    else:
        target_dir = project_agents_dir(project_dir) if project and project_dir else global_agents_dir()
        target = target_dir / f"{name}.md"

    if not target.exists():
        return False, f"Not found: {kind} '{name}'"

    if kind == "skill" and target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()

    # Update manifest
    if not project:
        records = load_manifest()
        key = manifest_key(kind, name)
        records.pop(key, None)
        save_manifest(records)

    return True, f"Removed {kind}: {name}"


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
