"""
SolverSession — tracks one full game of Okey from the solver's perspective.

The solver never draws cards itself.  The user enters which cards they see
in the real game; the session tracks what has been seen to compute the
remaining deck for probability calculations.

Terminology
───────────
  hand   – cards currently visible in the user's hand (user-entered)
  stack  – answer area: 0–3 cards chosen toward the next combo
  seen   – every card that has appeared (hand + stack + discarded + scored)
  remaining_deck – all 24 cards minus seen
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set

from okey_logic.game import Card, COLORS, NUMBERS, score_combo

ALL_CARDS: List[Card] = [Card(n, c) for c in COLORS for n in NUMBERS]
TOTAL_CARDS = len(ALL_CARDS)      # 24
MAX_STACK   = 3
MAX_VISIBLE = 5                   # hand + stack always ≤ 5


@dataclass
class ScoredCombo:
    cards: List[Card]
    points: int
    description: str


class SolverSession:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.hand: List[Card] = []            # currently in hand (user sees these)
        self.stack: List[Card] = []           # answer area (chosen toward combo)
        self.discarded: List[Card] = []       # permanently gone
        self.scored: List[ScoredCombo] = []   # completed combos
        self.total_score: int = 0
        self.round: int = 1

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def seen(self) -> Set[Card]:
        s: Set[Card] = set(self.hand) | set(self.stack) | set(self.discarded)
        for sc in self.scored:
            s.update(sc.cards)
        return s

    @property
    def remaining_deck(self) -> List[Card]:
        seen = self.seen
        return [c for c in ALL_CARDS if c not in seen]

    @property
    def hand_capacity(self) -> int:
        """How many cards the user can hold in hand right now."""
        return MAX_VISIBLE - len(self.stack)

    @property
    def hand_full(self) -> bool:
        return len(self.hand) >= self.hand_capacity

    @property
    def stack_full(self) -> bool:
        return len(self.stack) >= MAX_STACK

    @property
    def cards_seen(self) -> int:
        return len(self.seen)

    # ── Actions ───────────────────────────────────────────────────────────────

    def add_to_hand(self, card: Card) -> str:
        """Add a card the user drew to the hand. Returns error string or ''."""
        if card in self.seen:
            return f"{card} already used this game."
        if self.hand_full:
            return f"Hand is full ({self.hand_capacity} slots; {len(self.stack)} on stack)."
        self.hand.append(card)
        return ""

    def remove_from_hand(self, card: Card) -> bool:
        """Remove a card from hand (user correcting input)."""
        if card in self.hand:
            self.hand.remove(card)
            return True
        return False

    def move_to_stack(self, card: Card) -> str:
        """Move a hand card onto the answer stack."""
        if card not in self.hand:
            return f"{card} is not in hand."
        if self.stack_full:
            return "Stack is full (3 cards)."
        self.hand.remove(card)
        self.stack.append(card)
        return ""

    def return_from_stack(self, card: Card) -> str:
        """Return a stack card back to hand."""
        if card not in self.stack:
            return f"{card} is not on the stack."
        # Hand must have room — it always does since stack shrank by 1
        self.stack.remove(card)
        self.hand.append(card)
        return ""

    def discard_hand(self) -> List[Card]:
        """
        Discard all current hand cards (they are permanently gone from the deck).
        Returns the discarded cards.  Call this before entering the next hand.
        """
        gone = list(self.hand)
        self.discarded.extend(gone)
        self.hand.clear()
        self.round += 1
        return gone

    def discard_one(self, card: Card) -> bool:
        """
        Discard a single hand card (permanently gone from the deck).  Used when
        the user discards one card at a time in the real game and wants the
        solver to update EV before they enter the replacement.  Returns True
        on success.
        """
        if card not in self.hand:
            return False
        self.hand.remove(card)
        self.discarded.append(card)
        return True

    def undo_last_discard(self) -> Optional[Card]:
        """
        Return the most recently discarded card to the hand.  Returns the
        card on success, or None if there's nothing to undo or the hand is
        already at capacity.  Discarding is the only otherwise-irreversible
        action; this restores it.
        """
        if not self.discarded:
            return None
        if self.hand_full:
            return None
        card = self.discarded.pop()
        self.hand.append(card)
        return card

    def submit_combo(self) -> Tuple[bool, int, str]:
        """
        Validate and score the current stack (must have exactly 3 cards).
        On success → clears stack, records the combo in `scored`.  Hand is
        left untouched — discards must be explicit.  Scored cards are not
        added to `discarded`; `seen` already counts them via `scored`.
        Returns (success, points, description).
        """
        if len(self.stack) != MAX_STACK:
            return False, 0, f"Need exactly {MAX_STACK} cards on stack (have {len(self.stack)})."
        valid, pts, desc = score_combo(self.stack)
        if valid:
            self.scored.append(ScoredCombo(list(self.stack), pts, desc))
            self.stack.clear()
            self.total_score += pts
            return True, pts, desc
        return False, 0, "Invalid combination — try a different set of 3 cards."

    def clear_stack(self) -> None:
        """Return all stack cards to hand."""
        while self.stack:
            self.hand.append(self.stack.pop())
