"""pi-agent provider — installs to ``~/.pi/`` or ``.pi/``.

pi-agent reads agents from a ``.pi/agents/`` directory, either project-local
or global under ``~/.pi/``. Skills have no native concept in pi-agent; they
are copied verbatim into ``.pi/skills/`` for lossless preservation.

Layout observed in the wild (mbot-rules repo):

    .pi/
    ├── agents/
    │   ├── reviewer.md          ← single-file agents
    │   ├── worker.md
    │   └── develop.chain.md     ← chain files live alongside agents
    └── settings.json

Agents use plain ``.md`` filenames (no ``.agent.md`` suffix).
Multi-agent groups are preserved as subdirectories (pi-agent recurses).

Global root: ``~/.pi/``
Project root: ``<project>/.pi/``

Detection command: ``pi``
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from okit.providers.base import Provider

if TYPE_CHECKING:
    from okit.core import Artifact, ArtifactKind


class PiAgentProvider(Provider):
    id = "piagent"
    display_name = "pi-agent"
    detect_command = "pi"

    # --- Paths ---

    def _global_root(self) -> Path:
        return Path.home() / ".pi"

    def _skills_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".pi" / "skills"
        return self._global_root() / "skills"

    def _agents_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".pi" / "agents"
        return self._global_root() / "agents"

    # --- Install ---

    def install_skill(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # pi-agent has no native skill concept; copy verbatim for preservation.
        target = self._skills_dir(project_dir) / artifact.name
        _copy_tree(artifact.path, target)
        return [target]

    def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        dest_dir = self._agents_dir(project_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{artifact.name}.md"
        shutil.copy2(artifact.path, dest)
        return [dest]

    def install_multi_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # pi-agent recurses into subdirectories — preserve the group as a folder.
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
