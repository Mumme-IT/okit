# Getting Started

## Requirements

- Python 3.10+
- Git 2.25+
- No external Python dependencies (stdlib only)

## Install

```bash
# From git (recommended)
pipx install git+https://github.com/Mumme-IT/okit.git
```

For development:

```bash
git clone https://github.com/Mumme-IT/okit.git
cd okit
pip install -e .[dev]
```

## First run

On first run, okit writes `~/.config/okit/config.json` and auto-enables every provider whose CLI is already on PATH (`opencode`, `claude`, `copilot`, `surf`, `pi`).

To review or change the active providers:

```bash
okit setup
```

## Quickstart

```bash
# Browse what a repo offers before installing
okit list user/skills-and-agents

# Install everything from a repo to all enabled providers
okit install user/skills-and-agents --all

# See what is installed
okit installed
```

## Upgrade

```bash
pipx upgrade okit
```

## Next steps

- [Commands reference](commands.md) — full CLI usage
- [Providers](providers.md) — where files land for each AI tool
- [Content repo structure](content-repo.md) — how to publish your own skills and agents
