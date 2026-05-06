"""Claude Code provider — installs to ``~/.claude/`` or ``.claude/``."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from okit.providers.base import Provider

if TYPE_CHECKING:
    from okit.core import Artifact, ArtifactKind


def _filter_agent_content(text: str) -> str:
    """Normalise the model value in YAML frontmatter.

    Rewrites ``model: provider/model-id`` → ``model: model-id``.

    Only the YAML frontmatter block (between the first pair of ``---`` fences)
    is touched; the body is returned verbatim.
    """
    match = re.match(r"^(---\n)(.*?\n)(---\n)(.*)", text, re.DOTALL)
    if not match:
        return text

    fence_open, fm_body, fence_close, body = match.groups()
    filtered_lines: list[str] = []

    for line in fm_body.splitlines(keepends=True):
        key_match = re.match(r"^(model\s*:\s*)[^/\n]+/", line)
        if key_match:
            # Transform "provider/model-id" → "model-id".
            line = re.sub(r"^(model\s*:\s*)[^/\n]+/", r"\1", line)
        filtered_lines.append(line)

    return fence_open + "".join(filtered_lines) + fence_close + body


def _install_agent_file(src: Path, dest: Path) -> None:
    """Write *src* to *dest* with Claude Code-specific frontmatter filtering."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text(encoding="utf-8")
    dest.write_text(_filter_agent_content(content), encoding="utf-8")


class ClaudeCodeProvider(Provider):
    id = "claudecode"
    display_name = "Claude Code"
    detect_command = "claude"

    # --- Paths ---

    def _global_root(self) -> Path:
        return Path.home() / ".claude"

    def _skills_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".claude" / "skills"
        return self._global_root() / "skills"

    def _agents_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".claude" / "agents"
        return self._global_root() / "agents"

    # --- Install ---

    def install_skill(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        target = self._skills_dir(project_dir) / artifact.name
        _copy_tree(artifact.path, target)
        return [target]

    def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        dest_dir = self._agents_dir(project_dir)
        dest = dest_dir / f"{artifact.name}.md"
        _install_agent_file(artifact.path, dest)
        return [dest]

    def install_multi_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # Claude Code recurses into subdirectories: preserve the group as a folder.
        target = self._agents_dir(project_dir) / artifact.name
        _copy_tree(artifact.path, target)
        return [target]

    # --- Remove support ---

    def installed_paths(
        self,
        kind: "ArtifactKind",
        name: str,
        *,
        project_dir: Path | None,
    ) -> list[Path]:
        if kind == "skill":
            return [self._skills_dir(project_dir) / name]
        if kind == "multi-agent":
            return [self._agents_dir(project_dir) / name]
        return [self._agents_dir(project_dir) / f"{name}.md"]


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree, replacing dst when it already exists.

    Markdown files are filtered through ``_filter_agent_content`` to normalise
    frontmatter; all other files are copied verbatim.
    """
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_file():
            if item.suffix == ".md":
                content = item.read_text(encoding="utf-8")
                target.write_text(_filter_agent_content(content), encoding="utf-8")
            else:
                shutil.copy2(item, target)
        elif item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            _copy_tree(item, target)
