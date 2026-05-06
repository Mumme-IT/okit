# okit

CLI for installing AI tool skills and agents from Git repositories into multiple target tools simultaneously.

```bash
pipx install git+https://github.com/Mumme-IT/okit.git
```

## Quickstart

```bash
okit list user/skills-and-agents   # browse a repo
okit install user/skills-and-agents --all  # install everything
okit installed                     # see what is installed
```

## How it works

1. **Fetches** a git repo (shallow clone)
2. **Discovers** skills (`skills/<name>/SKILL.md`) and agents (`agents/<name>.md`)
3. **Installs** to every enabled provider simultaneously
4. **Tracks** source repo, commit hash, install time, and provider list in a manifest

On first run, okit auto-enables every provider whose CLI is on PATH. Use `okit setup` to adjust.

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | Install, first run, upgrade |
| [Commands](docs/commands.md) | Full CLI reference |
| [Providers](docs/providers.md) | Supported AI tools, install paths, quirks |
| [Content repo structure](docs/content-repo.md) | How to publish your own skills and agents |
| [Architecture](docs/architecture.md) | Codebase overview, module map, developer workflow |
| [Adding a provider](docs/contributing/adding-a-provider.md) | Extend okit to support a new AI tool |

## Requirements

- Python 3.10+
- Git 2.25+
- No external Python dependencies (stdlib only)
