# Content Repo Structure

Any public or private git repository can be an okit source. Structure it like this:

```
your-repo/
├── skills/
│   ├── my-skill/
│   │   └── SKILL.md
│   └── another-skill/
│       └── SKILL.md
└── agents/
    ├── reviewer.md
    ├── planner.md
    └── team/               ← multi-agent group (subdirectory)
        ├── agent-a.md
        └── agent-b.md
```

## Skills

A skill is a directory under `skills/` containing a `SKILL.md` file. The directory name becomes the skill's identifier.

```
skills/
└── my-skill/
    └── SKILL.md       ← required; may include YAML frontmatter
```

Additional files in the skill directory are copied alongside `SKILL.md`.

## Agents

An agent is a single `.md` file directly under `agents/`. The filename (without extension) is the agent's identifier.

```
agents/
└── reviewer.md
```

## Multi-agent groups

A subdirectory under `agents/` is treated as a multi-agent group. All `.md` files inside it are members of the group.

```
agents/
└── team/
    ├── lead.md
    └── reviewer.md
```

Providers that support subdirectories preserve the group directory. Providers that do not (Copilot, Windsurf) flatten the members to their agents root.

## Frontmatter

`SKILL.md` and agent files may include YAML frontmatter. okit preserves it as-is, except:

- Claude Code strips the `provider/` prefix from `model:` values.
- Windsurf strips all frontmatter and wraps the body in a workflow envelope.

## Validating a repo

```bash
okit validate .                          # local checkout
okit validate --repo user/skills-and-agents  # remote
```
