"""Tests for the provider abstraction and config layer.

Focus: the things that would break silently in production.
- Filename transforms (the .agent.md rule is the entire point of Copilot support).
- Multi-agent flattening (Copilot can't recurse).
- Multi-target install writes one copy per provider with the right names.
- Config auto-init enables detected providers.
- Manifest tracks providers so removal cleans up exactly where install wrote.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from okit import config as okit_config
from okit.core import (
    Artifact,
    install_artifact,
    load_manifest,
    manifest_key,
    remove_artifact,
    save_manifest,
)
from okit.providers import ALL_PROVIDERS, get_provider
from okit.providers.copilot import CopilotProvider, _filter_agent_content
from okit.providers.opencode import OpencodeProvider


# ---------------------------------------------------------------------------
# Fixtures: isolated config + manifest + fake $HOME
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Redirect HOME, XDG_CONFIG_HOME, OKIT_CONFIG, OKIT_MANIFEST into tmp_path."""
    home = tmp_path / "home"
    home.mkdir()
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("OKIT_CONFIG", str(xdg / "okit" / "config.json"))
    monkeypatch.setenv("OKIT_MANIFEST", str(tmp_path / "manifest.json"))
    return tmp_path


@pytest.fixture
def all_providers_enabled(isolated_env):
    cfg = okit_config.Config(enabled_providers=[p.id for p in ALL_PROVIDERS])
    okit_config.save(cfg)
    return cfg


def _make_agent(tmp_path: Path, name: str = "reviewer", body: str = "agent body") -> Artifact:
    src = tmp_path / "src_agents"
    src.mkdir(exist_ok=True)
    f = src / f"{name}.md"
    f.write_text(f"---\ndescription: a test agent\n---\n{body}\n")
    return Artifact(kind="agent", name=name, description="a test agent", path=f)


def _make_skill(tmp_path: Path, name: str = "tester") -> Artifact:
    src = tmp_path / "src_skills" / name
    src.mkdir(parents=True, exist_ok=True)
    (src / "SKILL.md").write_text(f"---\nname: {name}\ndescription: skill\n---\nbody\n")
    return Artifact(kind="skill", name=name, description="skill", path=src)


def _make_multi_agent(tmp_path: Path, name: str = "pipeline") -> Artifact:
    src = tmp_path / "src_multi" / name
    src.mkdir(parents=True, exist_ok=True)
    (src / "planner.md").write_text("---\ndescription: planner\n---\nplan\n")
    (src / "executor.md").write_text("---\ndescription: executor\n---\nrun\n")
    return Artifact(kind="multi-agent", name=name, description="multi", path=src)


# ---------------------------------------------------------------------------
# installed_paths — the public contract for filename/layout decisions
# ---------------------------------------------------------------------------


class TestInstalledPaths:
    def test_opencode_agent_plain_md(self, isolated_env):
        p = OpencodeProvider()
        paths = p.installed_paths("agent", "reviewer", project_dir=None)
        assert len(paths) == 1
        assert paths[0].name == "reviewer.md"

    def test_copilot_agent_has_agent_md_suffix(self, isolated_env):
        p = CopilotProvider()
        paths = p.installed_paths("agent", "reviewer", project_dir=None)
        assert len(paths) == 1
        assert paths[0].name == "reviewer.agent.md"

    def test_copilot_idempotent_for_already_suffixed_name(self, isolated_env):
        p = CopilotProvider()
        paths = p.installed_paths("agent", "foo.agent", project_dir=None)
        assert paths[0].name == "foo.agent.md"

    def test_opencode_global_agents_under_xdg(self, isolated_env):
        p = OpencodeProvider()
        paths = p.installed_paths("agent", "reviewer", project_dir=None)
        assert Path(os.environ["XDG_CONFIG_HOME"]) / "opencode" / "agents" / "reviewer.md" in paths

    def test_opencode_project_agents_under_dot_opencode(self, isolated_env):
        proj = isolated_env / "myproj"
        paths = OpencodeProvider().installed_paths("agent", "reviewer", project_dir=proj)
        assert paths[0] == proj / ".opencode" / "agents" / "reviewer.md"

    def test_copilot_global_agents_under_dot_copilot(self, isolated_env):
        paths = CopilotProvider().installed_paths("agent", "reviewer", project_dir=None)
        assert paths[0] == Path(os.environ["HOME"]) / ".copilot" / "agents" / "reviewer.agent.md"

    def test_copilot_project_agents_under_dot_github(self, isolated_env):
        proj = isolated_env / "myproj"
        paths = CopilotProvider().installed_paths("agent", "reviewer", project_dir=proj)
        assert paths[0] == proj / ".github" / "agents" / "reviewer.agent.md"


