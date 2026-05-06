"""Provider abstraction — translates okit artifacts to AI-tool-specific layouts.

Each provider declares where artifacts live for its target tool (e.g. OpenCode,
GitHub Copilot) and how filenames must be transformed. The core install/remove
machinery loops over enabled providers; provider-specific quirks (filename
suffixes, layout flattening, supported kinds) stay encapsulated here.

To add a new provider:
  1. Subclass `Provider` in a new module under `okit/providers/`.
  2. Implement the abstract path/filename methods.
  3. Register it in `ALL_PROVIDERS` below.
"""

from __future__ import annotations

from okit.providers.base import Provider
from okit.providers.claudecode import ClaudeCodeProvider
from okit.providers.copilot import CopilotProvider
from okit.providers.opencode import OpencodeProvider
from okit.providers.piagent import PiAgentProvider
from okit.providers.windsurf import WindsurfProvider

# Single source of truth for which providers exist. Order matters for display.
ALL_PROVIDERS: list[Provider] = [
    OpencodeProvider(),
    CopilotProvider(),
    ClaudeCodeProvider(),
    WindsurfProvider(),
    PiAgentProvider(),
]

PROVIDERS_BY_ID: dict[str, Provider] = {p.id: p for p in ALL_PROVIDERS}


def get_provider(provider_id: str) -> Provider:
    """Look up a provider by id, raising KeyError if unknown."""
    return PROVIDERS_BY_ID[provider_id]


__all__ = ["Provider", "ALL_PROVIDERS", "PROVIDERS_BY_ID", "get_provider"]
