"""GitHub Copilot provider.

Copilot CLI reads custom agents from ``~/.copilot/agents/`` (global) and
``.github/agents/`` (repo-local). Rules:

  - Agent files MUST end in ``.agent.md``.
  - Agents MUST live directly under the agents root — no subdirectory recursion.
    Multi-agent groups are therefore *flattened*: each member .md becomes its
    own ``<member>.agent.md`` file in the root.

Copilot has no native concept of okit "skills". Skills are copied verbatim
into a parallel ``skills/`` directory (``~/.copilot/skills/`` or
``.github/skills/``). They are available for humans and other tooling; Copilot
itself ignores them.

References:
  https://docs.github.com/en/copilot/reference/custom-agents-configuration
  https://github.com/github/copilot-cli  (changelog confirms ~/.copilot/agents)
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from okit.providers.base import Provider

if TYPE_CHECKING:
    from okit.core import Artifact, ArtifactKind

# Frontmatter fields not recognised by Copilot — stripped on install.
_UNKNOWN_FIELDS = frozenset({"hidden", "permission", "target", "mode"})


def _filter_agent_content(text: str) -> str:
    """Strip unknown frontmatter fields and normalise the model value.

    - Removes top-level keys in ``_UNKNOWN_FIELDS`` *and* their indented block
      children (e.g. a ``permission:`` mapping with nested keys).
    - Rewrites ``model: provider/model-id`` → ``model: model-id``.

    Only the YAML frontmatter block (between the first pair of ``---`` fences)
    is touched; the body is returned verbatim.
    """
    match = re.match(r"^(---\n)(.*?\n)(---\n)(.*)", text, re.DOTALL)
    if not match:
        return text

    fence_open, fm_body, fence_close, body = match.groups()
    filtered_lines: list[str] = []
    skip_indented = False  # True while consuming block children of a dropped key

    for line in fm_body.splitlines(keepends=True):
        # A line that starts with whitespace is a block child of the previous key.
        if line and line[0] in (" ", "\t"):
            if skip_indented:
                continue
            filtered_lines.append(line)
            continue

        # Top-level key line (no leading whitespace).
        skip_indented = False
        key_match = re.match(r"^(\w+)\s*:", line)
        if not key_match:
            filtered_lines.append(line)
            continue

        key = key_match.group(1)
        if key in _UNKNOWN_FIELDS:
            skip_indented = True  # also drop indented children
            continue

        if key == "model":
            # Transform "provider/model-id" → "model-id".
            line = re.sub(r"^(model\s*:\s*)[^/\n]+/", r"\1", line)

        filtered_lines.append(line)

    return fence_open + "".join(filtered_lines) + fence_close + body


def _install_agent_file(src: Path, dest: Path) -> None:
    """Write *src* to *dest* with Copilot-specific frontmatter filtering."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text(encoding="utf-8")
    dest.write_text(_filter_agent_content(content), encoding="utf-8")


class CopilotProvider(Provider):
    id = "copilot"
    display_name = "GitHub Copilot"
    detect_command = "copilot"

    _AGENT_SUFFIX = ".agent.md"

    # --- Paths ---

    def _global_root(self) -> Path:
        return Path.home() / ".copilot"

    def _project_root(self, project_dir: Path) -> Path:
        return project_dir / ".github"

    def _skills_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return self._project_root(project_dir) / "skills"
        return self._global_root() / "skills"

    def _agents_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return self._project_root(project_dir) / "agents"
        return self._global_root() / "agents"

    def _agent_filename(self, name: str) -> str:
        # Idempotent: don't double-suffix a name that already ends in `.agent`.
        if name.endswith(".agent"):
            return f"{name}.md"
        return f"{name}{self._AGENT_SUFFIX}"

    # --- Install ---

    def install_skill(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # Copy verbatim — Copilot ignores this folder, but the files are
        # preserved losslessly for humans / future tooling.
        target = self._skills_dir(project_dir) / artifact.name
        _copy_tree(artifact.path, target)
        return [target]

    def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        dest_dir = self._agents_dir(project_dir)
        dest = dest_dir / self._agent_filename(artifact.name)
        _install_agent_file(artifact.path, dest)
        return [dest]

    def install_multi_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # Copilot cannot recurse into subdirectories, so flatten the group:
        # each member .md → <member>.agent.md directly under agents root.
        dest_dir = self._agents_dir(project_dir)
        written: list[Path] = []
        for member in sorted(artifact.path.iterdir()):
            if member.is_file() and member.suffix == ".md":
                dest = dest_dir / self._agent_filename(member.stem)
                _install_agent_file(member, dest)
                written.append(dest)
        return written

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
            # We can't reconstruct member filenames without scanning, so return
            # a sentinel that won't exist — remove() handles missing paths
            # gracefully. Callers that need full cleanup should scan the dir.
            return []
        return [self._agents_dir(project_dir) / self._agent_filename(name)]


def _copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_file():
            shutil.copy2(item, target)
        elif item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