# ---------------------------------------------------------------------------
# Multi-target install: one artifact → N copies in N layouts
# ---------------------------------------------------------------------------


class TestMultiProviderInstall:
    def test_agent_lands_in_both_provider_layouts(self, all_providers_enabled, isolated_env):
        artifact = _make_agent(isolated_env)
        ok, msg = install_artifact(artifact, repo_url="user/repo", commit="abc")
        assert ok, msg

        oc_paths = OpencodeProvider().installed_paths("agent", "reviewer", project_dir=None)
        cp_paths = CopilotProvider().installed_paths("agent", "reviewer", project_dir=None)

        assert oc_paths[0].exists()
        assert oc_paths[0].name == "reviewer.md"
        assert cp_paths[0].exists()
        assert cp_paths[0].name == "reviewer.agent.md"
        # Copilot agents must be flat under /agents — no subfolders.
        assert cp_paths[0].parent.name == "agents"

    def test_manifest_records_both_providers(self, all_providers_enabled, isolated_env):
        artifact = _make_agent(isolated_env)
        install_artifact(artifact, repo_url="user/repo", commit="abc")

        records = load_manifest()
        rec = records[manifest_key("agent", "reviewer")]
        assert sorted(rec.providers) == ["claudecode", "copilot", "opencode", "piagent", "windsurf"]

    def test_skill_installs_to_all_providers(self, all_providers_enabled, isolated_env):
        artifact = _make_skill(isolated_env)
        install_artifact(artifact, repo_url="r", commit="c")

        # Per spec: skills are copied verbatim into a sibling skills/ folder
        # for Copilot, even though Copilot itself has no skills concept.
        oc_skill = OpencodeProvider().installed_paths("skill", "tester", project_dir=None)[0]
        cp_skill = CopilotProvider().installed_paths("skill", "tester", project_dir=None)[0]
        assert (oc_skill / "SKILL.md").exists()
        assert (cp_skill / "SKILL.md").exists()

    def test_multi_agent_flattened_for_copilot(self, all_providers_enabled, isolated_env):
        artifact = _make_multi_agent(isolated_env)
        install_artifact(artifact, repo_url="r", commit="c")

        # OpenCode preserves the subdirectory structure.
        oc_dir = OpencodeProvider().installed_paths("multi-agent", "pipeline", project_dir=None)[0]
        assert (oc_dir / "planner.md").exists()
        assert (oc_dir / "executor.md").exists()

        # Copilot flattens: each member → <member>.agent.md directly under agents/.
        cp_root = CopilotProvider()._agents_dir(None)
        assert (cp_root / "planner.agent.md").exists()
        assert (cp_root / "executor.agent.md").exists()
        assert not (cp_root / "pipeline").exists()


# ---------------------------------------------------------------------------
# Provider scoping — only enabled providers receive installs
# ---------------------------------------------------------------------------


class TestProviderScoping:
    def test_only_enabled_providers_get_install(self, isolated_env):
        okit_config.save(okit_config.Config(enabled_providers=["opencode"]))

        artifact = _make_agent(isolated_env)
        install_artifact(artifact, repo_url="r", commit="c")

        oc_path = OpencodeProvider().installed_paths("agent", "reviewer", project_dir=None)[0]
        cp_path = CopilotProvider().installed_paths("agent", "reviewer", project_dir=None)[0]
        assert oc_path.exists()
        assert not cp_path.exists()


# ---------------------------------------------------------------------------
# Removal: clean up exactly where install wrote
# ---------------------------------------------------------------------------


class TestRemoval:
    def test_remove_cleans_all_recorded_providers(self, all_providers_enabled, isolated_env):
        artifact = _make_agent(isolated_env)
        install_artifact(artifact, repo_url="r", commit="c")

        ok, _ = remove_artifact("agent", "reviewer")
        assert ok

        oc_path = OpencodeProvider().installed_paths("agent", "reviewer", project_dir=None)[0]
        cp_path = CopilotProvider().installed_paths("agent", "reviewer", project_dir=None)[0]
        assert not oc_path.exists()
        assert not cp_path.exists()
        assert manifest_key("agent", "reviewer") not in load_manifest()

    def test_remove_legacy_record_falls_back_to_enabled_providers(
        self, all_providers_enabled, isolated_env
    ):
        # Simulate a manifest written before multi-provider support: providers=[].
        artifact = _make_agent(isolated_env)
        install_artifact(artifact, repo_url="r", commit="c")
        records = load_manifest()
        records[manifest_key("agent", "reviewer")].providers = []
        save_manifest(records)

        ok, _ = remove_artifact("agent", "reviewer")
        assert ok

        oc_path = OpencodeProvider().installed_paths("agent", "reviewer", project_dir=None)[0]
        cp_path = CopilotProvider().installed_paths("agent", "reviewer", project_dir=None)[0]
        assert not oc_path.exists()
        assert not cp_path.exists()


