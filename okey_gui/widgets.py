"""Reusable tkinter widgets for the Okey game UI."""

from __future__ import annotations
import tkinter as tk
from typing import Optional, Callable

from okey_logic.game import Card

# ── Colour palette ────────────────────────────────────────────────────────────

BG       = "#1a1a2e"
PANEL    = "#16213e"
CARD_COL = {"yellow": "#FFD700", "red": "#d93030", "blue": "#2d63d8"}
TEXT_COL = {"yellow": "#111111", "red": "#ffffff",  "blue": "#ffffff"}
ACCENT   = "#e94560"
SUCCESS  = "#4caf50"
WARNING  = "#ff9800"
MUTED    = "#9898b8"
FG       = "#eaeaea"
HL_RING  = "#00e5ff"   # cyan highlight ring

# Button palette — punchy enough to read on the dark background
BTN_NEUTRAL = "#5b6cc7"   # was #333355 (too dim)
BTN_SUCCESS = "#2e8b2e"   # was #1a5c1a
BTN_DANGER  = "#b83838"   # was #5c1a1a


class CardWidget(tk.Canvas):
    """
    A single card displayed as a coloured Canvas.
    Clicking fires on_click(card).
    Pass highlight=True for a bright outline (solver suggestion).
    Pass dim=True to grey it out (empty slot).
    """

    W, H = 68, 96

    def __init__(
        self,
        parent: tk.Widget,
        card: Optional[Card] = None,
        on_click: Optional[Callable[[Card], None]] = None,
        highlight: bool = False,
        dimmed: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            width=self.W,
            height=self.H,
            bg=PANEL,
            highlightthickness=0,
            cursor="hand2" if (card and on_click) else "arrow",
            **kwargs,
        )
        self.card = card
        self.on_click = on_click
        self.highlight = highlight
        self.dimmed = dimmed
        self._draw()
        if on_click and card:
            self.bind("<Button-1>", lambda _e: on_click(card))
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        self.delete("all")
        W, H = self.W, self.H

        if self.card is None:
            # Empty slot — dashed border
            self.create_rectangle(
                3, 3, W - 3, H - 3,
                fill="#0d0d1f", outline=MUTED, width=1, dash=(4, 4),
            )
            self.create_text(
                W // 2, H // 2, text="·", fill=MUTED, font=("Arial", 20),
            )
            return

        bg = CARD_COL[self.card.color]
        fg = TEXT_COL[self.card.color]
        if self.dimmed:
            bg = "#3a3a4a"
            fg = "#888888"

        border_col = HL_RING if self.highlight else "#222244"
        border_w   = 3       if self.highlight else 1

        # Shadow
        self.create_rectangle(5, 5, W - 1, H - 1, fill="#0a0a1a", outline="")
        # Card face
        self.create_rectangle(
            3, 3, W - 4, H - 4,
            fill=bg, outline=border_col, width=border_w,
        )
        # Colour initial — top-left & bottom-right
        init = self.card.color[0].upper()
        self.create_text(11, 13, text=init, fill=fg, font=("Arial", 8, "bold"))
        self.create_text(W - 11, H - 13, text=init, fill=fg, font=("Arial", 8, "bold"))
        # Number — centre
        self.create_text(
            W // 2, H // 2, text=str(self.card.number),
            fill=fg, font=("Arial", 30, "bold"),
        )

    def _on_enter(self, _e: tk.Event) -> None:
        self.configure(bg="#1e2040")

    def _on_leave(self, _e: tk.Event) -> None:
        self.configure(bg=PANEL)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def refresh(
        self,
        card: Optional[Card] = None,
        highlight: bool = False,
        dimmed: bool = False,
    ) -> None:
        self.card      = card
        self.highlight = highlight
        self.dimmed    = dimmed
        self._draw()


