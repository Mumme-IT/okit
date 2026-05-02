# Manifest & UX Overhaul

## Overview

Seven coordinated changes to okit's manifest format, install/update semantics, and terminal UX. Adds content-based change detection, multi-agent groups, interactive selection, manifest portability via env/flag, and clustered visual output — all stdlib-only.

## Implementation Mode

`main`

---

## User Stories

### Story 1 — Manifest-driven reinstall (sharing)

As a team member, I want to run `okit install` with no repo argument so that all artifacts from my manifest are reinstalled, enabling manifest sharing across machines.

#### Acceptance Criteria

- Given a manifest with 3 skills from repo A and 2 agents from repo B, when `okit install` is run with no positional repo argument and no `--skills`/`--agents`/`--all` flags, then all 5 artifacts are reinstalled from their recorded repos.
- Given a manifest entry whose repo is unreachable, when `okit install` (no args) runs, then that entry fails with a clear error and remaining entries still attempt installation.
- Given an empty manifest, when `okit install` (no args) runs, then a message indicates nothing is tracked.
- Given `--force` is passed alongside bare `okit install`, then existing artifacts are overwritten.
- Given `--dry-run` is passed, then no files are written but planned actions are printed.

---

### Story 2 — OKIT_MANIFEST environment variable

As a developer, I want to set `OKIT_MANIFEST` to redirect where okit reads/writes its manifest, so that I can use project-specific or shared manifests.

#### Acceptance Criteria

