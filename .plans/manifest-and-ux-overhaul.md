# Implementation Plan: Manifest & UX Overhaul

Spec: .specs/manifest-and-ux-overhaul.md

## Tasks

### T1 — Manifest path resolution via OKIT_MANIFEST env var

- **Files**: `okit/core.py`
- **Depends on**: none
- **Description**: Replace the hardcoded `manifest_path()` function to check `OKIT_MANIFEST` env var first. If set and non-empty, use that path. Otherwise use existing default. On write, create parent directories automatically.
- **Acceptance criteria**:
  - [ ] `manifest_path()` returns `Path(os.environ["OKIT_MANIFEST"])` when env var is set and non-empty
  - [ ] `manifest_path()` returns default `~/.config/opencode/okit-manifest.json` when env var is unset/empty
  - [ ] `save_manifest()` creates parent dirs of the resolved path (already does `path.parent.mkdir(parents=True)`)
  - [ ] `load_manifest()` treats non-existent env-specified file as empty dict (existing behavior)

---

### T2 — Manifest schema v2: version field, content_hash, multi-agent kind

- **Files**: `okit/core.py`
- **Depends on**: none
- **Description**: Evolve `InstallRecord` to include `content_hash` field (default `""`). Add `"multi-agent"` to `ArtifactKind`. Add `version: 2` to serialized manifest. On load, treat missing `version` as v1; backfill missing `content_hash` with `""`. On save, always write v2 format.
- **Acceptance criteria**:
  - [ ] `ArtifactKind` is `Literal["skill", "agent", "multi-agent"]`
  - [ ] `InstallRecord` has `content_hash: str` field (default `""`)
  - [ ] `save_manifest()` writes `{"version": 2, "artifacts": {...}}` structure
  - [ ] `load_manifest()` reads both v1 (flat dict) and v2 (versioned) formats
  - [ ] v1 records loaded with missing `content_hash` get `""`
  - [ ] File is NOT rewritten on disk during read-only sessions

---

### T3 — Content hash computation

- **Files**: `okit/core.py`
- **Depends on**: T2
- **Description**: Add `compute_content_hash(path: Path, kind: ArtifactKind) -> str` function. For skills and multi-agents (directories): sort all file paths relative to root, hash each file's bytes with sha256, then hash the concatenation of `"relpath:hexdigest\n"` lines. For single agents (files): sha256 of file content. Returns hex digest.
- **Acceptance criteria**:
  - [ ] Function is deterministic (sorted paths, consistent encoding)
  - [ ] Skills: hashes all files recursively in the skill directory
  - [ ] Agents: hashes single `.md` file content
  - [ ] Multi-agents: hashes all files recursively in the subdirectory
  - [ ] Uses only `hashlib.sha256` from stdlib

---

### T4 — Multi-agent discovery

- **Files**: `okit/core.py`
- **Depends on**: T2
- **Description**: Modify `discover_agents()` to also detect subdirectories under `agents/` as multi-agent artifacts. Directories become `kind="multi-agent"` with `name=dirname`. Standalone `.md` files remain single agents. Add to `discover_all()`.
- **Acceptance criteria**:
  - [ ] Subdirectories under `agents/` produce `Artifact(kind="multi-agent", name=dirname, path=dir_path)`
  - [ ] Standalone `.md` files remain `kind="agent"`
  - [ ] Both types returned from `discover_agents()` / `discover_all()`
  - [ ] `manifest_key()` works with `"multi-agent"` kind (produces `multi-agent:<name>`)

---

### T5 — Multi-agent install and remove

- **Files**: `okit/core.py`
- **Depends on**: T4
- **Description**: Extend `install_artifact()` to handle `kind="multi-agent"`: copy entire subdirectory to agents target dir (preserving structure). Extend `remove_artifact()` to delete the subdirectory for multi-agents.
- **Acceptance criteria**:
  - [ ] `install_artifact()` with multi-agent copies directory tree to `agents/<name>/`
  - [ ] `remove_artifact()` with multi-agent deletes `agents/<name>/` directory
  - [ ] Manifest record uses key `multi-agent:<name>`
  - [ ] `--force` overwrites existing multi-agent directory

---

### T6 — Content hash integration into install and update flows

- **Files**: `okit/core.py`
- **Depends on**: T3, T5
- **Description**: Modify `install_artifact()` to compute and store `content_hash` in the `InstallRecord`. Add a helper `check_update_available(record, new_artifact_path) -> bool` that compares content hashes, falling back to commit comparison when `content_hash` is empty (legacy).
- **Acceptance criteria**:
  - [ ] After install, manifest record has non-empty `content_hash`
  - [ ] `check_update_available()` returns False when content hashes match (even if commit differs)
  - [ ] `check_update_available()` returns True when content hashes differ
  - [ ] Legacy records (empty `content_hash`) fall back to commit comparison
  - [ ] On update, new `content_hash` is stored

---

### T7 — Install --manifest flag (CLI argument)