class MiniCard(tk.Canvas):
    """Small non-interactive card used in the AI Analysis panel."""

    W, H = 42, 58

    def __init__(
        self,
        parent: tk.Widget,
        card: Optional[Card],
        highlight: bool = False,
        dim: bool = False,
        bg: str = "#0d0d1f",
        **kwargs,
    ) -> None:
        super().__init__(
            parent, width=self.W, height=self.H,
            bg=bg, highlightthickness=0, **kwargs,
        )
        self.card = card
        self.highlight = highlight
        self.dim = dim
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        W, H = self.W, self.H
        if self.card is None:
            self.create_rectangle(2, 2, W - 2, H - 2,
                                  fill="#0a0a1a", outline=MUTED,
                                  width=1, dash=(3, 3))
            return

        bg = CARD_COL[self.card.color]
        fg = TEXT_COL[self.card.color]
        if self.dim:
            bg = "#3a3a4a"
            fg = "#888888"

        border = HL_RING if self.highlight else "#222244"
        bw = 2 if self.highlight else 1

        # Shadow
        self.create_rectangle(3, 3, W - 1, H - 1, fill="#050510", outline="")
        # Face
        self.create_rectangle(1, 1, W - 3, H - 3,
                              fill=bg, outline=border, width=bw)
        # Initial
        init = self.card.color[0].upper()
        self.create_text(7, 8, text=init, fill=fg, font=("Arial", 6, "bold"))
        # Number
        self.create_text(W // 2, H // 2 + 1,
                         text=str(self.card.number),
                         fill=fg, font=("Arial", 17, "bold"))


class SectionLabel(tk.Label):
    def __init__(self, parent: tk.Widget, text: str, **kwargs) -> None:
        super().__init__(
            parent,
            text=text,
            font=("Arial", 11, "bold"),
            bg=BG,
            fg=MUTED,
            **kwargs,
        )


def _shift_hex(hex_color: str, factor: float) -> str:
    """Lighten (factor>0) or darken (factor<0) a hex colour."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if factor >= 0:
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
    else:
        f = 1 + factor
        r = max(0, int(r * f))
        g = max(0, int(g * f))
        b = max(0, int(b * f))
    return f"#{r:02x}{g:02x}{b:02x}"


class ActionButton(tk.Frame):
    """
    Label-based button.  Avoids tk.Button on macOS (which ignores bg/fg and
    draws a native grey button regardless, rendering our dark-theme buttons
    unreadable).  Works identically across platforms.
    """

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Optional[Callable] = None,
        color: str = ACCENT,
        **kwargs,
    ) -> None:
        super().__init__(
            parent, bg=color, highlightthickness=0, bd=0, **kwargs,
        )
        self._base  = color
        self._hover = _shift_hex(color, 0.18)
        self._press = _shift_hex(color, -0.15)
        self._command = command
        self._disabled = False
        self._dim = _shift_hex(color, -0.35)

        self._label = tk.Label(
            self, text=text, bg=color, fg="white",
            font=("Arial", 10, "bold"),
            padx=14, pady=7, cursor="hand2",
        )
        self._label.pack(fill="both", expand=True)

        for w in (self, self._label):
            w.bind("<Button-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_press(self, _e: tk.Event) -> None:
        if self._disabled:
            return
        self._paint(self._press)

    def _on_release(self, e: tk.Event) -> None:
        if self._disabled:
            return
        self._paint(self._hover)
        # Only fire if release happens inside the widget
        x, y = e.x_root, e.y_root
        x1 = self.winfo_rootx()
        y1 = self.winfo_rooty()
        x2 = x1 + self.winfo_width()
        y2 = y1 + self.winfo_height()
        if x1 <= x <= x2 and y1 <= y <= y2 and self._command:
            self._command()

    def _on_enter(self, _e: tk.Event) -> None:
        if self._disabled:
            return
        self._paint(self._hover)

    def _on_leave(self, _e: tk.Event) -> None:
        if self._disabled:
            return
        self._paint(self._base)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _paint(self, col: str) -> None:
        self.config(bg=col)
        self._label.config(bg=col)

    def set_state(self, state: str) -> None:
        if state == "disabled":
            self._disabled = True
            self._paint(self._dim)
            self._label.config(fg="#bbbbbb", cursor="arrow")
        else:
            self._disabled = False
            self._paint(self._base)
            self._label.config(fg="white", cursor="hand2")

    # Back-compat with the Tk "state=..." kwarg used elsewhere
    def config(self, **kw):  # type: ignore[override]
        if "state" in kw:
            self.set_state(kw.pop("state"))
        if kw:
            super().config(**kw)

    configure = config  # type: ignore[assignment]
