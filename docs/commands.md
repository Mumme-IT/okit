# Commands

## list

Browse skills and agents in a remote repo before installing.

```bash
okit list <repo>                    # summary view
okit list <repo> --detail           # include descriptions
okit list <repo> --kind skill       # filter: skill | agent
```

`<repo>` is a GitHub shorthand (`user/repo`) or a full git URL.

---

## install

```bash
okit install <repo> --all                          # everything
okit install <repo> --skills clean-code,tests-expert  # named skills
okit install <repo> --agents reviewer,planner      # named agents
okit install <repo> --all --project                # project-local instead of global
okit install <repo> --all --dry-run                # preview without writing files
okit install --manifest path/to/manifest.json      # replay a manifest file
```

Installs to every enabled provider simultaneously. Use `okit setup` to control which providers are active.

---

## installed

List everything okit has installed.

```bash
okit installed           # names only
okit installed --detail  # include source repo and install time
```

---

## remove

```bash
okit remove --skills example-skill
okit remove --agents example-reviewer
okit remove --all --force    # remove everything without confirmation
```

---

## update

Pull upstream changes for installed artifacts.

```bash
okit update                                    # update all
okit update --skills clean-code,tests-expert   # named skills only
okit update --dry-run                          # preview changes
```

---

## sync

Re-checks all tracked repos: updates changed artifacts and surfaces newly added ones.

```bash
okit sync            # interactive — confirm each new artifact
okit sync --all      # accept all new artifacts automatically
okit sync --dry-run  # preview only
```

---

## validate

Check that a directory or remote repo is structured correctly for okit.

```bash
okit validate .                          # local directory
okit validate --repo user/skills-and-agents  # remote repo
```

---

## setup

Interactive provider selector — choose which AI tools okit installs to.

```bash
okit setup
```

---

## doctor

Verify that okit prerequisites and enabled providers are correctly detected.

```bash
okit doctor
```
