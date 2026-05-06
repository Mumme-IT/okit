# Providers

okit installs to every **enabled** provider simultaneously. On first run it auto-enables any provider whose CLI is on PATH. Change the active set at any time with `okit setup`.

## Supported providers

| ID | Tool | Detect command |
|---|---|---|
| `opencode` | OpenCode | `opencode` |
| `copilot` | GitHub Copilot | `copilot` |
| `claudecode` | Claude Code | `claude` |
| `windsurf` | Windsurf | `surf` |
| `piagent` | pi-agent | `pi` |

## Install paths

| Provider | Global skills | Global agents | Project skills | Project agents |
|---|---|---|---|---|
| OpenCode | `~/.config/opencode/skills/<name>/` | `~/.config/opencode/agents/<name>.md` | `.opencode/skills/<name>/` | `.opencode/agents/<name>.md` |
| GitHub Copilot | — | `~/.copilot/agents/<name>.agent.md` | — | `.github/agents/<name>.agent.md` |
| Claude Code | — | `~/.claude/agents/<name>.md` | — | `.claude/agents/<name>.md` |
| Windsurf | — | `~/.codeium/windsurf/workflows/<name>.md` | — | `.windsurf/workflows/<name>.md` |
| pi-agent | `~/.pi/skills/<name>/` | `~/.pi/agents/<name>.md` | `.pi/skills/<name>/` | `.pi/agents/<name>.md` |

## Provider notes

### GitHub Copilot

- Agent filename uses the `.agent.md` suffix.
- Multi-agent subdirectories are **flattened**: each member becomes a separate file at the agents root.

### Claude Code

- Rewrites `model: provider/model-id` → `model: model-id` in frontmatter (strips the provider prefix).
- Recurses into multi-agent subdirectories (preserved, not flattened).

### Windsurf

- No native agent concept. Agents are installed as **Workflows**.
- Frontmatter is stripped; content is wrapped in a minimal Windsurf workflow envelope.
- Multi-agent subdirectories are flattened to the workflows root.
- No native skill concept: skills are not installed.

### pi-agent

- No native skill concept: skills are copied verbatim to `.pi/skills/` for preservation.
- Agents are installed as plain `.md` files.

## Adding a new provider

See [contributing/adding-a-provider.md](contributing/adding-a-provider.md).
