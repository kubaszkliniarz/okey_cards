"""
Main solver window.

The user plays Okey in a separate real-world game/app and uses this window
to get strategy advice.  No cards are drawn by this app — the user enters
what they see using the card picker grid.

Layout
──────
  Left column
    • Stats bar
    • Answer stack  (0–3 slots + Submit / Clear)
    • Current hand  (0–5 slots depending on stack size)
    • [Discard Hand & Draw]
    • Card picker   (3×8 grid of all 24 cards)
    • Log

  Right column  (fixed-width)
    • AI Solver panel
"""

from __future__ import annotations
import datetime
import os
import random
import tempfile
import threading
import tkinter as tk
import urllib.request
from tkinter import font as tkfont
from typing import Dict, List, Optional, Any, Tuple

from okey_logic.game import Card, COLORS, NUMBERS, score_combo
from okey_logic.session import SolverSession, ALL_CARDS
from okey_logic.solver import solve
from okey_gui.widgets import (
    BG, PANEL, ACCENT, SUCCESS, WARNING, MUTED, FG, HL_RING,
    BTN_NEUTRAL, BTN_SUCCESS, BTN_DANGER,
    CardWidget, MiniCard, ActionButton,
)

PICKER_CARD_W = 52
PICKER_CARD_H = 72
CARD_PAD      = 3
SOLVER_BG     = "#0d0d1f"
REC_BG        = "#1a1e35"

# card state → visual style
STATE_COLORS = {
    "available":  {"bg": None,      "border": "#333355", "bw": 1, "alpha": 1.0},
    "hand":       {"bg": None,      "border": SUCCESS,   "bw": 3, "alpha": 1.0},
    "stack":      {"bg": None,      "border": HL_RING,   "bw": 3, "alpha": 1.0},
    "discarded":  {"bg": "#1e1e2e", "border": "#222222", "bw": 1, "alpha": 0.3},
    "scored":     {"bg": "#1e1e2e", "border": "#222233", "bw": 1, "alpha": 0.3},
}

COLOR_HEX = {"yellow": "#FFD700", "red": "#d93030", "blue": "#2d63d8"}
TEXT_COL  = {"yellow": "#111111", "red": "#ffffff",  "blue": "#ffffff"}


# ── Picker card ───────────────────────────────────────────────────────────────

