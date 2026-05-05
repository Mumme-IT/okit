---
name: add-provider
description: Step-by-step workflow for adding a new AI tool provider to okit. Covers research, proposal, implementation, and registration.
---

# Add Provider

Use when adding support for a new AI tool target (e.g. Windsurf, Cursor, Zed).

---

## Step 1 — Research the tool

Web-search the tool to learn:

1. **Where does it read agents/skills from?** Look for:
   - A global user directory (e.g. `~/.copilot/agents/`, `~/.config/opencode/agents/`)
   - A project-local directory (e.g. `.github/agents/`, `.opencode/agents/`)
   - Environment variables that override the paths

2. **What filename format does it expect?**
   - Specific suffix required? (e.g. `.agent.md`, `.instructions.md`)
   - Case-sensitive? Character restrictions?

3. **Does it support agents at all?**
   - If not, decide: skip agents, or transform them into whatever the tool *does* support (e.g. a system prompt file, a config entry).

4. **Does it support a skills / instructions concept?**
   - If yes: what format and path?
   - If no: copy verbatim into a parallel folder (lossless preservation), or skip entirely.

5. **Does it recurse into subdirectories for agents?**
   - If no: multi-agent groups must be flattened.

Search queries to use:
- `"<toolname>" custom agents directory global config`
- `"<toolname>" instructions skills prompt files path`
- `"<toolname>" CLI changelog OR docs agents folder`
- `site:github.com/<toolname-org>/<toolname-repo> agents`

---

## Step 2 — Propose the mapping

Before writing code, state the mapping plainly. Example format:

> **Agents** → `~/.windsurf/agents/<name>.md` (global), `.windsurf/agents/<name>.md` (project)
> **Skills** → no native concept; copy verbatim to `~/.windsurf/skills/<name>/` for preservation
> **Multi-agent groups** → flattened: each member becomes its own agent file
> **Filename rule** → plain `<name>.md`, no suffix required
> **Detection** → check for `windsurf` binary on PATH

Get confirmation before implementing.

---

## Step 3 — Implement

### 3a. Create `okit/providers/<toolname>.py`

Subclass `Provider` from `okit/providers/base.py`. Implement exactly three required methods plus path helpers:

```python
from __future__ import annotations
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from okit.providers.base import Provider

if TYPE_CHECKING:
    from okit.core import Artifact, ArtifactKind


class WindsurfProvider(Provider):
    id = "windsurf"
    display_name = "Windsurf"
    detect_command = "windsurf"  # binary probed by is_available()

    # --- Paths ---

    def _global_root(self) -> Path:
        return Path.home() / ".windsurf"

    def _skills_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".windsurf" / "skills"
        return self._global_root() / "skills"

    def _agents_dir(self, project_dir: Path | None) -> Path:
        if project_dir is not None:
            return project_dir / ".windsurf" / "agents"
        return self._global_root() / "agents"

    # --- install_skill ---
    # Own the full pipeline: destination, filename, content.
    # Copy verbatim, rename, reformat, or produce a totally different format.

    def install_skill(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        target = self._skills_dir(project_dir) / artifact.name
        _copy_tree(artifact.path, target)
        return [target]

    # --- install_agent ---
    # Same ownership: you decide filename and content.
    # If the tool has no agent concept, transform the markdown into whatever it does use.

    def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        dest_dir = self._agents_dir(project_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{artifact.name}.md"
        shutil.copy2(artifact.path, dest)
        return [dest]

    # --- install_multi_agent (optional) ---
    # Default (from base): calls install_agent for each .md member.
    # Override when you need flattening, directory preservation, or a different structure.

    # def install_multi_agent(self, artifact, *, project_dir): ...

    # --- installed_paths ---
    # Pure function. Returns what WOULD be written for (kind, name).
    # Powers dry-run output AND remove(). No filesystem access allowed.
    # If install writes N files, return exactly N paths here.

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
            # If flattened: return [] here and override remove() with a dir scan.
            # If preserved as subdir: return [self._agents_dir(project_dir) / name]
            return [self._agents_dir(project_dir) / name]
        return [self._agents_dir(project_dir) / f"{name}.md"]
```

**Content transformation example** — tool has no agent concept, transform to a system prompt `.txt`:

```python
def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
    from okit.core import parse_frontmatter
    text = artifact.path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)        # strip YAML frontmatter
    dest_dir = self._agents_dir(project_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{artifact.name}.txt"  # tool expects .txt
    dest.write_text(body.strip(), encoding="utf-8")
    return [dest]

def installed_paths(self, kind, name, *, project_dir):
    if kind == "agent":
        return [self._agents_dir(project_dir) / f"{name}.txt"]  # matches install
    ...
```

### 3b. Register the provider

In `okit/providers/__init__.py`, add one line:

```python
from okit.providers.windsurf import WindsurfProvider   # add this import

ALL_PROVIDERS: list[Provider] = [
    OpencodeProvider(),
    CopilotProvider(),
    WindsurfProvider(),   # add this
]
```

That's it. The config, CLI, install/remove, doctor, and setup TUI all discover providers from `ALL_PROVIDERS` automatically.

---

## Provider contract reference

```
Provider (base class)
│
├── id: str                    — stable key, e.g. "opencode"
├── display_name: str          — shown in TUI + doctor output
├── detect_command: str        — binary checked by is_available()
│
├── is_available() -> bool     — PATH probe; override for richer checks
│
├── install_skill(artifact, *, project_dir) -> list[Path]    REQUIRED
├── install_agent(artifact, *, project_dir) -> list[Path]    REQUIRED
├── install_multi_agent(...)   -> list[Path]                 optional
│     └─ default: calls install_agent per .md member
│
├── installed_paths(kind, name, *, project_dir) -> list[Path]  REQUIRED
│     └─ deterministic, no filesystem access
│        must match exactly what install_* writes
│
└── remove(kind, name, *, project_dir) -> (bool, list[Path])
      └─ provided by base; deletes every path in installed_paths()
         override only for non-trivial cleanup (dir scans, etc.)
```

**Rules:**
- `installed_paths` must be a pure function — no `os.listdir`, no `Path.exists()`.
- Every path returned by `install_*` must appear in `installed_paths`.
- `install_*` is called after the force/skip check — overwrite unconditionally.
- `project_dir=None` means global install; `project_dir=Path(...)` means project-scoped.
