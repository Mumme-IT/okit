# Adding a Provider

Use this guide when adding support for a new AI tool target (e.g. Cursor, Zed, Cline).

---

## Step 1 — Research the tool

Find out:

1. **Where does it read agents/skills from?**
   - Global user directory (e.g. `~/.copilot/agents/`)
   - Project-local directory (e.g. `.github/agents/`)
   - Environment variables that override the paths

2. **What filename format does it expect?**
   - Specific suffix? (e.g. `.agent.md`, `.instructions.md`)
   - Case-sensitive? Character restrictions?

3. **Does it support agents?**
   - If not, decide: skip agents, or transform them into whatever the tool *does* support (e.g. a system prompt file, a config entry).

4. **Does it support a skills / instructions concept?**
   - If yes: what format and path?
   - If no: copy verbatim into a parallel folder (lossless preservation), or skip entirely.

5. **Does it recurse into subdirectories for agents?**
   - If not, multi-agent groups must be flattened.

Useful search queries:

```
"<toolname>" custom agents directory global config
"<toolname>" instructions skills prompt files path
"<toolname>" CLI changelog OR docs agents folder
site:github.com/<toolname-org>/<toolname-repo> agents
```

---

## Step 2 — Propose the mapping

Before writing code, state the mapping plainly:

> **Agents** → `~/.toolname/agents/<name>.md` (global), `.toolname/agents/<name>.md` (project)
> **Skills** → no native concept; copy verbatim to `~/.toolname/skills/<name>/` for preservation
> **Multi-agent groups** → flattened: each member becomes its own agent file
> **Filename rule** → plain `<name>.md`, no suffix required
> **Detection** → check for `toolname` binary on PATH

---

## Step 3 — Implement

### 3a. Create `okit/providers/<toolname>.py`

Subclass `Provider` from `okit/providers/base.py` and implement the three required methods:

```python
from __future__ import annotations
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from okit.providers.base import Provider

if TYPE_CHECKING:
    from okit.core import Artifact, ArtifactKind


class MyToolProvider(Provider):
    id = "mytool"
    display_name = "My Tool"
    detect_command = "mytool"   # binary probed by is_available()

    # --- Paths ---

    def _global_root(self) -> Path:
        return Path.home() / ".mytool"

    def _skills_dir(self, project_dir: Path | None) -> Path:
        root = project_dir / ".mytool" if project_dir else self._global_root()
        return root / "skills"

    def _agents_dir(self, project_dir: Path | None) -> Path:
        root = project_dir / ".mytool" if project_dir else self._global_root()
        return root / "agents"

    # --- install_skill ---
    # Own the full pipeline: destination, filename, content.

    def install_skill(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        target = self._skills_dir(project_dir) / artifact.name
        _copy_tree(artifact.path, target)
        return [target]

    # --- install_agent ---

    def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
        dest_dir = self._agents_dir(project_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{artifact.name}.md"
        shutil.copy2(artifact.path, dest)
        return [dest]

    # --- installed_paths ---
    # Pure function. No filesystem access. Must match exactly what install_* writes.

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
```

**Content transformation example** — tool has no agent concept, transform to a system prompt `.txt`:

```python
def install_agent(self, artifact: "Artifact", *, project_dir: Path | None) -> list[Path]:
    from okit.core import parse_frontmatter
    text = artifact.path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)        # strip YAML frontmatter
    dest_dir = self._agents_dir(project_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{artifact.name}.txt"
    dest.write_text(body.strip(), encoding="utf-8")
    return [dest]

def installed_paths(self, kind, name, *, project_dir):
    if kind == "agent":
        return [self._agents_dir(project_dir) / f"{name}.txt"]
    ...
```

### 3b. Register the provider

In `okit/providers/__init__.py`, add one import and one entry:

```python
from okit.providers.mytool import MyToolProvider   # add

ALL_PROVIDERS: list[Provider] = [
    OpencodeProvider(),
    CopilotProvider(),
    MyToolProvider(),   # add
]
```

The config, CLI, install/remove, doctor, and setup TUI all discover providers from `ALL_PROVIDERS` automatically.

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
