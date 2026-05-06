"""Windsurf provider.

Windsurf (``~/.codeium/windsurf/``) supports three relevant artifact types:

  - **Skills** — stored as directories under ``~/.codeium/windsurf/skills/``
    (global) or ``.windsurf/skills/`` (project-local). Copied verbatim, matching
    the native Windsurf skill layout (a directory with ``SKILL.md`` + resources).

  - **Agents** — Windsurf has no native agent concept. Agents are installed as
    **Workflows**: ``.md`` files that Cascade invokes via ``/slash-command``.
    Global path: ``~/.codeium/windsurf/windsurf/workflows/<name>.md``
    Project path: ``.windsurf/workflows/<name>.md``

  - **Multi-agent groups** — flattened: each member ``.md`` becomes its own
    workflow file directly under the workflows root (no subdirectory recursion).

Filename normalisation: agent names ending in ``.agent`` (e.g. ``ama.agent``)
are stripped to their bare name (``ama``) so the Windsurf slash command is
``/ama``, not ``/ama.agent``.

Global root: ``~/.codeium/windsurf/``
Project root: ``<project>/.windsurf/``

References:
  https://docs.windsurf.com/windsurf/cascade/skills
  https://docs.windsurf.com/windsurf/cascade/workflows
  https://docs.windsurf.com/windsurf/cascade/memories
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from okit.providers.base import Provider

if TYPE_CHECKING:
    from okit.core import Artifact, ArtifactKind


def _agent_to_workflow(text: str, name: str) -> str:
    """Convert an agent markdown file to a Windsurf workflow.

    Strips YAML frontmatter and wraps the body in a Windsurf workflow file::

        ---
        description: <name or frontmatter description>
        ---

        <agent body>

    The ``description`` is sourced from the agent's frontmatter ``description``
    field when present; otherwise the agent ``name`` is used as a fallback.
    """
    match = re.match(r"^---\n(.*?\n)---\n(.*)", text, re.DOTALL)
    if match:
        fm_block, body = match.groups()
        # Extract description from frontmatter if present.
        desc_match = re.search(r"^description\s*:\s*(.+)", fm_block, re.MULTILINE)
        description = desc_match.group(1).strip().strip('"').strip("'") if desc_match else name
        body = body.lstrip("\n")
    else:
        description = name
        body = text.lstrip("\n")

    return f"---\ndescription: {description}\n---\n\n{body}"


def _install_workflow_file(src: Path, dest: Path, name: str) -> None:
    """Write *src* to *dest* as a Windsurf workflow."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text(encoding="utf-8")
    dest.write_text(_agent_to_workflow(content, name), encoding="utf-8")


class WindsurfProvider(Provider):
    id = "windsurf"
    display_name = "Windsurf"
    detect_command = "surf"

    # --- Paths ---

    def _global_root(self) -> Path:
        return Path.home() / ".codeium" / "windsurf"

    def _skills_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".windsurf" / "skills"
        return self._global_root() / "skills"

    def _workflows_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".windsurf" / "workflows"
        return self._global_root() / "windsurf" / "workflows"

    @staticmethod
    def _workflow_name(name: str) -> str:
        """Strip a trailing ``.agent`` suffix so ``ama.agent`` → ``ama``."""
        if name.endswith(".agent"):
            return name[: -len(".agent")]
        return name

    # --- Install ---

    def install_skill(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # Copy verbatim — Windsurf natively reads the skill directory, including
        # SKILL.md and any supporting resource files.
        target = self._skills_dir(project_dir) / artifact.name
        _copy_tree(artifact.path, target)
        return [target]

    def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # Windsurf has no native agent concept; install as a workflow instead.
        dest_dir = self._workflows_dir(project_dir)
        wf_name = self._workflow_name(artifact.name)
        dest = dest_dir / f"{wf_name}.md"
        _install_workflow_file(artifact.path, dest, wf_name)
        return [dest]

    def install_multi_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # Windsurf workflows cannot recurse into subdirectories, so flatten the
        # group: each member .md → <member>.md directly under workflows root.
        dest_dir = self._workflows_dir(project_dir)
        written: list[Path] = []
        for member in sorted(artifact.path.iterdir()):
            if member.is_file() and member.suffix == ".md":
                wf_name = self._workflow_name(member.stem)
                dest = dest_dir / f"{wf_name}.md"
                _install_workflow_file(member, dest, wf_name)
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
            # Multi-agent members are flattened; we can't reconstruct member
            # filenames without scanning, so return an empty list.
            # remove() handles missing paths gracefully.
            return []
        return [self._workflows_dir(project_dir) / f"{self._workflow_name(name)}.md"]


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree, replacing dst when it already exists."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_file():
            shutil.copy2(item, target)
        elif item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
