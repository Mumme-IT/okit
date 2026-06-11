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


def _build_visible(nodes: list[_Node], collapsed: set[int]) -> list[int]:
    """Return positions of nodes that are currently visible (not hidden by a collapsed ancestor)."""
    visible: list[int] = []
    hidden_until: int = len(nodes)  # nodes[i] with i < hidden_until but inside a collapsed range are skipped

    # We scan linearly; maintain a stack of active collapsed ranges.
    skip_stack: list[int] = []  # stack of range-end values

    for pos, node in enumerate(nodes):
        # Pop exhausted ranges
        while skip_stack and pos >= skip_stack[-1]:
            skip_stack.pop()

        if skip_stack:
            # Inside a collapsed subtree — skip
            continue

        visible.append(pos)

        if node.children_range is not None and pos in collapsed:
            # Push the end of this collapsed range so children are skipped
            skip_stack.append(node.children_range[1])

    return visible


def _fuzzy_matches(query: str, label: str) -> bool:
    """Return True when all query chars appear in label order, case-insensitively."""
    needle = query.casefold()
    haystack = label.casefold()
    next_pos = 0
    for char in needle:
        found_at = haystack.find(char, next_pos)
        if found_at == -1:
            return False
        next_pos = found_at + 1
    return True


def _ancestors_for(nodes: list[_Node], node_pos: int) -> list[int]:
    """Return visible ancestor positions for a flat tree node."""
    ancestors: list[int] = []
    for pos in range(node_pos - 1, -1, -1):
        children_range = nodes[pos].children_range
        if children_range is None:
            continue
        if children_range[0] <= node_pos < children_range[1]:
            ancestors.append(pos)
    return list(reversed(ancestors))


def _build_search_visible(nodes: list[_Node], query: str) -> list[int]:
    """Return matching leaves plus their ancestors for search mode."""
    included: set[int] = set()
    for pos, node in enumerate(nodes):
        if node.index is None or not _fuzzy_matches(query, node.label):
            continue
        included.update(_ancestors_for(nodes, pos))
        included.add(pos)
    return [pos for pos in range(len(nodes)) if pos in included]


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

_INDENT = ("", "  ", "    ")
_CHECKBOX_CHECKED = "[x]"
_CHECKBOX_EMPTY = "[ ]"
_CHECKBOX_PARTIAL = "[-]"
_EXPAND_ICON = "▶"
_COLLAPSE_ICON = "▼"


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


def _render_lines(
    nodes: list[_Node],
    selected: set[int],
    cursor: int,
    collapsed: set[int],
    visible: list[int],
    scroll_offset: int,
    viewport_height: int,
) -> list[str]:
    """Build display lines for the visible viewport slice."""
    lines = []
    viewport_slice = visible[scroll_offset : scroll_offset + viewport_height]
    for pos in viewport_slice:
        node = nodes[pos]
        indent = _INDENT[node.depth]
        if node.index is not None:
            checkbox = _CHECKBOX_CHECKED if node.index in selected else _CHECKBOX_EMPTY
            expand_icon = "  "
        else:
            checkbox = _checkbox_for_parent(nodes, pos, selected)
            if node.children_range is not None:
                expand_icon = f"{_EXPAND_ICON} " if pos in collapsed else f"{_COLLAPSE_ICON} "
            else:
                expand_icon = "  "

        prefix = "> " if pos == cursor else "  "
        lines.append(f"{prefix}{indent}{expand_icon}{checkbox} {node.label}")
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
# Scroll helpers
# ---------------------------------------------------------------------------


