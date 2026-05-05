"""OpenCode provider — installs to ``~/.config/opencode/`` or ``.opencode/``."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from okit.providers.base import Provider

if TYPE_CHECKING:
    from okit.core import Artifact, ArtifactKind


class OpencodeProvider(Provider):
    id = "opencode"
    display_name = "OpenCode"
    detect_command = "opencode"

    # --- Paths ---

    def _global_root(self) -> Path:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        return base / "opencode"

    def _skills_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".opencode" / "skills"
        return self._global_root() / "skills"

    def _agents_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".opencode" / "agents"
        return self._global_root() / "agents"

    def _agent_filename(self, name: str) -> str:
        return f"{name}.md"

    # --- Install ---

    def install_skill(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        target = self._skills_dir(project_dir) / artifact.name
        _copy_tree(artifact.path, target)
        return [target]

    def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        dest_dir = self._agents_dir(project_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / self._agent_filename(artifact.name)
        shutil.copy2(artifact.path, dest)
        return [dest]

    def install_multi_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        # OpenCode supports subdirectories: preserve the group as a folder.
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
        return [self._agents_dir(project_dir) / self._agent_filename(name)]


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
