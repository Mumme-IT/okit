"""`okit setup` interactive configuration menu.

Currently a single-entry menu (Providers) per spec. Adding a future entry is
a one-line change: append to ``MENU_ITEMS`` with a callback that mutates the
``Config`` and saves it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from okit import config as okit_config
from okit.config import Config
from okit.providers import ALL_PROVIDERS
from okit.selector import interactive_select_grouped


@dataclass
class MenuItem:
    label: str
    handler: Callable[[Config], Config]  # returns possibly-mutated Config


# --- Provider selection ---


def _edit_providers(config: Config) -> Config:
    """Show a multi-select of all known providers; persist the chosen set."""
    items: list[tuple[int, str]] = []
    preselected: set[int] = set()
    for idx, provider in enumerate(ALL_PROVIDERS):
        suffix = []
        if provider.is_available():
            suffix.append("detected")
        else:
            suffix.append("not detected")
        label = f"{provider.display_name} [{provider.id}] — {', '.join(suffix)}"
        items.append((idx, label))
        if config.is_enabled(provider.id):
            preselected.add(idx)

    groups = [{"label": "Providers", "children": [{"label": "Targets", "items": items}]}]

    selected = interactive_select_grouped(
        groups,
        header="Select providers okit should install to",
        preselected=preselected,
    )
    if selected is None:
        print("Provider selection unchanged.")
        return config

    enabled_ids = [ALL_PROVIDERS[i].id for i in selected]
    config.enabled_providers = enabled_ids
    okit_config.save(config)
    if enabled_ids:
        print(f"Enabled providers: {', '.join(enabled_ids)}")
    else:
        print("No providers enabled. okit will not install anywhere until at least one is selected.")
    return config


# --- Menu registration: append here to add new setup screens. ---

MENU_ITEMS: list[MenuItem] = [
    MenuItem(label="Providers", handler=_edit_providers),
]


# --- Top-level menu ---


def run_setup() -> None:
    """Top-level `okit setup` entry. One screen per MENU_ITEM, repeatable."""
    if not sys.stdin.isatty():
        print("Error: 'okit setup' requires an interactive terminal.")
        sys.exit(1)

    config = okit_config.ensure_initialized()

    items = [(i, item.label) for i, item in enumerate(MENU_ITEMS)]
    groups = [{"label": "okit setup", "children": [{"label": "Settings", "items": items}]}]

    selected = interactive_select_grouped(
        groups,
        header="Choose what to configure (Space to pick, Enter to open)",
    )
    if not selected:
        print("Setup cancelled.")
        return

    for idx in selected:
        MENU_ITEMS[idx].handler(config)
