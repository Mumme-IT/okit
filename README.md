# okit

CLI for managing OpenCode skills and agents from Git repositories.

## Install

```bash
# From git (recommended)
pipx install git+https://git.mumme-it.de/Mumme-IT/okit.git

# Or for development
git clone https://git.mumme-it.de/Mumme-IT/okit.git
cd okit
pip install -e .
```

## Usage

```bash
# List available skills and agents in a repo
okit list user/skills-and-agents
okit list user/skills-and-agents --detail
okit list user/skills-and-agents --kind skill

# Install everything from a repo
okit install user/skills-and-agents --all

# Install specific items
okit install user/skills-and-agents --skills clean-code,tests-expert
okit install user/skills-and-agents --agents reviewer,planner

# Install to current project (instead of global)
okit install user/skills-and-agents --all --project

# Preview without installing
okit install user/skills-and-agents --all --dry-run

# Install from a manifest file
okit install --manifest path/to/manifest.json

# Show what's installed
okit installed
okit installed --detail

# Remove artifacts
okit remove --skills example-skill
okit remove --agents example-reviewer
okit remove --all --force

# Update artifacts that changed upstream
okit update
okit update --skills clean-code,tests-expert
okit update --dry-run

# Sync tracked repos: update existing, offer new artifacts
okit sync
okit sync --all
okit sync --dry-run

# Validate a local directory or remote repo
okit validate .
okit validate --repo user/skills-and-agents

# Check your OpenCode setup
okit doctor
```

## How it works

1. **Fetches** a git repo (shallow clone)
2. **Discovers** skills (`skills/<name>/SKILL.md`) and agents (`agents/<name>.md`)
3. **Installs** to OpenCode's config directories:
   - Skills → `~/.config/opencode/skills/<name>/SKILL.md`
   - Agents → `~/.config/opencode/agents/<name>.md`
4. **Tracks** source repo, commit hash, and install time in a manifest

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
