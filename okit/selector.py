"""Interactive multi-select terminal UI using prompt_toolkit."""

from __future__ import annotations

from typing import NamedTuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class _Node(NamedTuple):
    """Flat representation of one visible row in the tree."""

    depth: int           # 0 = repo, 1 = kind, 2 = leaf item
    label: str
    index: int | None    # Only leaf nodes carry a selectable index
    children_range: tuple[int, int] | None  # [start, end) into the flat list


# ---------------------------------------------------------------------------
# Tree-building helpers
# ---------------------------------------------------------------------------


def _build_nodes(groups: list[dict]) -> list[_Node]:
    """Convert grouped data into a flat list of tree nodes."""
    nodes: list[_Node] = []

    for group in groups:
        repo_start = len(nodes)
        nodes.append(_Node(depth=0, label=group["label"], index=None, children_range=None))

        for child in group.get("children", []):
            kind_start = len(nodes)
            nodes.append(_Node(depth=1, label=child["label"], index=None, children_range=None))

            for idx, item_label in child.get("items", []):
                nodes.append(_Node(depth=2, label=item_label, index=idx, children_range=None))

            kind_end = len(nodes)
            nodes[kind_start] = nodes[kind_start]._replace(children_range=(kind_start + 1, kind_end))

        repo_end = len(nodes)
        nodes[repo_start] = nodes[repo_start]._replace(children_range=(repo_start + 1, repo_end))

    return nodes


def _leaf_indices_in_range(nodes: list[_Node], start: int, end: int) -> list[int]:
    """Return node positions of all leaf items within [start, end)."""
    return [i for i in range(start, end) if nodes[i].index is not None]


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

_INDENT = ("", "  ", "    ")
_CHECKBOX_CHECKED = "[x]"
_CHECKBOX_EMPTY = "[ ]"
_CHECKBOX_PARTIAL = "[-]"


def _checkbox_for_parent(nodes: list[_Node], node_pos: int, selected: set[int]) -> str:
    """Return the appropriate checkbox string for a parent node."""
    cr = nodes[node_pos].children_range
    if cr is None:
        return _CHECKBOX_EMPTY
    leaf_positions = _leaf_indices_in_range(nodes, *cr)
    if not leaf_positions:
        return _CHECKBOX_EMPTY
    selected_count = sum(1 for p in leaf_positions if nodes[p].index in selected)
    if selected_count == 0:
        return _CHECKBOX_EMPTY
    if selected_count == len(leaf_positions):
        return _CHECKBOX_CHECKED
    return _CHECKBOX_PARTIAL


def _render_lines(nodes: list[_Node], selected: set[int], cursor: int) -> list[str]:
    """Build display lines for all nodes."""
    lines = []
    for pos, node in enumerate(nodes):
        indent = _INDENT[node.depth]
        if node.index is not None:
            checkbox = _CHECKBOX_CHECKED if node.index in selected else _CHECKBOX_EMPTY
        else:
            checkbox = _checkbox_for_parent(nodes, pos, selected)

        prefix = "> " if pos == cursor else "  "
        lines.append(f"{prefix}{indent}{checkbox} {node.label}")
    return lines


# ---------------------------------------------------------------------------
# Selection state mutations
# ---------------------------------------------------------------------------


def _toggle_node(nodes: list[_Node], node_pos: int, selected: set[int]) -> None:
    """Toggle a node: leaves flip themselves; parents flip all descendants."""
    node = nodes[node_pos]
    if node.index is not None:
        if node.index in selected:
            selected.discard(node.index)
        else:
            selected.add(node.index)
        return

    cr = node.children_range
    if cr is None:
        return
    leaf_positions = _leaf_indices_in_range(nodes, *cr)
    leaf_indices = {nodes[p].index for p in leaf_positions}
    if leaf_indices.issubset(selected):
        selected -= leaf_indices
    else:
        selected |= leaf_indices


def _select_all(nodes: list[_Node], selected: set[int]) -> None:
    for node in nodes:
        if node.index is not None:
            selected.add(node.index)


def _deselect_all(selected: set[int]) -> None:
    selected.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def interactive_select_grouped(
    groups: list[dict],
    header: str = "",
    preselected: set[int] | None = None,
) -> list[int] | None:
    """Grouped hierarchical checkbox selector.

    Args:
        groups: List of group dicts, each with:
            - "label": str (e.g., repo name)
            - "children": list of dicts with:
                - "label": str (e.g., "Skills", "Agents")
                - "items": list of tuples (index: int, label: str)
        header: Optional header text
        preselected: Set of indices to pre-check when the selector opens

    Returns:
        List of selected indices on confirm (Enter)
        None on cancel (Escape / Ctrl+C)
    """
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    nodes = _build_nodes(groups)
    if not nodes:
        return []

    selected: set[int] = set(preselected) if preselected else set()
    cursor = 0
    result: list[int] | None = []
    cancelled = False

    hint = "↑↓ navigate  Space toggle  Enter confirm  Esc cancel  a select-all  n deselect-all"
    title_text = header or "Select artifacts"

    style = Style.from_dict({
        "title": "bold",
        "hint": "fg:ansiblue",
        "cursor": "bold fg:ansigreen",
    })

    def get_content():
        lines = _render_lines(nodes, selected, cursor)
        result_fragments = []
        result_fragments.append(("class:title", f"{title_text}\n"))
        result_fragments.append(("class:hint", f"{hint}\n\n"))
        for i, line in enumerate(lines):
            cls = "class:cursor" if i == cursor else ""
            result_fragments.append((cls, line + "\n"))
        return result_fragments

    kb = KeyBindings()

    @kb.add("up")
    def _move_up(event):
        nonlocal cursor
        cursor = max(0, cursor - 1)

    @kb.add("down")
    def _move_down(event):
        nonlocal cursor
        cursor = min(len(nodes) - 1, cursor + 1)

    @kb.add("space")
    def _toggle(event):
        _toggle_node(nodes, cursor, selected)

    @kb.add("a")
    def _all(event):
        _select_all(nodes, selected)

    @kb.add("n")
    def _none(event):
        _deselect_all(selected)

    @kb.add("enter")
    def _confirm(event):
        nonlocal result
        result = sorted(selected)
        event.app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(event):
        nonlocal cancelled
        cancelled = True
        event.app.exit()

    layout = Layout(
        HSplit([
            Window(content=FormattedTextControl(get_content, focusable=True)),
        ])
    )

    app: Application = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=True,
        mouse_support=False,
    )
    app.run()

    if cancelled:
        return None
    return result


def interactive_select(items: list[str], header: str = "") -> list[int] | None:
    """Flat list checkbox selector (backward-compatible).

    Args:
        items: List of item labels to display
        header: Optional header text shown above the list

    Returns:
        List of selected indices on confirm (Enter)
        None on cancel (Escape / Ctrl+C)
    """
    if not items:
        return []

    groups = [
        {
            "label": header or "Items",
            "children": [
                {
                    "label": "Select",
                    "items": [(i, label) for i, label in enumerate(items)],
                }
            ],
        }
    ]
    raw = interactive_select_grouped(groups, header=header)
    if raw is None:
        return None
    return raw
