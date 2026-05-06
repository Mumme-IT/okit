# Architecture

## Stack

- Language: Python 3.10+, stdlib-only except `prompt_toolkit` for the TUI
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

## Key entry points

| Entry point | Location | Purpose |
|---|---|---|
| CLI main | `okit/cli.py:main` | Parses args, calls `ensure_initialized()`, dispatches commands |
| Install | `okit/core.py:install_artifact` | Loops enabled providers, calls `provider.install()`, writes manifest |
| Remove | `okit/core.py:remove_artifact` | Resolves providers from manifest record, calls `provider.remove()` |
| Auto-init | `okit/config.py:ensure_initialized` | Writes default config on first run, detecting available CLIs |

## Provider layer

The provider layer is the extension point for supporting new AI tools. Every tool has a different layout on disk — different directories, filename conventions, and content formats. The provider layer isolates all of that.

Each provider subclasses `Provider` (`okit/providers/base.py`) and implements:

```python
def install_skill(artifact, *, project_dir) -> list[Path]
def install_agent(artifact, *, project_dir) -> list[Path]
def installed_paths(kind, name, *, project_dir) -> list[Path]
```

See [contributing/adding-a-provider.md](contributing/adding-a-provider.md) for the full contract and a step-by-step implementation guide.

## Developer workflow

```bash
mise run okit -- <args>          # run okit (auto-installs editable package on first run)
mise run test                    # run tests
mise run okit:install            # install editable package manually (pip install -e .[dev])
mise run version:update <x.y.z> # bump version in pyproject.toml + okit/__init__.py
```

Environment overrides: `OKIT_CONFIG`, `OKIT_MANIFEST`, `XDG_CONFIG_HOME`.

## Adding a provider

New file in `okit/providers/` + one line in `ALL_PROVIDERS` (`okit/providers/__init__.py`).  
See [contributing/adding-a-provider.md](contributing/adding-a-provider.md).
