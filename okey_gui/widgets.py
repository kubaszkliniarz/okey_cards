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
MUTED    = "#777799"
FG       = "#eaeaea"
HL_RING  = "#00e5ff"   # cyan highlight ring


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


class ActionButton(tk.Button):
    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable,
        color: str = ACCENT,
        **kwargs,
    ) -> None:
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=color,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            padx=12,
            pady=6,
            activebackground=color,
            activeforeground="white",
            cursor="hand2",
            **kwargs,
        )
