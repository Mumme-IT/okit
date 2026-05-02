"""Interactive multi-select terminal UI using only stdlib."""

from __future__ import annotations

import os
import sys
import termios
import tty

ANSI_BOLD_ON = "\x1b[1m"
ANSI_RESET = "\x1b[0m"
ANSI_CLEAR_LINE = "\x1b[2K"
ANSI_CURSOR_UP = "\x1b[{n}A"

KEY_UP = "\x1b[A"
KEY_DOWN = "\x1b[B"
KEY_SPACE = "\x20"
KEY_ENTER_CR = "\r"
KEY_ENTER_LF = "\n"
KEY_ESCAPE = "\x1b"


def interactive_select(items: list[str], header: str = "") -> list[int] | None:
    """Show an interactive multi-select prompt in the terminal.

    Returns a list of selected indices on Enter, or None if the user cancels
    with Escape. Returns an empty list immediately for an empty items list.
    """
    if not items:
        return []

    fd = sys.stdin.fileno()
    original_attrs = termios.tcgetattr(fd)
    state = _SelectionState(items)

    _print_menu(items, state, header)

    try:
        tty.setraw(fd)
        return _run_event_loop(fd, items, state, header, original_attrs)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
        sys.stdout.write("\n")
        sys.stdout.flush()


# --- Internal state ---


class _SelectionState:
    """Holds mutable UI state for the selection loop."""

    def __init__(self, items: list[str]) -> None:
        self.cursor = 0
        self.selected: set[int] = set()
        self.item_count = len(items)

    def move_up(self) -> None:
        self.cursor = (self.cursor - 1) % self.item_count

    def move_down(self) -> None:
        self.cursor = (self.cursor + 1) % self.item_count

    def toggle_current(self) -> None:
        if self.cursor in self.selected:
            self.selected.discard(self.cursor)
        else:
            self.selected.add(self.cursor)


# --- Rendering ---


def _print_menu(items: list[str], state: _SelectionState, header: str) -> None:
    """Print the full menu to stdout."""
    output = []
    if header:
        output.append(f"{header}\n")
    for index, item in enumerate(items):
        output.append(_render_row(index, item, state))
    sys.stdout.write("".join(output))
    sys.stdout.flush()


def _redraw_menu(items: list[str], state: _SelectionState, header: str) -> None:
    """Move cursor up and overwrite all menu lines."""
    line_count = len(items) + (1 if header else 0)
    sys.stdout.write(ANSI_CURSOR_UP.format(n=line_count))
    _print_menu(items, state, header)


def _render_row(index: int, item: str, state: _SelectionState) -> str:
    marker = "[x]" if index in state.selected else "[ ]"
    is_highlighted = index == state.cursor
    prefix = "> " if is_highlighted else "  "
    line = f"{prefix}{marker} {item}\n"
    if is_highlighted:
        return f"{ANSI_CLEAR_LINE}{ANSI_BOLD_ON}{line}{ANSI_RESET}"
    return f"{ANSI_CLEAR_LINE}{line}"


# --- Input reading ---


def _read_key(fd: int) -> str:
    """Read one logical key from the terminal file descriptor."""
    first = os.read(fd, 1).decode("utf-8", errors="replace")
    if first != KEY_ESCAPE:
        return first

    # Peek for escape sequence vs bare Escape press
    remaining = _try_read_escape_sequence(fd)
    return first + remaining


def _try_read_escape_sequence(fd: int) -> str:
    """Read the remainder of an escape sequence, if any."""
    import select as _select

    readable, _, _ = _select.select([fd], [], [], 0.05)
    if not readable:
        return ""

    bracket = os.read(fd, 1).decode("utf-8", errors="replace")
    if bracket != "[":
        return bracket

    direction = os.read(fd, 1).decode("utf-8", errors="replace")
    return f"[{direction}"


# --- Event loop ---


def _run_event_loop(
    fd: int,
    items: list[str],
    state: _SelectionState,
    header: str,
    original_attrs: list,
) -> list[int] | None:
    """Process keystrokes until Enter or Escape.

    Restores terminal attrs before returning so callers can use `finally` for
    the same cleanup without double-restore issues.
    """
    while True:
        key = _read_key(fd)

        if key == KEY_UP:
            state.move_up()
        elif key == KEY_DOWN:
            state.move_down()
        elif key == KEY_SPACE:
            state.toggle_current()
        elif key in (KEY_ENTER_CR, KEY_ENTER_LF):
            termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
            _redraw_menu(items, state, header)
            return sorted(state.selected)
        elif key == KEY_ESCAPE:
            termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
            _redraw_menu(items, state, header)
            return None
        else:
            continue

        _redraw_menu(items, state, header)
