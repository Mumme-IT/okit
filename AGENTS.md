# okit

CLI for installing AI tool skills and agents from Git repositories into multiple target tools simultaneously.

## Architecture

- Language: Python 3.10+, stdlib-only except `prompt_toolkit` for TUI
- Pattern: thin CLI shell (`cli.py`) → core logic (`core.py`) → provider layer (`providers/`)
- Config: `~/.config/okit/config.json` — which providers are enabled
- Manifest: `~/.config/okit/manifest.json` — what was installed, from where, into which providers

## Modules

| Module | Path | Responsibility |
|---|---|---|
| CLI | `okit/cli.py` | Argument parsing, user-facing commands, output rendering |
| Core | `okit/core.py` | Git ops, artifact discovery, manifest I/O, install/remove orchestration |
| Config | `okit/config.py` | User config file, provider enable/disable, first-run auto-detection |
| Providers | `okit/providers/` | Per-tool install translation (paths, filenames, content transforms) |
| Selector | `okit/selector.py` | Hierarchical checkbox TUI (prompt_toolkit) |
| Setup | `okit/setup.py` | `okit setup` TUI — provider selection and future config screens |

## Provider Layer

The provider layer is the extension point for supporting new AI tools. Every tool has a different layout on disk — different directories, different filename conventions, different content formats. The provider layer isolates all of that.

### Contract

Each provider subclasses `Provider` (`okit/providers/base.py`) and implements three methods:

```python
def install_skill(artifact, *, project_dir) -> list[Path]
def install_agent(artifact, *, project_dir) -> list[Path]
def installed_paths(kind, name, *, project_dir) -> list[Path]
```

- `install_skill` / `install_agent` — own the full pipeline: destination directory, filename, and content. May copy verbatim, rename, reformat, or transform content entirely.
- `install_multi_agent` — optional override; default calls `install_agent` per member file.
- `installed_paths` — pure function returning what *would be* written for `(kind, name)`. Powers both dry-run output and `remove()`. Must be deterministic without filesystem access.
- `remove()` — provided by base; deletes every path from `installed_paths`. Override only for non-trivial cleanup.

### Registered providers

| ID | Class | Global root | Agent filename | Multi-agent |
|---|---|---|---|---|
| `opencode` | `OpencodeProvider` | `~/.config/opencode/` | `<name>.md` | subdirectory preserved |
| `copilot` | `CopilotProvider` | `~/.copilot/` | `<name>.agent.md` | flattened to agents root |
| `claudecode` | `ClaudeCodeProvider` | `~/.claude/` | `<name>.md` | subdirectory preserved |
| `windsurf` | `WindsurfProvider` | `~/.codeium/windsurf/` | `<name>.md` (as workflow) | flattened to workflows root |
| `piagent` | `PiAgentProvider` | `~/.pi/` | `<name>.md` | subdirectory preserved |

Project-scoped installs use `.opencode/` (OpenCode), `.github/` (Copilot), `.claude/` (Claude Code), `.windsurf/` (Windsurf), and `.pi/` (pi-agent).

**Provider notes:**
- `claudecode` — rewrites `model: provider/model-id` → `model: model-id` in frontmatter; recurses into multi-agent subdirectories.
- `windsurf` — no native agent concept; agents are installed as Workflows (`.windsurf/workflows/<name>.md`). Frontmatter is stripped and wrapped in a minimal Windsurf workflow envelope. Detect command: `surf`.
- `piagent` — no native skill concept; skills copied verbatim to `.pi/skills/`. Agents installed as plain `.md` files. Detect command: `pi`.

### Adding a provider

See [docs/contributing/adding-a-provider.md](docs/contributing/adding-a-provider.md).

## Key Entry Points

| Entry point | Path | Purpose |
|---|---|---|
| CLI main | `okit/cli.py:main` | Parses args, calls `ensure_initialized()`, dispatches commands |
| Install | `okit/core.py:install_artifact` | Loops enabled providers, calls `provider.install()`, writes manifest |
| Remove | `okit/core.py:remove_artifact` | Resolves providers from manifest record, calls `provider.remove()` |
| Auto-init | `okit/config.py:ensure_initialized` | Writes default config on first run, detecting available CLIs |

## Developer Notes

- Run: `mise run okit -- <args>` (auto-installs editable package on first run)
- Test: `mise run test`
- Install dev: `mise run okit:install` (or `pip install -e .[dev]`)
- Version bump: `mise run version:update <new_version>` (updates `pyproject.toml` + `okit/__init__.py`)
- Env overrides: `OKIT_CONFIG`, `OKIT_MANIFEST`, `XDG_CONFIG_HOME`
- New provider → new file in `okit/providers/` + one line in `ALL_PROVIDERS` (`okit/providers/__init__.py`)