class PickerCard(tk.Canvas):
    """One cell in the 3×8 card-picker grid."""

    W, H = PICKER_CARD_W, PICKER_CARD_H

    def __init__(self, parent: tk.Widget, card: Card, on_click, **kw) -> None:
        super().__init__(
            parent, width=self.W, height=self.H,
            bg=PANEL, highlightthickness=0, cursor="hand2", **kw,
        )
        self.card = card
        self._on_click = on_click
        self._state = "available"
        self.bind("<Button-1>", lambda _e: on_click(card))
        self.bind("<Enter>", self._hover_in)
        self.bind("<Leave>", self._hover_out)
        self._hovering = False
        self.draw()

    def set_state(self, state: str) -> None:
        self._state = state
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        W, H = self.W, self.H
        s = self._state

        if s in ("discarded", "scored"):
            # Dark greyed-out card
            self.create_rectangle(2, 2, W-2, H-2, fill="#111122", outline="#222233", width=1)
            self.create_text(W//2, H//2 - 6, text=str(self.card.number),
                             fill="#333344", font=("Arial", 18, "bold"))
            symbol = "✓" if s == "scored" else "✕"
            self.create_text(W//2, H-14, text=symbol, fill="#333344", font=("Arial", 10))
            return

        bg  = COLOR_HEX[self.card.color]
        fg  = TEXT_COL[self.card.color]
        st  = STATE_COLORS[s]
        bdr = st["border"]
        bw  = st["bw"]

        if self._hovering and s == "available":
            bdr = "#aaaacc"
            bw  = 2

        # Shadow
        self.create_rectangle(3, 3, W-1, H-1, fill="#0a0a18", outline="")
        # Face
        self.create_rectangle(2, 2, W-3, H-3, fill=bg, outline=bdr, width=bw)
        # Corner initial
        init = self.card.color[0].upper()
        self.create_text(9, 10,   text=init, fill=fg, font=("Arial", 7, "bold"))
        self.create_text(W-9,H-10,text=init, fill=fg, font=("Arial", 7, "bold"))
        # Number
        self.create_text(W//2, H//2, text=str(self.card.number),
                         fill=fg, font=("Arial", 22, "bold"))

    def _hover_in(self, _e):
        self._hovering = True
        if self._state == "available":
            self.draw()

    def _hover_out(self, _e):
        self._hovering = False
        if self._state == "available":
            self.draw()


# ── Small hand/stack card display ────────────────────────────────────────────

class SlotCard(tk.Canvas):
    """Card displayed in the hand or stack area (larger, clickable)."""

    W, H = 64, 90

    def __init__(self, parent, card: Optional[Card], on_click=None,
                 on_right_click=None, border_color="#333355", **kw):
        super().__init__(parent, width=self.W, height=self.H,
                         bg=PANEL, highlightthickness=0,
                         cursor="hand2" if (card and on_click) else "arrow", **kw)
        self.card = card
        if on_click and card:
            self.bind("<Button-1>", lambda _e: on_click(card))
        if on_right_click and card:
            # On macOS a two-finger tap or Control-click usually fires
            # <Button-2>; on Linux/Windows it's <Button-3>.  Bind both plus
            # explicit Ctrl-click so discard works everywhere.
            for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
                self.bind(seq, lambda _e, c=card: on_right_click(c))
        self._border = border_color
        self._draw()

    def _draw(self):
        self.delete("all")
        W, H = self.W, self.H
        if self.card is None:
            self.create_rectangle(3, 3, W-3, H-3, fill="#0d0d1f",
                                  outline=MUTED, width=1, dash=(4, 4))
            self.create_text(W//2, H//2, text="·", fill=MUTED, font=("Arial", 18))
            return
        bg = COLOR_HEX[self.card.color]
        fg = TEXT_COL[self.card.color]
        self.create_rectangle(4, 4, W-2, H-2, fill="#0a0a18", outline="")
        self.create_rectangle(2, 2, W-4, H-4, fill=bg,
                              outline=self._border, width=3)
        init = self.card.color[0].upper()
        self.create_text(10, 11,   text=init, fill=fg, font=("Arial", 8, "bold"))
        self.create_text(W-10,H-11,text=init, fill=fg, font=("Arial", 8, "bold"))
        self.create_text(W//2, H//2, text=str(self.card.number),
                         fill=fg, font=("Arial", 26, "bold"))


# ── Main window ───────────────────────────────────────────────────────────────

class OkeyApp(tk.Tk):

    def __init__(self) -> None:
        super().__init__()
        self.title("Okey Solver")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.session = SolverSession()
        self._picker: Dict[Card, PickerCard] = {}
        self._solve_result: Optional[Dict[str, Any]] = None
        self._highlighted: List[Card] = []      # play / keep set (cyan ring)
        self._drop_target: Optional[Card] = None  # one card to discard (red)
        self._game_over_overlay: Optional[tk.Frame] = None

        self._build_ui()
        self._refresh()
        self._easter_egg = _KremuwkaEgg(self)

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Title ─────────────────────────────────────────────────────────────
        title_row = tk.Frame(self, bg=BG)
        title_row.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(title_row, text="OKEY", font=("Arial", 20, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(title_row, text=" Solver", font=("Arial", 20),
                 bg=BG, fg=FG).pack(side="left")
        ActionButton(title_row, "New Game", self._new_game,
                     color=BTN_NEUTRAL).pack(side="right")

        # ── Stats ──────────────────────────────────────────────────────────────
        stats = tk.Frame(self, bg=BG)
        stats.pack(fill="x", padx=18, pady=(0, 6))
        self.lbl_score  = self._stat(stats, "Score: 0",    SUCCESS)
        self.lbl_combos = self._stat(stats, "Combos: 0",   FG)
        self.lbl_seen   = self._stat(stats, "Seen: 0/24",  FG)
        self.lbl_round  = self._stat(stats, "Round: 1",    MUTED)
        self.lbl_deck   = self._stat(stats, "Deck left: 24", MUTED)

        _sep(self)

        # ── Body ───────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=6)

        left  = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=PANEL, width=340)
        right.pack(side="right", fill="y", padx=(16, 0))
        right.pack_propagate(False)

        # ── Answer stack ───────────────────────────────────────────────────────
        self._section(left, "ANSWER STACK  —  click a stack card to return it to hand")
        stack_outer = tk.Frame(left, bg=BG)
        stack_outer.pack(anchor="w", pady=(0, 4))
        self.stack_frame = tk.Frame(stack_outer, bg=PANEL, padx=8, pady=6)
        self.stack_frame.pack(side="left")
        stack_btns = tk.Frame(stack_outer, bg=BG)
        stack_btns.pack(side="left", padx=(10, 0))
        self.btn_submit = ActionButton(stack_btns, "✓ Submit Combo",
                                       self._submit_combo, color=BTN_SUCCESS)
        self.btn_submit.pack(anchor="w", pady=(0, 4))
        ActionButton(stack_btns, "↩ Clear Stack",
                     self._clear_stack, color=BTN_NEUTRAL).pack(anchor="w")
        self.stack_status = tk.Label(left, text="", font=("Arial", 10),
                                     bg=BG, fg=MUTED)
        self.stack_status.pack(anchor="w", pady=(0, 4))

        _sep(left)

        # ── Hand ───────────────────────────────────────────────────────────────
        self._section(
            left,
            "CURRENT HAND  —  left-click: move to stack   "
            "·   right-click (or ⌃-click): discard just that card",
        )
        hand_outer = tk.Frame(left, bg=BG)
        hand_outer.pack(anchor="w", pady=(0, 6))
        self.hand_frame = tk.Frame(hand_outer, bg=PANEL, padx=8, pady=6)
        self.hand_frame.pack(side="left")

        hand_btns = tk.Frame(hand_outer, bg=BG)
        hand_btns.pack(side="left", padx=(12, 0))
        ActionButton(hand_btns, "↺ Discard Hand & Draw",
                     self._discard_hand, color=BTN_DANGER).pack(anchor="w")
        self.btn_undo = ActionButton(
            hand_btns, "↶ Undo Last Discard",
            self._undo_discard, color=BTN_NEUTRAL,
        )
        self.btn_undo.pack(anchor="w", pady=(4, 0))

        _sep(left)

        # ── Card picker ────────────────────────────────────────────────────────
        self._section(
            left,
            "CARD PICKER  —  click cards you see in the real game to add/remove from hand",
        )
        picker_outer = tk.Frame(left, bg=PANEL, padx=6, pady=6)
        picker_outer.pack(anchor="w", pady=(0, 8))

        for row, color in enumerate(COLORS):
            row_frame = tk.Frame(picker_outer, bg=PANEL)
            row_frame.pack(anchor="w", pady=2)
            # colour label
            col_hex = COLOR_HEX[color]
            tk.Label(row_frame, text=f"{color.upper()[:3]}",
                     font=("Arial", 8, "bold"), bg=PANEL,
                     fg=col_hex, width=4).pack(side="left", padx=(0, 4))
            for num in NUMBERS:
                card = Card(num, color)
                pc = PickerCard(row_frame, card, self._picker_clicked)
                pc.pack(side="left", padx=2)
                self._picker[card] = pc

        _sep(left)

        # ── Log ────────────────────────────────────────────────────────────────
        self._section(left, "GAME LOG")
        self.log_text = tk.Text(
            left, height=5, bg="#0d0d1f", fg=MUTED,
            font=("Courier", 8), relief="flat", state="disabled",
            padx=6, pady=4,
        )
        self.log_text.pack(fill="x", pady=(0, 4))
        self.log_text.tag_configure("good", foreground=SUCCESS)
        self.log_text.tag_configure("warn", foreground=WARNING)
        self.log_text.tag_configure("head", foreground=ACCENT)
        # Colour tags for individual cards in the log
        self.log_text.tag_configure("card_yellow",
                                    foreground=COLOR_HEX["yellow"],
                                    font=("Courier", 8, "bold"))
        self.log_text.tag_configure("card_red",
                                    foreground=COLOR_HEX["red"],
                                    font=("Courier", 8, "bold"))
        self.log_text.tag_configure("card_blue",
                                    foreground="#5b8eff",   # lighter than card face for legibility on dark
                                    font=("Courier", 8, "bold"))

        # ── Solver panel ───────────────────────────────────────────────────────
        tk.Label(right, text="🧠  AI ANALYSIS", font=("Arial", 13, "bold"),
                 bg=PANEL, fg=ACCENT).pack(pady=(12, 4))
        ActionButton(right, "Analyse Now", self._run_solver,
                     color=ACCENT).pack(padx=10, fill="x", pady=(0, 4))
        self._auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(right, text="Auto-analyse on changes",
                       variable=self._auto_var,
                       bg=PANEL, fg=FG, activebackground=PANEL,
                       activeforeground=FG,
                       selectcolor=BG, font=("Arial", 9),
                       command=lambda: None).pack(padx=10, anchor="w")

        # Scrollable container for the analysis content (a Canvas wrapping a Frame)
        wrap = tk.Frame(right, bg=SOLVER_BG)
        wrap.pack(fill="both", expand=True, padx=6, pady=(4, 10))
        self.solver_canvas = tk.Canvas(
            wrap, bg=SOLVER_BG, highlightthickness=0,
        )
        sb = tk.Scrollbar(wrap, orient="vertical",
                          command=self.solver_canvas.yview)
        self.solver_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.solver_canvas.pack(side="left", fill="both", expand=True)

        self.solver_frame = tk.Frame(self.solver_canvas, bg=SOLVER_BG)
        self._solver_win = self.solver_canvas.create_window(
            (0, 0), window=self.solver_frame, anchor="nw",
        )
        self.solver_frame.bind(
            "<Configure>",
            lambda _e: self.solver_canvas.configure(
                scrollregion=self.solver_canvas.bbox("all")
            ),
        )
        self.solver_canvas.bind(
            "<Configure>",
            lambda e: self.solver_canvas.itemconfigure(
                self._solver_win, width=e.width
            ),
        )
        self.solver_canvas.bind(
            "<Enter>",
            lambda _e: self.solver_canvas.bind_all(
                "<MouseWheel>", self._on_solver_wheel
            ),
        )
        self.solver_canvas.bind(
            "<Leave>",
            lambda _e: self.solver_canvas.unbind_all("<MouseWheel>"),
        )

        # ── Status bar ─────────────────────────────────────────────────────────
        self.status_bar = tk.Label(
            self, text="Enter the 5 cards you see in the real game using the picker.",
            font=("Arial", 10), bg=BG, fg=FG, anchor="w", pady=5,
        )
        self.status_bar.pack(fill="x", padx=18, pady=(0, 6))

    # ─────────────────────────────────────────────────────────────────────────
    # Refresh
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh(self, auto_solve: bool = True) -> None:
        self._draw_stack()
        self._draw_hand()
        self._update_stats()
        self._update_picker_states()
        self._update_buttons()
        if auto_solve and self._auto_var.get():
            self._run_solver()

    def _draw_stack(self) -> None:
        _clear(self.stack_frame)
        for card in self.session.stack:
            SlotCard(self.stack_frame, card,
                     on_click=self._stack_card_clicked,
                     border_color=HL_RING).pack(side="left", padx=4)
        for _ in range(3 - len(self.session.stack)):
            SlotCard(self.stack_frame, None).pack(side="left", padx=4)

        n = len(self.session.stack)
        if n == 3:
            ok, pts, desc = score_combo(self.session.stack)
            if ok:
                self.stack_status.config(text=f"✓  {desc}", fg=SUCCESS)
            else:
                self.stack_status.config(text="✗  Invalid combination", fg=ACCENT)
        else:
            self.stack_status.config(text=f"{n}/3 cards selected", fg=MUTED)

    def _draw_hand(self) -> None:
        _clear(self.hand_frame)
        for card in self.session.hand:
            if card == self._drop_target:
                border = ACCENT      # red — this is the card the solver wants gone
            elif card in self._highlighted:
                border = HL_RING     # cyan — keep / play
            else:
                border = SUCCESS     # default green
            SlotCard(self.hand_frame, card,
                     on_click=self._hand_card_clicked,
                     on_right_click=self._hand_card_discard_one,
                     border_color=border).pack(side="left", padx=4)
        for _ in range(self.session.hand_capacity - len(self.session.hand)):
            SlotCard(self.hand_frame, None).pack(side="left", padx=4)

    def _update_picker_states(self) -> None:
        hand_set  = set(self.session.hand)
        stack_set = set(self.session.stack)
        disc_set  = set(self.session.discarded)
        scored_set: set = set()
        for sc in self.session.scored:
            scored_set.update(sc.cards)

        for card, widget in self._picker.items():
            if card in stack_set:
                widget.set_state("stack")
            elif card in hand_set:
                widget.set_state("hand")
            elif card in scored_set:
                widget.set_state("scored")
            elif card in disc_set:
                widget.set_state("discarded")
            else:
                widget.set_state("available")

    def _update_stats(self) -> None:
        s = self.session
        self.lbl_score.config( text=f"Score: {s.total_score}")
        self.lbl_combos.config(text=f"Combos: {len(s.scored)}")
        self.lbl_seen.config(  text=f"Seen: {s.cards_seen}/24")
        self.lbl_round.config( text=f"Round: {s.round}")
        self.lbl_deck.config(  text=f"Deck left: {len(s.remaining_deck)}")

    def _update_buttons(self) -> None:
        has_3 = len(self.session.stack) == 3
        self.btn_submit.config(state="normal" if has_3 else "disabled")
        can_undo = (
            len(self.session.discarded) > 0
            and not self.session.hand_full
        )
        self.btn_undo.config(state="normal" if can_undo else "disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # User actions
    # ─────────────────────────────────────────────────────────────────────────

    def _picker_clicked(self, card: Card) -> None:
        if card in self.session.hand:
            self.session.remove_from_hand(card)
            self._highlighted = [c for c in self._highlighted if c != card]
            self._refresh()
            return
        if card in self.session.stack or card in self.session.seen:
            self._status(f"{card} is already used — can't add it again.", WARNING)
            return
        err = self.session.add_to_hand(card)
        if err:
            self._status(err, WARNING)
            return
        self._refresh()

    def _hand_card_clicked(self, card: Card) -> None:
        if self.session.stack_full:
            self._status("Stack is full — submit or clear it first.", WARNING)
            return
        err = self.session.move_to_stack(card)
        if err:
            self._status(err, WARNING)
            return
        self._highlighted = [c for c in self._highlighted if c != card]
        self._refresh()

    def _hand_card_discard_one(self, card: Card) -> None:
        """Right-click on a hand card: discard just that one, then redraw
        recommendations.  The user then enters the replacement card via the
        picker once they see it in the real game."""
        if not self.session.discard_one(card):
            return
        self._highlighted = [c for c in self._highlighted if c != card]
        self._solve_result = None
        self._log_cards("Discarded: ", [card])
        self._status(
            f"Discarded {card}.  Enter the card you drew to replace it.",
            FG,
        )
        self._refresh()
        if self.session.cards_seen == 24:
            self._show_game_over()

    def _stack_card_clicked(self, card: Card) -> None:
        err = self.session.return_from_stack(card)
        if err:
            self._status(err, WARNING)
            return
        self._refresh()

    def _submit_combo(self) -> None:
        ok, pts, desc = self.session.submit_combo()
        if ok:
            self._status(f"✓  Combo scored!  +{pts} pts  ({desc})", SUCCESS)
            self._log(f"Combo scored: {desc}", "good")
            self._highlighted.clear()
            self._solve_result = None
            self._refresh()
            if self.session.cards_seen == 24:
                self._show_game_over()
        else:
            self._status(desc, ACCENT)

    def _clear_stack(self) -> None:
        self.session.clear_stack()
        self._refresh()
        self._status("Stack cleared — cards returned to hand.", MUTED)

    def _discard_hand(self) -> None:
        if not self.session.hand:
            self._status("Hand is empty — use the picker to enter your new cards.", WARNING)
            return
        gone = self.session.discard_hand()
        self._log_cards("Discarded: ", gone)
        capacity = self.session.hand_capacity
        self._status(
            f"Hand discarded ({len(gone)} card(s)).  "
            f"Now enter the new card(s) you drew "
            f"(stack has {len(self.session.stack)}).",
            FG,
        )
        self._highlighted.clear()
        self._solve_result = None
        self._refresh()
        if self.session.cards_seen == 24:
            self._show_game_over()

    def _undo_discard(self) -> None:
        card = self.session.undo_last_discard()
        if card is None:
            if self.session.hand_full:
                self._status("Hand is already full — can't undo.", WARNING)
            else:
                self._status("Nothing to undo.", MUTED)
            return
        self._log_cards("Undid discard: ", [card], tag="good")
        self._status(f"Restored {card} to hand.", FG)
        self._solve_result = None
        self._refresh()

    # ─────────────────────────────────────────────────────────────────────────
    # Solver
    # ─────────────────────────────────────────────────────────────────────────

    def _run_solver(self) -> None:
        if not self.session.hand and not self.session.stack:
            self._write_solver_idle()
            return
        result = solve(
            list(self.session.hand),
            list(self.session.stack),
            list(self.session.remaining_deck),
        )
        self._solve_result = result
        self._highlighted, self._drop_target = _highlight_from(result)
        self._draw_hand()
        self._write_solver(result)

    # ── Solver panel rendering (graphical) ───────────────────────────────────

    def _on_solver_wheel(self, event: tk.Event) -> None:
        self.solver_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _card_row(
        self,
        parent: tk.Widget,
        cards: List[Card],
        highlight: bool = False,
        dim: bool = False,
        bg: Optional[str] = None,
    ) -> tk.Frame:
        bg_col = bg or parent.cget("bg")
        row = tk.Frame(parent, bg=bg_col)
        row.pack(anchor="w", pady=2)
        for c in cards:
            MiniCard(row, c, highlight=highlight, dim=dim,
                     bg=bg_col).pack(side="left", padx=2)
        return row

    def _write_solver(self, r: Dict[str, Any]) -> None:
        f = self.solver_frame
        _clear(f)

        rec = r.get("recommendation", {})
        action = rec.get("action", "")
        deck_size = len(self.session.remaining_deck)

        # ── 1. RECOMMENDATION (top) ───────────────────────────────────────────
        rec_frame = tk.Frame(f, bg=REC_BG, bd=2,
                             highlightbackground=ACCENT,
                             highlightthickness=2)
        rec_frame.pack(fill="x", pady=(4, 10), padx=4)
        inner = tk.Frame(rec_frame, bg=REC_BG)
        inner.pack(fill="x", padx=10, pady=8)

        tk.Label(inner, text="▶  RECOMMENDATION",
                 font=("Arial", 11, "bold"), bg=REC_BG,
                 fg=ACCENT).pack(anchor="w")

        if action == "play":
            tk.Label(inner, text="PLAY THIS COMBO NOW",
                     font=("Arial", 14, "bold"), bg=REC_BG,
                     fg=SUCCESS).pack(anchor="w", pady=(4, 2))
            self._card_row(inner, rec["cards"], highlight=True, bg=REC_BG)
            tk.Label(inner, text=f"+{rec['score']} pts guaranteed",
                     font=("Arial", 11, "bold"), bg=REC_BG,
                     fg=SUCCESS).pack(anchor="w", pady=(4, 0))
            desc = rec.get("desc", "").split("→")[0].strip()
            if desc:
                tk.Label(inner, text=desc,
                         font=("Arial", 9), bg=REC_BG,
                         fg=MUTED, wraplength=280,
                         justify="left").pack(anchor="w")
            # Show why this combo over alternatives (residual EV)
            future_ev = rec.get("future_ev")
            total_ev = rec.get("total_ev")
            if future_ev is not None:
                tk.Label(inner,
                         text=f"Residual hand projects {future_ev:.0f} more "
                              f"pts → total play EV {total_ev:.0f}.",
                         font=("Arial", 9), bg=REC_BG, fg=MUTED,
                         wraplength=300,
                         justify="left").pack(anchor="w", pady=(2, 0))

        elif action == "discard_one":
            drop = rec["drop"]
            tk.Label(inner, text="DISCARD THIS ONE CARD",
                     font=("Arial", 14, "bold"), bg=REC_BG,
                     fg=WARNING).pack(anchor="w", pady=(4, 2))
            self._card_row(inner, [drop], highlight=True, bg=REC_BG)
            tk.Label(inner,
                     text="Right-click it in your hand to discard, then enter "
                          "the replacement card you drew.",
                     font=("Arial", 8, "italic"), bg=REC_BG,
                     fg=MUTED, wraplength=300,
                     justify="left").pack(anchor="w", pady=(2, 0))

            tk.Label(inner, text=f"Keeping ({len(rec.get('keep',[]))}):",
                     font=("Arial", 9, "bold"), bg=REC_BG,
                     fg=SUCCESS).pack(anchor="w", pady=(8, 1))
            self._card_row(inner, rec.get("keep", []),
                           highlight=True, bg=REC_BG)

            need_cards = rec.get("need_cards", [])
            if need_cards:
                tk.Label(inner, text="Best draws to hope for:",
                         font=("Arial", 9, "bold"), bg=REC_BG,
                         fg=FG).pack(anchor="w", pady=(6, 1))
                self._card_row(inner, need_cards[:6], bg=REC_BG)

            p = rec.get("prob", 0.0)
            ev = rec.get("ev", 0.0)
            stat_color = SUCCESS if p >= 0.5 else WARNING
            tk.Label(inner,
                     text=f"1-step EV = {ev:.0f} pts     "
                          f"P(any combo on next draw) = {p:.0%}",
                     font=("Arial", 11, "bold"), bg=REC_BG,
                     fg=stat_color).pack(anchor="w", pady=(8, 0))
            if "alt_play_score" in rec:
                tk.Label(inner,
                         text=f"(or play {rec['alt_play_score']} pts now)",
                         font=("Arial", 9, "italic"), bg=REC_BG,
                         fg=WARNING).pack(anchor="w")

        elif action == "draw_more":
            missing = rec.get("missing", 0)
            tk.Label(inner, text=f"DRAW {missing} MORE CARD(S)",
                     font=("Arial", 14, "bold"), bg=REC_BG,
                     fg=HL_RING).pack(anchor="w", pady=(4, 2))
            tk.Label(inner,
                     text="Your hand isn't full — no discard is needed yet. "
                          "Just enter the next cards you draw, then re-analyse.",
                     font=("Arial", 9), bg=REC_BG, fg=FG,
                     wraplength=300,
                     justify="left").pack(anchor="w", pady=(2, 0))

        elif action == "keep_and_draw":
            # Legacy fallback: shouldn't normally hit with new solver
            keep = rec.get("keep", [])
            discard = rec.get("discard", [])
            tk.Label(inner, text="(legacy advice — please refresh)",
                     font=("Arial", 9, "italic"), bg=REC_BG,
                     fg=MUTED).pack(anchor="w")
            if keep:
                self._card_row(inner, keep, highlight=True, bg=REC_BG)

        # Reasoning bullets
        for line in rec.get("reasoning", [])[:4]:
            tk.Label(inner, text=f"• {line}",
                     font=("Arial", 8), bg=REC_BG, fg=MUTED,
                     wraplength=280, justify="left").pack(anchor="w", pady=(2, 0))

        # ── 2. VALID COMBOS NOW ───────────────────────────────────────────────
        self._section_header(f, "✓  VALID COMBOS NOW")
        combos = r.get("immediate_combos", [])
        if combos:
            for cards, pts, desc in combos[:3]:
                sub = tk.Frame(f, bg=SOLVER_BG)
                sub.pack(fill="x", padx=6, pady=2, anchor="w")
                self._card_row(sub, cards, bg=SOLVER_BG)
                label_desc = desc.split("→")[0].strip()
                tk.Label(sub, text=f"{pts} pts  ·  {label_desc}",
                         font=("Arial", 9, "bold"), bg=SOLVER_BG,
                         fg=SUCCESS, wraplength=300,
                         justify="left").pack(anchor="w", pady=(0, 2))
        else:
            tk.Label(f, text="  None with current cards.",
                     font=("Arial", 9, "italic"), bg=SOLVER_BG,
                     fg=MUTED).pack(anchor="w", padx=8, pady=(0, 4))

        # ── 3. DISCARD ONE CARD (per-card EV ranking) ────────────────────────
        single_discards = r.get("single_discards", [])
        if single_discards:
            self._section_header(f, "⇄  DISCARD ONE CARD (per-card EV)")
            tk.Label(f,
                     text="If you discard this card and draw 1 from the deck, "
                          "what's your expected best combo over the next 1–2 moves?",
                     font=("Arial", 8, "italic"), bg=SOLVER_BG,
                     fg=MUTED, wraplength=310,
                     justify="left").pack(anchor="w", padx=8, pady=(0, 4))
            best_ev = single_discards[0]["ev"]
            for sd in single_discards:
                self._render_single_discard(f, sd, best_ev)

        # ── 4. NEAR COMBOS ────────────────────────────────────────────────────
        self._section_header(f, "◯  NEAR COMBOS (hope to draw)")
        nears = r.get("near_combos", [])
        if nears:
            for nc in nears[:4]:
                self._render_near(f, nc, deck_size)
        else:
            tk.Label(f, text="  None.",
                     font=("Arial", 9, "italic"), bg=SOLVER_BG,
                     fg=MUTED).pack(anchor="w", padx=8, pady=(0, 4))

        # ── 5. Baseline ───────────────────────────────────────────────────────
        tk.Label(f,
                 text=f"Fresh-draw baseline EV ≈ {r.get('fresh_ev', 0):.0f} pts",
                 font=("Arial", 8, "italic"), bg=SOLVER_BG,
                 fg=MUTED).pack(anchor="w", padx=8, pady=(8, 8))

        # Scroll to top after rebuild
        self.solver_canvas.yview_moveto(0.0)

    def _section_header(self, parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text,
                 font=("Arial", 10, "bold"), bg=SOLVER_BG,
                 fg=ACCENT).pack(anchor="w", padx=6, pady=(10, 2))

    def _render_single_discard(
        self, parent: tk.Widget, sd: Dict[str, Any], best_ev: float,
    ) -> None:
        """One row in the DISCARD ONE CARD panel: drop, keep, EV, best draw."""
        is_best = abs(sd["ev"] - best_ev) < 0.5

        sub = tk.Frame(parent, bg=SOLVER_BG)
        sub.pack(fill="x", padx=6, pady=3, anchor="w")

        head_color = SUCCESS if is_best else FG
        head = f"Drop {sd['drop']}"
        if is_best:
            head += "   ← BEST"
        tk.Label(sub, text=head,
                 font=("Arial", 9, "bold"), bg=SOLVER_BG,
                 fg=head_color).pack(anchor="w")

        row = tk.Frame(sub, bg=SOLVER_BG)
        row.pack(anchor="w", pady=1)
        # Show the drop card dimmed (but keeping its colour)
        MiniCard(row, sd["drop"], dim=True,
                 bg=SOLVER_BG).pack(side="left", padx=(0, 4))
        tk.Label(row, text="→  keep", font=("Arial", 8),
                 bg=SOLVER_BG, fg=MUTED).pack(side="left", padx=(0, 4))
        for c in sd["keep"]:
            MiniCard(row, c, highlight=is_best,
                     bg=SOLVER_BG).pack(side="left", padx=1)

        bo = sd.get("best_outcome")
        bo_str = ""
        if bo:
            be_cards, be_pts, _ = bo
            bo_str = f"   best draw → {be_pts} pts ({' '.join(str(c) for c in be_cards)})"
        tk.Label(sub,
                 text=(f"EV {sd['ev']:.0f}   "
                       f"P {sd['prob']:.0%}{bo_str}"),
                 font=("Arial", 8), bg=SOLVER_BG,
                 fg=SUCCESS if is_best else MUTED).pack(anchor="w")

    def _render_alt_keep(self, parent: tk.Widget, k: Dict[str, Any],
                         best_adj: float) -> None:
        """One row in the DISCARD OPTIONS panel — keep/discard layout + EV."""
        n_draw = k["n_draw"]
        is_best = abs(k["adjusted_ev"] - best_adj) < 0.5

        sub = tk.Frame(parent, bg=SOLVER_BG)
        sub.pack(fill="x", padx=6, pady=3, anchor="w")

        head_color = SUCCESS if is_best else FG
        head = f"Discard {n_draw}"
        if is_best:
            head += "   ← BEST"
        tk.Label(sub, text=head,
                 font=("Arial", 9, "bold"), bg=SOLVER_BG,
                 fg=head_color).pack(anchor="w")

        row = tk.Frame(sub, bg=SOLVER_BG)
        row.pack(anchor="w", pady=1)
        if k["keep"]:
            tk.Label(row, text="keep", font=("Arial", 8),
                     bg=SOLVER_BG, fg=MUTED).pack(side="left", padx=(0, 2))
            for c in k["keep"]:
                MiniCard(row, c, highlight=is_best,
                         bg=SOLVER_BG).pack(side="left", padx=1)
        if k["discard"]:
            tk.Label(row, text="  drop", font=("Arial", 8),
                     bg=SOLVER_BG, fg=MUTED).pack(side="left", padx=(6, 2))
            for c in k["discard"]:
                MiniCard(row, c, dim=True,
                         bg=SOLVER_BG).pack(side="left", padx=1)

        tk.Label(sub,
                 text=(f"raw EV {k['ev']:.0f}   "
                       f"adj {k['adjusted_ev']:.0f}   "
                       f"P={k['prob']:.0%}"),
                 font=("Arial", 8), bg=SOLVER_BG,
                 fg=SUCCESS if is_best else MUTED).pack(anchor="w")

    def _render_near(self, parent: tk.Widget, nc: Dict[str, Any],
                     deck_size: int) -> None:
        sub = tk.Frame(parent, bg=SOLVER_BG)
        sub.pack(fill="x", padx=6, pady=3, anchor="w")

        line = tk.Frame(sub, bg=SOLVER_BG)
        line.pack(anchor="w")
        for c in nc["pair"]:
            MiniCard(line, c, highlight=True,
                     bg=SOLVER_BG).pack(side="left", padx=2)
        tk.Label(line, text="+", font=("Arial", 14, "bold"),
                 bg=SOLVER_BG, fg=MUTED).pack(side="left", padx=4)
        need_cards = nc.get("need_cards", [])
        for c in need_cards[:3]:
            MiniCard(line, c, bg=SOLVER_BG).pack(side="left", padx=2)
        extra = len(need_cards) - 3
        if extra > 0:
            tk.Label(line, text=f"(+{extra} more)",
                     font=("Arial", 8), bg=SOLVER_BG,
                     fg=MUTED).pack(side="left", padx=4)

        p = nc["prob"]
        color = SUCCESS if p >= 0.5 else WARNING
        tk.Label(sub,
                 text=(f"P = {p:.0%}   "
                       f"best {nc['best_score']}   "
                       f"EV {nc['ev']:.0f}   "
                       f"({nc['need_count']} of {deck_size} left)"),
                 font=("Arial", 9), bg=SOLVER_BG,
                 fg=color).pack(anchor="w", pady=(1, 0))

    def _write_solver_idle(self) -> None:
        _clear(self.solver_frame)
        tk.Label(self.solver_frame,
                 text="Enter cards using the picker\nto see analysis here.",
                 font=("Arial", 9), bg=SOLVER_BG, fg=MUTED,
                 justify="left").pack(padx=16, pady=20, anchor="w")

    # ─────────────────────────────────────────────────────────────────────────
    # End game (in-window, no popup)
    # ─────────────────────────────────────────────────────────────────────────

    def _show_game_over(self) -> None:
        # Guard: only one overlay at a time
        if self._game_over_overlay is not None:
            return

        score  = self.session.total_score
        combos = len(self.session.scored)
        tier   = "GOLD 🥇" if score >= 400 else "SILVER 🥈" if score >= 300 else "BRONZE 🥉"

        # Full-window dimming scrim
        scrim = tk.Frame(self, bg="#000000")
        scrim.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._game_over_overlay = scrim

        # Centered card inside the scrim
        card = tk.Frame(scrim, bg="#0a0a1e", bd=2, relief="ridge",
                        highlightbackground=ACCENT, highlightthickness=2)
        card.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(card, text="GAME OVER", font=("Arial", 22, "bold"),
                 bg="#0a0a1e", fg=ACCENT, padx=40, pady=10).pack()
        tk.Label(card, text=f"Final Score:  {score} pts",
                 font=("Arial", 14), bg="#0a0a1e", fg=FG).pack(pady=(0, 4))
        tk.Label(card, text=f"Combos Made:  {combos}",
                 font=("Arial", 12), bg="#0a0a1e", fg=MUTED).pack()
        tk.Label(card, text=f"Tier:  {tier}",
                 font=("Arial", 14, "bold"), bg="#0a0a1e", fg=SUCCESS,
                 pady=8).pack()

        btns = tk.Frame(card, bg="#0a0a1e")
        btns.pack(padx=20, pady=(8, 16))

        def _play_again():
            self._dismiss_game_over()
            self._new_game()

        def _close():
            self._dismiss_game_over()

        ActionButton(btns, "Play Again", _play_again, color=BTN_SUCCESS).pack(
            side="left", padx=4)
        ActionButton(btns, "Dismiss", _close, color=BTN_NEUTRAL).pack(
            side="left", padx=4)

        # Ensure overlay is on top of everything
        scrim.lift()
        scrim.focus_set()
        # Also dismiss on Esc
        self.bind("<Escape>", lambda _e: self._dismiss_game_over())

        self._log(f"Game over! Score: {score}  Tier: {tier}", "head")

    def _dismiss_game_over(self) -> None:
        if self._game_over_overlay is not None:
            self._game_over_overlay.destroy()
            self._game_over_overlay = None
            self.unbind("<Escape>")

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    def _new_game(self) -> None:
        self._dismiss_game_over()
        self.session.reset()
        self._highlighted.clear()
        self._solve_result = None
        self._clear_solver()
        self._refresh(auto_solve=False)
        self._log("─── New game started ───", "head")
        self._status("New game! Enter the 5 cards you see in the picker.", SUCCESS)

    def _status(self, msg: str, color: str = FG) -> None:
        self.status_bar.config(text=msg, fg=color)

    def _log(self, msg: str, tag: str = "") -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _log_cards(self, prefix: str, cards: List[Card],
                   tag: str = "warn") -> None:
        """Append a log line where each card is rendered in its own colour."""
        self.log_text.config(state="normal")
        self.log_text.insert("end", prefix, tag)
        for i, c in enumerate(cards):
            if i:
                self.log_text.insert("end", " ", tag)
            self.log_text.insert("end", str(c), f"card_{c.color}")
        self.log_text.insert("end", "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_solver(self) -> None:
        _clear(self.solver_frame)

    @staticmethod
    def _stat(parent: tk.Frame, text: str, color: str = FG) -> tk.Label:
        lbl = tk.Label(parent, text=text, font=("Arial", 10), bg=BG, fg=color)
        lbl.pack(side="left", padx=10)
        return lbl

    @staticmethod
    def _section(parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text, font=("Arial", 9, "bold"),
                 bg=BG, fg=MUTED).pack(anchor="w", pady=(6, 2))


# ── Module-level helpers ──────────────────────────────────────────────────────

def _clear(frame: tk.Frame) -> None:
    for w in frame.winfo_children():
        w.destroy()


def _sep(parent: tk.Widget) -> None:
    tk.Frame(parent, bg="#2a2a44", height=1).pack(fill="x", pady=4)


def _highlight_from(result: Dict[str, Any]) -> Tuple[List[Card], Optional[Card]]:
    """Returns (highlighted_keep_cards, drop_target_card)."""
    rec    = result.get("recommendation", {})
    action = rec.get("action", "")
    if action == "play":
        return list(rec.get("cards", [])), None
    if action == "discard_one":
        return list(rec.get("keep", [])), rec.get("drop")
    if action == "keep_and_draw":
        return list(rec.get("keep", [])), rec.get("first_drop")
    return [], None


# ── Easter egg ────────────────────────────────────────────────────────────────

class _KremuwkaEgg:
    """
    Fetches a GIF once, then shows a popup:
      • once at a random moment 5–15 min after launch
      • always when the local clock hits 21:37 (once per day)
    Gracefully degrades to a text-only popup if the download or GIF decode fails.
    """

    GIF_URL = (
        "https://images.steamusercontent.com/ugc/544154344545956752/"
        "125260318A6E3AC2B729722D743E1C31C6DBD111/"
        "?imw=5000&imh=5000&ima=fit&impolicy=Letterbox"
        "&imcolor=%23000000&letterbox=false"
    )

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.gif_path: Optional[str] = None
        self._random_fired = False
        self._last_daily_key: Optional[str] = None

        threading.Thread(target=self._download, daemon=True).start()

        delay_ms = int(random.uniform(5 * 60, 15 * 60) * 1000)
        root.after(delay_ms, self._random_fire)
        root.after(30_000, self._tick_daily)

    def _download(self) -> None:
        try:
            req = urllib.request.Request(
                self.GIF_URL,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            if not data:
                return
            tmp = tempfile.NamedTemporaryFile(suffix=".gif", delete=False)
            tmp.write(data)
            tmp.close()
            self.gif_path = tmp.name
        except Exception:
            pass

    def _random_fire(self) -> None:
        if not self._random_fired:
            self._random_fired = True
            self._show()

    def _tick_daily(self) -> None:
        try:
            now = datetime.datetime.now()
            if now.hour == 21 and now.minute == 37:
                key = now.strftime("%Y-%m-%d")
                if self._last_daily_key != key:
                    self._last_daily_key = key
                    self._show()
        finally:
            self.root.after(30_000, self._tick_daily)

    def _show(self) -> None:
        try:
            top = tk.Toplevel(self.root)
        except tk.TclError:
            return
        top.title("INSERT KREMUWKA")
        top.configure(bg="#000000")
        top.resizable(False, False)

        tk.Label(top, text="INSERT KREMUWKA",
                 font=("Arial", 28, "bold"),
                 fg="#ffcc00", bg="#000000",
                 padx=24, pady=14).pack()

        if self.gif_path and os.path.exists(self.gif_path):
            frames: List[tk.PhotoImage] = []
            i = 0
            while True:
                try:
                    frames.append(
                        tk.PhotoImage(file=self.gif_path,
                                      format=f"gif -index {i}")
                    )
                    i += 1
                except tk.TclError:
                    break
            if frames:
                img = tk.Label(top, bg="#000000")
                img.pack(padx=20, pady=(0, 10))
                img.image_refs = frames  # type: ignore[attr-defined]

                def animate(idx: int = 0) -> None:
                    if not img.winfo_exists():
                        return
                    img.configure(image=frames[idx])
                    top.after(90, animate, (idx + 1) % len(frames))

                animate()

        tk.Button(top, text="OK", command=top.destroy,
                  bg="#ffcc00", fg="#000000",
                  font=("Arial", 12, "bold"),
                  relief="flat", padx=28, pady=6,
                  activebackground="#ffdd33",
                  cursor="hand2").pack(pady=(4, 20))

        top.transient(self.root)
        top.lift()
        top.attributes("-topmost", True)
        top.after(200, lambda: top.attributes("-topmost", False))
        top.update_idletasks()
        w = top.winfo_width()
        h = top.winfo_height()
        sw = top.winfo_screenwidth()
        sh = top.winfo_screenheight()
        top.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