def _clamp_scroll(scroll_offset: int, cursor_vis_pos: int, viewport_height: int, total_visible: int) -> int:
    """Adjust scroll so cursor stays within viewport."""
    if cursor_vis_pos < scroll_offset:
        return cursor_vis_pos
    if cursor_vis_pos >= scroll_offset + viewport_height:
        return cursor_vis_pos - viewport_height + 1
    max_scroll = max(0, total_visible - viewport_height)
    return min(scroll_offset, max_scroll)


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
    collapsed: set[int] = set()
    cursor = 0
    scroll_offset = 0
    result: list[int] | None = []
    cancelled = False

    hint = (
        "↑↓ navigate  ◀▶ collapse/expand  Space toggle  "
        "Enter confirm  / search  Esc cancel  a select-all  n deselect-all"
    )
    title_text = header or "Select artifacts"
    search_query = ""
    search_active = False

    style = Style.from_dict({
        "title": "bold",
        "hint": "fg:ansiblue",
        "cursor": "bold fg:ansigreen",
    })

    def _visible() -> list[int]:
        if search_query:
            return _build_search_visible(nodes, search_query)
        return _build_visible(nodes, collapsed)

    def _header_rows() -> int:
        return 4 if search_active or search_query else 3

    def _set_cursor_to_first_visible() -> None:
        nonlocal cursor, scroll_offset
        visible = _visible()
        if visible and cursor not in visible:
            cursor = visible[0]
            scroll_offset = 0

    def _append_search_text(text: str) -> None:
        nonlocal search_query
        search_query += text
        _set_cursor_to_first_visible()

    def get_content():
        nonlocal scroll_offset
        visible = _visible()
        _set_cursor_to_first_visible()
        visible = _visible()
        cursor_vis_pos = visible.index(cursor) if cursor in visible else 0

        app_height = app.output.get_size().rows
        viewport_height = max(1, app_height - _header_rows())

        scroll_offset = _clamp_scroll(scroll_offset, cursor_vis_pos, viewport_height, len(visible))

        lines = _render_lines(nodes, selected, cursor, collapsed, visible, scroll_offset, viewport_height)

        result_fragments = []
        result_fragments.append(("class:title", f"{title_text}\n"))
        result_fragments.append(("class:hint", f"{hint}\n"))
        if search_active or search_query:
            prompt = "/" if search_active else " "
            result_fragments.append(("class:search", f"Search: {prompt}{search_query}\n"))
        result_fragments.append(("", "\n"))

        if not visible:
            result_fragments.append(("", "  No matches\n"))
            return result_fragments

        for vis_idx, line in enumerate(lines):
            abs_vis_pos = scroll_offset + vis_idx
            abs_node_pos = visible[abs_vis_pos] if abs_vis_pos < len(visible) else -1
            cls = "class:cursor" if abs_node_pos == cursor else ""
            result_fragments.append((cls, line + "\n"))
        return result_fragments

    kb = KeyBindings()

    @kb.add("up")
    def _move_up(event):
        nonlocal cursor
        visible = _visible()
        vis_pos = visible.index(cursor) if cursor in visible else 0
        if vis_pos > 0:
            cursor = visible[vis_pos - 1]

    @kb.add("down")
    def _move_down(event):
        nonlocal cursor
        visible = _visible()
        vis_pos = visible.index(cursor) if cursor in visible else 0
        if vis_pos < len(visible) - 1:
            cursor = visible[vis_pos + 1]

    @kb.add("right")
    def _expand(event):
        if search_query:
            return
        node = nodes[cursor]
        if node.children_range is not None and cursor in collapsed:
            collapsed.discard(cursor)

    @kb.add("left")
    def _collapse(event):
        if search_query:
            return
        node = nodes[cursor]
        if node.children_range is not None and cursor not in collapsed:
            collapsed.add(cursor)

    @kb.add("space")
    def _toggle(event):
        if search_active:
            _append_search_text(" ")
            return
        visible = _visible()
        if not visible:
            return
        _toggle_node(nodes, cursor, selected)

    @kb.add("a")
    def _all(event):
        if search_active:
            _append_search_text(event.data)
            return
        _select_all(nodes, selected)

    @kb.add("n")
    def _none(event):
        if search_active:
            _append_search_text(event.data)
            return
        _deselect_all(selected)

    @kb.add("/")
    def _start_search(event):
        nonlocal search_active
        if search_active:
            _append_search_text(event.data)
            return
        search_active = True

    @kb.add("backspace")
    def _search_backspace(event):
        nonlocal search_query
        if not search_active:
            return
        search_query = search_query[:-1]
        _set_cursor_to_first_visible()

    @kb.add("c-h")
    def _search_ctrl_h(event):
        _search_backspace(event)

    @kb.add("<any>")
    def _search_type(event):
        if not search_active:
            return
        _append_search_text(event.data)

    @kb.add("enter")
    def _confirm(event):
        nonlocal result
        result = sorted(selected)
        event.app.exit()

    @kb.add("escape")
    def _escape(event):
        nonlocal cancelled, search_active
        if search_active:
            search_active = False
            _set_cursor_to_first_visible()
            return
        cancelled = True
        event.app.exit()

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


def interactive_menu(items: list[str], header: str = "") -> int | None:
    """Simple arrow-key menu — navigate with ↑↓, confirm with Enter, cancel with Esc/Ctrl+C.

    No checkboxes. One item is highlighted at a time. Returns the selected index or None.
    """
    if not items:
        return None

    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    cursor = 0
    scroll_offset = 0
    result: int | None = None
    cancelled = False

    HEADER_ROWS = 3
    hint = "↑↓ navigate  Enter select  Esc cancel"
    title_text = header or "Select"

    style = Style.from_dict({
        "title": "bold",
        "hint": "fg:ansiblue",
        "cursor": "bold fg:ansigreen",
    })

    def get_content():
        nonlocal scroll_offset
        app_height = app.output.get_size().rows
        viewport_height = max(1, app_height - HEADER_ROWS)
        scroll_offset = _clamp_scroll(scroll_offset, cursor, viewport_height, len(items))

        fragments = []
        fragments.append(("class:title", f"{title_text}\n"))
        fragments.append(("class:hint", f"{hint}\n\n"))

        for i, label in enumerate(items[scroll_offset : scroll_offset + viewport_height]):
            abs_i = scroll_offset + i
            prefix = "> " if abs_i == cursor else "  "
            cls = "class:cursor" if abs_i == cursor else ""
            fragments.append((cls, f"{prefix}{label}\n"))
        return fragments

    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        nonlocal cursor
        if cursor > 0:
            cursor -= 1

    @kb.add("down")
    def _down(event):
        nonlocal cursor
        if cursor < len(items) - 1:
            cursor += 1

    @kb.add("enter")
    def _confirm(event):
        nonlocal result
        result = cursor
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
