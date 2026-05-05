"""Provider base class — the contract every AI-tool target must implement.

The contract is deliberately minimal: two required methods, one optional.
A provider owns everything about how an artifact becomes a file on disk for
its target tool — paths, filenames, content transforms, format conversions.
The base class makes zero assumptions about copy vs. transform semantics.

Required:
    install_skill(artifact, project_dir)
    install_agent(artifact, project_dir)

Optional (override when multi-agent groups need special handling):
    install_multi_agent(artifact, project_dir)
    -- default: calls install_agent for each member file in the group.

Remove:
    installed_paths(kind, name, project_dir) -> list[Path]
    -- provider declares what was written; base remove() deletes those paths.
    -- override when removal is more complex (e.g. transformed filenames).

To add a new provider (e.g. Windsurf):
    1. Subclass Provider in okit/providers/windsurf.py.
    2. Implement install_skill + install_agent (transform content as needed).
    3. Implement installed_paths so remove() knows what to clean up.
    4. Append WindsurfProvider() to ALL_PROVIDERS in okit/providers/__init__.py.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from okit.core import Artifact, ArtifactKind


class Provider(ABC):
    """Translates okit artifacts into a target AI tool's on-disk representation.

    Subclasses own the full pipeline: where files go, what they are named,
    and what content they contain. Plain copy, rename, format conversion —
    all valid; the base class imposes nothing.
    """

    # --- Identity ---

    id: str = ""               # stable machine identifier, e.g. "opencode"
    display_name: str = ""     # human-facing label, e.g. "OpenCode"
    detect_command: str = ""   # binary probed by is_available(), e.g. "opencode"

    # --- Detection ---

    def is_available(self) -> bool:
        """Return True if the target tool's CLI binary is on PATH.

        Used to auto-enable providers on first run. Override for richer probes
        (e.g. checking a config file, a package manager, etc.).
        """
        if not self.detect_command:
            return False
        return shutil.which(self.detect_command) is not None

    # --- Required install entry-points ---

    @abstractmethod
    def install_skill(
        self,
        artifact: "Artifact",
        *,
        project_dir: Path | None,
    ) -> list[Path]:
        """Install a skill artifact. Returns every path written.

        The provider decides the destination directory, filename, and content.
        Written paths are stored in the manifest so remove() can clean up
        exactly the right files later.
        """

    @abstractmethod
    def install_agent(
        self,
        artifact: "Artifact",
        *,
        project_dir: Path | None,
    ) -> list[Path]:
        """Install a single-file agent. Returns every path written.

        The provider decides the destination directory, filename, and whether
        the agent content is transformed (e.g. converted to a different format).
        """

    # --- Optional multi-agent hook ---

    def install_multi_agent(
        self,
        artifact: "Artifact",
        *,
        project_dir: Path | None,
    ) -> list[Path]:
        """Install a multi-agent group. Returns every path written.

        Default: call install_agent for each .md member in the group directory.
        Override when the group should be installed atomically, flattened,
        ignored, or converted into a different structure entirely.
        """
        written: list[Path] = []
        for member in sorted(artifact.path.iterdir()):
            if member.is_file() and member.suffix == ".md":
                from okit.core import Artifact as _Artifact
                member_artifact = _Artifact(
                    kind="agent",
                    name=member.stem,
                    description=artifact.description,
                    path=member,
                    metadata=artifact.metadata,
                )
                written.extend(self.install_agent(member_artifact, project_dir=project_dir))
        return written

    # --- Remove support ---

    @abstractmethod
    def installed_paths(
        self,
        kind: "ArtifactKind",
        name: str,
        *,
        project_dir: Path | None,
    ) -> list[Path]:
        """Return all paths this provider would have written for this artifact.

        Used by remove() to delete exactly what was installed, and by dry-run
        output to show the user what *would* be written.

        Must be deterministic from (kind, name, project_dir) alone — i.e. no
        filesystem scanning. If the provider writes N files, return N paths.
        """

    def remove(
        self,
        kind: "ArtifactKind",
        name: str,
        *,
        project_dir: Path | None,
    ) -> tuple[bool, list[Path]]:
        """Delete every path this provider wrote for the artifact.

        Returns (any_removed, paths_that_existed_and_were_deleted).
        Providers with non-trivial removal (e.g. reverse-transform or
        per-group scanning) should override this method.
        """
        targets = self.installed_paths(kind, name, project_dir=project_dir)
        removed: list[Path] = []
        for target in targets:
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(target)
        return bool(removed), removed

    # --- Dispatch helper (called by core.install_artifact) ---

    def install(
        self,
        artifact: "Artifact",
        *,
        project_dir: Path | None,
    ) -> list[Path]:
        """Dispatch to the correct install_* method. Returns all written paths."""
        if artifact.kind == "skill":
            return self.install_skill(artifact, project_dir=project_dir)
        if artifact.kind == "multi-agent":
            return self.install_multi_agent(artifact, project_dir=project_dir)
        return self.install_agent(artifact, project_dir=project_dir)
