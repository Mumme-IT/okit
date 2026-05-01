# okit

CLI for managing OpenCode skills and agents from Git repositories.

## Install

```bash
# From git (recommended)
pipx install git+ssh://git@git.mumme-it.de:2222/Mumme-IT/okit.git

# Or for development
git clone ssh://git@git.mumme-it.de:2222/Mumme-IT/okit.git
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

# Show what's installed
okit installed
okit installed --detail

# Remove artifacts
okit remove --skills example-skill
okit remove --agents example-reviewer
okit remove --all --force

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
