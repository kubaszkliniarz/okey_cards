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
import tkinter as tk
from tkinter import font as tkfont
from typing import Dict, List, Optional, Any

from okey_logic.game import Card, COLORS, NUMBERS, score_combo
from okey_logic.session import SolverSession, ALL_CARDS
from okey_logic.solver import solve
from okey_gui.widgets import (
    BG, PANEL, ACCENT, SUCCESS, WARNING, MUTED, FG, HL_RING,
    CardWidget, ActionButton,
)

PICKER_CARD_W = 52
PICKER_CARD_H = 72
CARD_PAD      = 3

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
                 border_color="#333355", **kw):
        super().__init__(parent, width=self.W, height=self.H,
                         bg=PANEL, highlightthickness=0,
                         cursor="hand2" if (card and on_click) else "arrow", **kw)
        self.card = card
        if on_click and card:
            self.bind("<Button-1>", lambda _e: on_click(card))
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
        self._highlighted: List[Card] = []

        self._build_ui()
        self._refresh()

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
                     color="#333355").pack(side="right")

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
        right = tk.Frame(body, bg=PANEL, width=280)
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
                                       self._submit_combo, color="#1a5c1a")
        self.btn_submit.pack(anchor="w", pady=(0, 4))
        ActionButton(stack_btns, "↩ Clear Stack",
                     self._clear_stack, color="#333355").pack(anchor="w")
        self.stack_status = tk.Label(left, text="", font=("Arial", 10),
                                     bg=BG, fg=MUTED)
        self.stack_status.pack(anchor="w", pady=(0, 4))

        _sep(left)

        # ── Hand ───────────────────────────────────────────────────────────────
        self._section(left, "CURRENT HAND  —  click a hand card to move it to the stack")
        hand_outer = tk.Frame(left, bg=BG)
        hand_outer.pack(anchor="w", pady=(0, 6))
        self.hand_frame = tk.Frame(hand_outer, bg=PANEL, padx=8, pady=6)
        self.hand_frame.pack(side="left")
        ActionButton(hand_outer, "↺ Discard Hand & Draw",
                     self._discard_hand, color="#5c1a1a").pack(
            side="left", padx=(12, 0))

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

        # ── Solver panel ───────────────────────────────────────────────────────
        tk.Label(right, text="🧠  AI ANALYSIS", font=("Arial", 13, "bold"),
                 bg=PANEL, fg=ACCENT).pack(pady=(12, 4))
        ActionButton(right, "Analyse Now", self._run_solver,
                     color=ACCENT).pack(padx=10, fill="x", pady=(0, 4))
        self._auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(right, text="Auto-analyse on changes",
                       variable=self._auto_var,
                       bg=PANEL, fg=MUTED, activebackground=PANEL,
                       selectcolor=BG, font=("Arial", 9),
                       command=lambda: None).pack(padx=10, anchor="w")
        self.solver_text = tk.Text(
            right, bg="#0d0d1f", fg=FG, font=("Courier", 9),
            wrap="word", state="disabled", relief="flat",
            padx=8, pady=8, spacing1=1,
        )
        self.solver_text.pack(fill="both", expand=True, padx=6, pady=(4, 10))
        _configure_tags(self.solver_text)

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
            hl = card in self._highlighted
            border = HL_RING if hl else SUCCESS
            SlotCard(self.hand_frame, card,
                     on_click=self._hand_card_clicked,
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
            elif card in disc_set or card in scored_set:
                widget.set_state("discarded" if card in disc_set else "scored")
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
        gone_str = "  ".join(str(c) for c in gone)
        self._log(f"Discarded: {gone_str}", "warn")
        capacity = self.session.hand_capacity
        self._status(
            f"Hand discarded.  Now enter the {capacity} new card(s) you drew "
            f"(stack has {len(self.session.stack)}).",
            FG,
        )
        self._highlighted.clear()
        self._solve_result = None
        self._refresh()
        if self.session.cards_seen == 24:
            self._show_game_over()

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
        self._highlighted = _highlight_from(result)
        self._draw_hand()
        self._write_solver(result)

    def _write_solver(self, r: Dict[str, Any]) -> None:
        t = self.solver_text
        t.config(state="normal")
        t.delete("1.0", "end")

        def w(text: str, tag: str = "") -> None:
            t.insert("end", text, tag)

        deck_size = len(self.session.remaining_deck)

        # ── Valid combos ──────────────────────────────────────────────────────
        w("═══ VALID COMBOS NOW ═══\n", "hdr")
        combos = r.get("immediate_combos", [])
        if combos:
            for cards, pts, desc in combos[:4]:
                w(f"  {desc}\n", "good")
                w(f"  Cards: {[str(c) for c in cards]}\n\n", "muted")
        else:
            w("  None with current cards.\n\n", "muted")

        # ── Near combos ───────────────────────────────────────────────────────
        w("═══ NEAR COMBOS ═══\n", "hdr")
        nears = r.get("near_combos", [])
        if nears:
            for nc in nears[:4]:
                pair_str = " + ".join(str(c) for c in nc["pair"])
                w(f"  Keep: {pair_str}\n", "hl")
                w(f"  Need: {nc['need_count']}× card in deck ({deck_size} left)\n")
                w(f"  Examples: {', '.join(nc['need_examples'])}\n", "muted")
                tag = "good" if nc["prob"] >= 0.5 else "warn"
                w(f"  P={nc['prob']:.0%}  score={nc['best_score']}  EV={nc['ev']:.0f}\n",
                  tag)
                w(f"  → {nc['best_desc']}\n\n", "muted")
        else:
            w("  None.\n\n", "muted")

        # ── Two-pair ─────────────────────────────────────────────────────────
        tp = r.get("two_pair")
        if tp and tp["ev"] > 0:
            w("═══ TWO-PAIR OPTION ═══\n", "hdr")
            p1 = " + ".join(str(c) for c in tp["pair1"])
            p2 = " + ".join(str(c) for c in tp["pair2"])
            w(f"  Keep: {p1}\n", "hl")
            w(f"  Keep: {p2}\n", "hl")
            tag = "good" if tp["prob"] >= 0.4 else "warn"
            w(f"  P={tp['prob']:.0%}  draw {tp['n_draw']}  EV={tp['ev']:.0f}\n\n", tag)

        # ── EV baseline ───────────────────────────────────────────────────────
        w(f"Fresh draw EV ≈ {r.get('fresh_ev', 0):.0f} pts\n\n", "muted")

        # ── Recommendation ────────────────────────────────────────────────────
        w("═══ RECOMMENDATION ═══\n", "hdr")
        rec = r.get("recommendation", {})
        action = rec.get("action", "")

        if action == "play":
            w("  ✓ PLAY THESE 3 CARDS NOW\n", "good")
            w(f"  {[str(c) for c in rec['cards']]}\n", "good")
            w(f"  Score: {rec['score']} pts\n\n", "good")
        elif action == "keep_and_draw":
            w("  ↻ KEEP THIS PAIR, DISCARD THE REST\n", "hl")
            keep_str = " + ".join(str(c) for c in rec["keep"])
            w(f"  Keep:    {keep_str}\n", "hl")
            if rec.get("discard"):
                w(f"  Discard: {[str(c) for c in rec['discard']]}\n", "muted")
            need = rec.get("need_examples", [])
            if need:
                w(f"  Hoping for: {', '.join(need)}\n")
            tag = "good" if rec.get("prob", 0) >= 0.5 else "warn"
            w(f"  P={rec.get('prob', 0):.0%}  EV={rec.get('ev', 0):.0f} pts\n\n", tag)
            if "alt_play_score" in rec:
                w(f"  (Alt: play now for {rec['alt_play_score']} pts guaranteed)\n\n",
                  "warn")
        elif action == "keep_two_pairs":
            w("  ↻ KEEP BOTH PAIRS\n", "hl")
            p1 = " + ".join(str(c) for c in rec["pair1"])
            p2 = " + ".join(str(c) for c in rec["pair2"])
            w(f"  Pair 1: {p1}\n", "hl")
            w(f"  Pair 2: {p2}\n", "hl")
            if rec.get("discard"):
                w(f"  Discard: {[str(c) for c in rec['discard']]}\n", "muted")
            tag = "good" if rec.get("prob", 0) >= 0.4 else "warn"
            w(f"  P={rec.get('prob', 0):.0%}  EV={rec.get('ev', 0):.0f} pts\n\n", tag)
        else:
            w("  ↺ DISCARD ALL, DRAW FRESH\n", "warn")
            w(f"  No profitable partial combos.  EV≈{rec.get('ev', 0):.0f}\n\n", "muted")

        for line in rec.get("reasoning", []):
            w(f"  • {line}\n", "muted")

        t.config(state="disabled")

    def _write_solver_idle(self) -> None:
        t = self.solver_text
        t.config(state="normal")
        t.delete("1.0", "end")
        t.insert("end", "Enter cards using the picker\nto see analysis here.", "muted")
        t.config(state="disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # End game (in-window, no popup)
    # ─────────────────────────────────────────────────────────────────────────

    def _show_game_over(self) -> None:
        score  = self.session.total_score
        combos = len(self.session.scored)
        tier   = "GOLD 🥇" if score >= 400 else "SILVER 🥈" if score >= 300 else "BRONZE 🥉"

        # Overlay frame on top of everything
        overlay = tk.Frame(self, bg="#0a0a1e", bd=2, relief="ridge")
        overlay.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(overlay, text="GAME OVER", font=("Arial", 22, "bold"),
                 bg="#0a0a1e", fg=ACCENT, pady=10).pack()
        tk.Label(overlay, text=f"Final Score:  {score} pts",
                 font=("Arial", 14), bg="#0a0a1e", fg=FG).pack(pady=(0, 4))
        tk.Label(overlay, text=f"Combos Made:  {combos}",
                 font=("Arial", 12), bg="#0a0a1e", fg=MUTED).pack()
        tk.Label(overlay, text=f"Tier:  {tier}",
                 font=("Arial", 14, "bold"), bg="#0a0a1e", fg=SUCCESS,
                 pady=8).pack()

        def _new():
            overlay.destroy()
            self._new_game()

        ActionButton(overlay, "Play Again", _new, color=ACCENT).pack(
            padx=20, pady=(8, 16))

        self._log(f"Game over! Score: {score}  Tier: {tier}", "head")

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    def _new_game(self) -> None:
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

    def _clear_solver(self) -> None:
        self.solver_text.config(state="normal")
        self.solver_text.delete("1.0", "end")
        self.solver_text.config(state="disabled")

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


def _configure_tags(t: tk.Text) -> None:
    t.tag_configure("hdr",  foreground=ACCENT,   font=("Courier", 9, "bold"))
    t.tag_configure("good", foreground=SUCCESS)
    t.tag_configure("warn", foreground=WARNING)
    t.tag_configure("muted",foreground=MUTED)
    t.tag_configure("hl",   foreground=HL_RING)


def _highlight_from(result: Dict[str, Any]) -> List[Card]:
    rec    = result.get("recommendation", {})
    action = rec.get("action", "")
    if action == "play":
        return list(rec.get("cards", []))
    if action == "keep_and_draw":
        return list(rec.get("keep", []))
    if action == "keep_two_pairs":
        return rec.get("pair1", []) + rec.get("pair2", [])
    return []