- **Files**: `okit/cli.py`
- **Depends on**: T1
- **Description**: Add `--manifest <file>` flag to the install subcommand. When provided: error if combined with positional repo arg, `--skills`, or `--agents`. Read the specified manifest file, install all its artifacts (using each record's `repo`), then update the user's active manifest. Error if file not found.
- **Acceptance criteria**:
  - [ ] `--manifest` flag added to install parser
  - [ ] Errors on mutual exclusion: `--manifest` + repo, `--manifest` + `--skills/--agents`
  - [ ] Reads external manifest file and installs all entries
  - [ ] User's own manifest is updated with installed records
  - [ ] `--dry-run` works with `--manifest`
  - [ ] File-not-found produces clear error

---

### T8 — Bare `okit install` (manifest-driven reinstall)

- **Files**: `okit/cli.py`
- **Depends on**: T7
- **Description**: Make the `repo` positional argument optional on the install subcommand. When no repo and no `--manifest` flag: read the user's active manifest, reinstall all entries from their recorded repos. Support `--force` and `--dry-run`. Group by repo to minimize clones. Error clearly on empty manifest.
- **Acceptance criteria**:
  - [ ] `repo` argument is `nargs="?"` (optional)
  - [ ] No repo + no `--manifest` + no `--skills/--agents` → manifest-driven reinstall
  - [ ] Groups entries by repo, clones once per repo
  - [ ] `--force` overwrites existing artifacts
  - [ ] `--dry-run` prints planned actions
  - [ ] Empty manifest prints "nothing is tracked"
  - [ ] Unreachable repo for one entry doesn't block others

---

### T9 — Update command uses content-hash detection

- **Files**: `okit/cli.py`
- **Depends on**: T6
- **Description**: Refactor `cmd_update()` to use `check_update_available()` instead of raw commit comparison. Show "up to date" when content hashes match. Compute and store new content hash on successful update.
- **Acceptance criteria**:
  - [ ] Update skips artifacts where content hash matches (no false positives from unrelated commits)
  - [ ] Update proceeds when content hash differs
  - [ ] Legacy records (no content_hash) fall back to commit comparison
  - [ ] New content_hash stored after successful update
  - [ ] Output messages reflect content-based detection

---

### T10 — Interactive terminal selector module

- **Files**: `okit/selector.py` (new file)
- **Depends on**: none
- **Description**: Create a new module implementing multi-select interactive UI using only `sys.stdin`, `tty`, `termios`. Features: arrow key navigation, space to toggle, enter to confirm, escape to cancel. Renders items with `[ ]`/`[x]` markers. Restores terminal state in a `finally` block. Returns list of selected items or `None` on escape.
- **Acceptance criteria**:
  - [ ] `interactive_select(items: list[str], header: str) -> list[int] | None` public API
  - [ ] Up/down arrow moves highlight
  - [ ] Space toggles selection
  - [ ] Enter returns selected indices
  - [ ] Escape returns None (cancel)
  - [ ] Terminal state always restored (finally block with `termios.tcsetattr`)
  - [ ] Only stdlib: `sys`, `tty`, `termios`

---

### T11 — Interactive mode integration into install

- **Files**: `okit/cli.py`
- **Depends on**: T8, T10
- **Description**: When `okit install <repo>` is invoked without `--all`, `--skills`, `--agents`, or `--manifest`: if stdin is a TTY, show interactive selector with discovered artifacts. If not a TTY, behave as `--all`. Interactive mode is skipped for bare install (manifest reinstall) and `--manifest`.
- **Acceptance criteria**:
  - [ ] Interactive selector shown when: repo given, no filter flags, stdin is TTY
  - [ ] Escape cancels with no changes
  - [ ] Selected items proceed to install
  - [ ] Non-TTY stdin falls back to `--all` behavior
  - [ ] `--all`, `--skills`, `--agents`, `--manifest`, bare install all skip interactive

---

### T12 — Interactive mode integration into update

- **Files**: `okit/cli.py`
- **Depends on**: T9, T10
- **Description**: When `okit update` is invoked without `--skills` or `--agents` flags: if stdin is a TTY and updatable artifacts exist, show interactive selector listing only artifacts with changes. If not a TTY, update all.
- **Acceptance criteria**:
  - [ ] Interactive selector shown when: no filter flags, stdin is TTY, updatable artifacts exist
  - [ ] Only artifacts with actual changes appear in selector
  - [ ] Selected items proceed to update
  - [ ] Non-TTY falls back to update-all
  - [ ] `--skills`/`--agents` flags skip interactive

---

### T13 — Clustered visual output for install/update

- **Files**: `okit/cli.py`
- **Depends on**: T4
- **Description**: Refactor output formatting in `cmd_install()` and `cmd_update()` to group results by repo → kind. Use Unicode box-drawing characters (U+2500 range) for repo headers and kind sub-headers. Apply to both real and `--dry-run` output.
- **Acceptance criteria**:
  - [ ] Results grouped: repo header → skills block → agents block → multi-agents block
  - [ ] Repo header uses box-drawing top border (e.g., `┌─ repo-name ─┐`)
  - [ ] Kind sub-sections have sub-headers (e.g., `├─ Skills`)
  - [ ] Single-repo operations still show repo header
  - [ ] `--dry-run` uses same clustering

---

### T14 — Clustered visual output for `installed` command

- **Files**: `okit/cli.py`
- **Depends on**: T13
- **Description**: Refactor `cmd_installed()` to cluster output by repo → kind using the same box-drawing formatting established in T13.
- **Acceptance criteria**:
  - [ ] Output grouped by repo then by kind
  - [ ] Uses same visual style as install/update output
  - [ ] `--detail` still shows expanded info within clustered layout
  - [ ] `--kind` filter still works within clustered display

---

## Execution Order

```
Parallel group 1 (no dependencies):
  [T1, T2, T10]

Parallel group 2 (depends on T2):
  [T3, T4]

Sequential from T4:
  T4 → T5

Sequential from T3 + T5:
  T6

Parallel group 3 (depends on T1 or T4):
  [T7, T13]

Sequential from T7:
  T7 → T8

Sequential from T6 + T8:
  T9

Sequential from T8 + T10:
  T11

Sequential from T9 + T10:
  T12

Sequential from T13:
  T14
```

**Critical path**: T2 → T3 → T6 → T9 → T12
**Maximum parallelism**: 3 tasks in first wave, 2 in second wave
