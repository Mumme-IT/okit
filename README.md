# okit

CLI for installing AI tool skills and agents from Git repositories into multiple target tools simultaneously.

## Install

```bash
# From git (recommended)
pipx install git+https://github.com/Mumme-IT/okit.git

# Or for development
git clone https://github.com/Mumme-IT/okit.git
cd okit
pip install -e .
```

## Usage

### List

Browse skills and agents in any compatible repo before installing.

```bash
okit list user/skills-and-agents           # summary view
okit list user/skills-and-agents --detail  # show descriptions
okit list user/skills-and-agents --kind skill  # filter by type: skill | agent
```

### Install

```bash
okit install user/skills-and-agents --all                          # everything
okit install user/skills-and-agents --skills clean-code,tests-expert  # named skills
okit install user/skills-and-agents --agents reviewer,planner      # named agents
okit install user/skills-and-agents --all --project                # project-local instead of global
okit install user/skills-and-agents --all --dry-run                # preview only
okit install --manifest path/to/manifest.json                      # from manifest file
```

### Inspect installed artifacts

```bash
okit installed           # list all installed skills and agents
okit installed --detail  # include source repo and install time
```

### Remove

```bash
okit remove --skills example-skill
okit remove --agents example-reviewer
okit remove --all --force  # remove everything without confirmation
```

### Update

Pull upstream changes for installed artifacts.

```bash
okit update                              # update all
okit update --skills clean-code,tests-expert  # named skills only
okit update --dry-run                    # preview changes
```

### Sync

Re-checks all tracked repos: updates changed artifacts and surfaces new ones.

```bash
okit sync           # interactive — confirm each new artifact
okit sync --all     # accept all new artifacts automatically
okit sync --dry-run # preview only
```

### Validate

Check that a repo or local directory is structured correctly for okit.

```bash
okit validate .                        # local directory
okit validate --repo user/skills-and-agents  # remote repo
```

### Doctor

```bash
okit doctor  # verify OpenCode setup and okit prerequisites
```

### Upgrade

Upgrade okit to the latest version via pipx:

```bash
pipx upgrade okit
```

## How it works

1. **Fetches** a git repo (shallow clone)
2. **Discovers** skills (`skills/<name>/SKILL.md`) and agents (`agents/<name>.md`)
3. **Installs** to every enabled provider's layout (see `okit setup`):
   - **OpenCode**: `~/.config/opencode/skills/<name>/`, `~/.config/opencode/agents/<name>.md`
   - **GitHub Copilot**: `~/.copilot/agents/<name>.agent.md` (project: `.github/agents/`)
   - **Claude Code**: `~/.claude/agents/<name>.md` (project: `.claude/agents/`)
   - **Windsurf**: `~/.codeium/windsurf/workflows/<name>.md` (agents installed as Workflows)
4. **Tracks** source repo, commit hash, install time, and provider list in a manifest

## Providers

okit can install to multiple AI tools at once. On first run it writes
`~/.config/okit/config.json` and auto-enables every provider whose CLI is on
PATH (`opencode`, `claude`, `copilot`, `surf`). Adjust the selection any time:

```bash
okit setup     # interactive provider selector
```

Per-provider quirks are encapsulated in `okit/providers/`. Adding a new target
is one new module + one entry in `ALL_PROVIDERS`.

| Provider | Global agents path | Agent filename | Multi-agent dirs | Notes |
| --- | --- | --- | --- | --- |
| OpenCode | `~/.config/opencode/agents/` | `<name>.md` | preserved | |
| GitHub Copilot | `~/.copilot/agents/` | `<name>.agent.md` | flattened | project: `.github/agents/` |
| Claude Code | `~/.claude/agents/` | `<name>.md` | preserved | strips `provider/` from model IDs |
| Windsurf | `~/.codeium/windsurf/workflows/` | `<name>.md` | flattened | agents installed as Workflows; no native agent concept |

## Content repo structure

Any git repo can be a source. Structure it like:

```
your-repo/
├── skills/
│   ├── my-skill/
│   │   └── SKILL.md
│   └── another-skill/
│       └── SKILL.md
└── agents/
    ├── reviewer.md
    └── planner.md
```

## Requirements

- Python 3.10+
- Git 2.25+
- No external Python dependencies (stdlib only)