- Given `OKIT_MANIFEST=/tmp/team-manifest.json` is set, when any okit command reads or writes the manifest, then it uses `/tmp/team-manifest.json` instead of `~/.config/opencode/okit-manifest.json`.
- Given `OKIT_MANIFEST` is unset or empty, when okit runs, then the default path is used.
- Given `OKIT_MANIFEST` points to a non-existent file, when okit reads the manifest, then it treats it as empty (same as today's behavior for missing default file).
- Given `OKIT_MANIFEST` points to a non-existent parent directory, when okit writes the manifest, then parent directories are created automatically.

---

### Story 3 — Install --manifest flag

As a user, I want `okit install --manifest <file>` to install all artifacts from a specific manifest file, so that I can bootstrap from a teammate's exported manifest without changing my env.

#### Acceptance Criteria

- Given a valid manifest file at `/tmp/shared.json`, when `okit install --manifest /tmp/shared.json` is run, then all artifacts listed in that file are installed.
- Given `--manifest` is combined with a positional repo argument, then the command errors with a clear message (mutually exclusive).
- Given `--manifest` is combined with `--skills` or `--agents`, then the command errors (mutually exclusive with selective flags when using manifest source).
- Given the manifest file does not exist, then the command errors with "file not found".
- Given `--dry-run` is passed with `--manifest`, then planned installs are printed without writing files.
- Given `--manifest` installs succeed, when artifacts are written, then the user's own active manifest (default or `OKIT_MANIFEST`) is updated with the new records.

---

### Story 4 — Content-based hash replaces commit hash

As a user, I want `okit update` to detect actual content changes rather than commit-hash changes, so that unrelated repo commits don't trigger false "updates available."

#### Acceptance Criteria

- Given a skill directory with 3 files, when its content hash is computed, then the hash is deterministic: sorted file paths, each file's content hashed, then combined into a single digest.
- Given an agent file, when its content hash is computed, then the hash is the digest of that single file's content.
- Given a multi-agent directory (Story 5), when its content hash is computed, then all files in the directory tree are included (same algorithm as skills).
- Given a freshly installed artifact, when the manifest is written, then the record contains a `content_hash` field alongside `commit`.
- Given an artifact whose upstream commit changed but file content is identical, when `okit update` runs, then the artifact is reported as "up to date" (no reinstall).
- Given an artifact whose file content changed, when `okit update` runs, then the artifact is reported as updatable regardless of commit hash.
- Given a legacy manifest record without `content_hash`, when `okit update` runs, then it falls back to commit-hash comparison for that record and computes + stores the content hash on next install/update.

---

### Story 5 — Multi-agent group support

As a user, I want to install a directory of related agent files as a single "multi-agent" unit, so that agent groups (e.g., a pipeline with planner + executor) are managed atomically.

#### Acceptance Criteria

- Given a repo with `agents/wi-delivery-pipeline/planner.md` and `agents/wi-delivery-pipeline/executor.md`, when discovery runs, then a single artifact of kind `multi-agent` named `wi-delivery-pipeline` is produced.
- Given a multi-agent directory is installed, when the target is written, then the entire subdirectory is copied to the agents target directory (preserving internal structure).
- Given a multi-agent is installed, when `okit installed` lists it, then it displays as `multi-agent: wi-delivery-pipeline` (distinct from single `agent`).
- Given a multi-agent group and a standalone agent file coexist under `agents/`, when discovery runs, then both are discovered: directories become multi-agents, standalone `.md` files remain single agents.
- Given a multi-agent is removed, when `okit remove` runs, then the entire subdirectory is deleted atomically.
- Given a multi-agent's manifest key, then it follows the pattern `multi-agent:<name>`.
- Given `--agents <name>` references a multi-agent group name, then it matches correctly for install/update/remove operations.

---

### Story 6 — Clustered visual output

As a user, I want okit output grouped by repo then by kind with box-drawing structure, so that I can visually parse results faster.

#### Acceptance Criteria

- Given install/update results span 2 repos with mixed skills and agents, when output is printed, then results are grouped: repo header → skills block → agents block.
- Given a repo header is printed, then it uses a visually distinct format (box-drawing top border or indented heading).
- Given kind sub-sections within a repo, then a sub-header separates skills from agents (and multi-agents).
- Given a single-repo operation, then the repo header is still shown for consistency.
- Given `--dry-run` output, then the same clustering applies.
- Given the `installed` command output, then results are clustered by repo → kind.
- Given a terminal that doesn't support Unicode, when box-drawing is used, then the characters are standard Unicode box-drawing (U+2500 range) which degrade gracefully.

---

### Story 7 — Interactive selection (default for repo operations)

As a user, I want interactive multi-select when installing from a repo or updating, so that I can pick exactly which artifacts to act on without memorizing names for CLI flags.

#### Acceptance Criteria

- Given `okit install <repo>` with no `--all`, `--skills`, or `--agents` flags, when the command starts, then an interactive multi-select is displayed listing all discovered artifacts.
- Given the interactive selector is shown, when the user presses up/down arrows, then the highlight moves between items.
- Given the interactive selector is shown, when the user presses space, then the highlighted item is toggled (selected/deselected).
- Given the interactive selector is shown, when the user presses enter, then only selected items proceed to installation.
- Given the interactive selector is shown, when the user presses escape, then the operation is cancelled with no changes.
- Given `okit update` with no `--skills` or `--agents` flags, when updatable artifacts exist, then the interactive selector is shown with only the artifacts that have changes.
- Given `okit install --all <repo>`, then interactive mode is skipped — all artifacts are installed.
- Given `okit install --skills x,y <repo>`, then interactive mode is skipped — named artifacts are installed directly.
- Given `okit install --manifest <file>`, then interactive mode is skipped.
- Given `okit install` (bare, manifest-driven reinstall), then interactive mode is skipped.
- Given stdin is not a TTY (piped/scripted), then interactive mode is skipped and the command behaves as if `--all` was passed (or errors with guidance, depending on context).
- Given the implementation, then it uses only `sys.stdin`, `tty`, and `termios` modules (stdlib) for raw terminal input.

---

## Manifest Schema Evolution

### New manifest format (v2)

- Top-level `version` field (integer, value `2`).
- Records gain `content_hash` field (hex string).
- `kind` gains value `"multi-agent"` in addition to `"skill"` and `"agent"`.

### Migration

- Given a manifest without a `version` field, when okit loads it, then it is treated as version 1.
- Given a v1 manifest is loaded, when okit writes it back, then it is upgraded to v2 format (adding `version` and empty `content_hash` fields).
- Given a v1 manifest, when no write occurs during the session, then the file is not modified on disk.

---

## Dependencies

- External: git CLI (for cloning repos)
- Behavioral: existing manifest must exist for update/reinstall flows; TTY required for interactive mode

## Constraints

- Python stdlib only — no pip dependencies.
- Must work on Linux and macOS terminals (POSIX termios).
- Backward compatible: v1 manifests load without error and upgrade transparently on next write.
- Content hash algorithm must be deterministic across platforms (consistent sort order, consistent encoding).
- Interactive mode must restore terminal state on interrupt/crash (finally block with `termios.tcsetattr`).

## Out of Scope

- Windows terminal support for interactive mode.
- Color/ANSI escape codes in output (may be added later).
- Manifest encryption or signing.
- Conflict resolution when merging manifests from multiple sources.
- Remote manifest fetching (HTTP URL for manifest).
- Agent file format changes or new frontmatter fields.