# ---------------------------------------------------------------------------
# Config: first-run init + auto-detection
# ---------------------------------------------------------------------------


class TestConfigInit:
    def test_first_run_writes_default_config(self, isolated_env):
        path = okit_config.config_path()
        assert not path.exists()

        cfg = okit_config.ensure_initialized()
        assert path.exists()
        assert cfg.enabled_providers  # non-empty

    def test_init_is_idempotent(self, isolated_env):
        okit_config.ensure_initialized()
        narrow = okit_config.Config(enabled_providers=["opencode"])
        okit_config.save(narrow)

        second = okit_config.ensure_initialized()
        assert second.enabled_providers == ["opencode"]

    def test_autodetect_picks_only_providers_on_path(self, isolated_env, monkeypatch):
        monkeypatch.setattr("okit.providers.base.shutil.which", lambda cmd: "/fake/opencode" if cmd == "opencode" else None)
        cfg = okit_config.ensure_initialized()
        assert cfg.enabled_providers == ["opencode"]

    def test_autodetect_falls_back_to_all_when_none_present(self, isolated_env, monkeypatch):
        monkeypatch.setattr("okit.providers.base.shutil.which", lambda _: None)
        cfg = okit_config.ensure_initialized()
        assert sorted(cfg.enabled_providers) == sorted(p.id for p in ALL_PROVIDERS)

    def test_corrupt_config_is_treated_as_empty(self, isolated_env):
        path = okit_config.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json {")
        cfg = okit_config.load()
        assert cfg.enabled_providers == []

    def test_unknown_provider_ids_are_dropped(self, isolated_env):
        path = okit_config.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "providers": {"enabled": ["opencode", "ghost"]}}))
        cfg = okit_config.load()
        assert cfg.enabled_providers == ["opencode"]


# ---------------------------------------------------------------------------
# Copilot frontmatter filtering
# ---------------------------------------------------------------------------


class TestCopilotFrontmatterFilter:
    def test_strips_unknown_fields(self):
        src = "---\ndescription: x\nhidden: true\npermission: read\ntarget: foo\nmode: ask\n---\nbody\n"
        result = _filter_agent_content(src)
        assert "hidden" not in result
        assert "permission" not in result
        assert "target" not in result
        assert "mode" not in result
        assert "description: x" in result

    def test_strips_block_children_of_unknown_field(self):
        src = "---\ndescription: x\npermission:\n  bash:\n    allow:\n      - read\nmodel: gpt-4o\n---\nbody\n"
        result = _filter_agent_content(src)
        assert "permission" not in result
        assert "bash" not in result
        assert "allow" not in result
        assert "model: gpt-4o" in result

    def test_normalises_model_with_provider_prefix(self):
        src = "---\nmodel: openai/gpt-4o\n---\nbody\n"
        result = _filter_agent_content(src)
        assert "model: gpt-4o" in result
        assert "openai/" not in result

    def test_preserves_model_without_prefix(self):
        src = "---\nmodel: gpt-4o\n---\nbody\n"
        result = _filter_agent_content(src)
        assert "model: gpt-4o" in result

    def test_body_untouched(self):
        src = "---\ndescription: x\n---\nhidden: yes\npermission: denied\n"
        result = _filter_agent_content(src)
        assert result.endswith("hidden: yes\npermission: denied\n")

    def test_no_frontmatter_returned_verbatim(self):
        src = "just body\nhidden: true\n"
        assert _filter_agent_content(src) == src

    def test_installed_agent_has_unknown_fields_removed(self, all_providers_enabled, isolated_env):
        src = isolated_env / "src_agents"
        src.mkdir(exist_ok=True)
        f = src / "checker.md"
        f.write_text("---\ndescription: d\nhidden: true\nmodel: anthropic/claude-3\n---\nbody\n")
        artifact = Artifact(kind="agent", name="checker", description="d", path=f)
        install_artifact(artifact, repo_url="r", commit="c")

        cp_path = CopilotProvider().installed_paths("agent", "checker", project_dir=None)[0]
        content = cp_path.read_text()
        assert "hidden" not in content
        assert "model: claude-3" in content


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_get_provider_returns_correct_instance(self):
        assert isinstance(get_provider("opencode"), OpencodeProvider)
        assert isinstance(get_provider("copilot"), CopilotProvider)

    def test_get_provider_unknown_raises(self):
        with pytest.raises(KeyError):
            get_provider("nope")
