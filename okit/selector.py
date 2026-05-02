"""Interactive multi-select terminal UI using prompt_toolkit."""

from __future__ import annotations


def interactive_select(items: list[str], header: str = "") -> list[int] | None:
    """Show an interactive multi-select checkbox list.

    Args:
        items: List of item labels to display
        header: Optional header text shown above the list

    Returns:
        List of selected indices on confirm (Enter)
        None on cancel (Ctrl+C / Escape)
    """
    if not items:
        return []

    from prompt_toolkit.shortcuts import checkboxlist_dialog

    values = [(i, item) for i, item in enumerate(items)]

    result = checkboxlist_dialog(
        title=header or "Select items",
        text="Use ↑↓ to navigate, Space to select, Enter to confirm",
        values=values,
    ).run()

    if result is None:
        return None
    return result
