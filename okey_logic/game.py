"""
Core game logic: cards, deck, scoring, game state.

Deck: 24 cards  —  numbers 1–8, colors yellow / red / blue (one of each combo).
Scoring (exactly 3-card hands), matching the open-sourced game clone
this tool is built to solve — verified against in-game observations:
  Run, same colour                  →  100                 (flat)
  Run, mixed colour                 →  10 × min(numbers)  [10 … 60]
  Set (same number, all 3 colours)  →  10 × (number + 1)  [20 … 90]
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

COLORS: List[str] = ["yellow", "red", "blue"]
NUMBERS: List[int] = list(range(1, 9))  # 1–8


# ── Card ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Card:
    number: int
    color: str

    def __str__(self) -> str:
        return f"{self.color[0].upper()}{self.number}"

    def __repr__(self) -> str:
        return str(self)


def make_deck() -> List[Card]:
    deck = [Card(n, c) for c in COLORS for n in NUMBERS]
    random.shuffle(deck)
    return deck


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_combo(cards: List[Card]) -> Tuple[bool, int, str]:
    """Return (is_valid, score, description). Expects exactly 3 cards."""
    if len(cards) != 3:
        return False, 0, ""

    nums = sorted(c.number for c in cards)
    cols = {c.color for c in cards}

    is_run = (nums[1] - nums[0] == 1) and (nums[2] - nums[1] == 1)
    is_set = nums[0] == nums[1] == nums[2]
    is_same_col = len(cols) == 1

    if is_run and is_same_col:
        pts = 100
        col = next(iter(cols))
        return True, pts, f"Run · same colour ({col}) [{nums[0]}-{nums[1]}-{nums[2]}] → {pts}pts"

    if is_run and not is_same_col:
        pts = 10 * nums[0]
        return True, pts, f"Run · mixed colour [{nums[0]}-{nums[1]}-{nums[2]}] → {pts}pts"

    if is_set and len(cols) == 3:
        pts = 10 + 10 * nums[0]
        return True, pts, f"Set · all colours [{nums[0]}×3] → {pts}pts"

    return False, 0, ""


def completing_cards(pair: Tuple[Card, Card]) -> List[Tuple[Card, int, str]]:
    """All cards that would form a valid combo with *pair*."""
    a, b = pair
    result = []
    for c in COLORS:
        for n in NUMBERS:
            cand = Card(n, c)
            if cand == a or cand == b:
                continue
            ok, pts, desc = score_combo([a, b, cand])
            if ok:
                result.append((cand, pts, desc))
    return result


# ── Game state ────────────────────────────────────────────────────────────────

HAND_SIZE = 5
ANSWER_SIZE = 3


class GameState:
    """
    hand        – list of HAND_SIZE slots (Card | None)
    answer_area – up to 3 cards selected for the current combo attempt
    deck        – cards not yet drawn
    discarded   – permanently removed cards (don't return to deck)
    score       – accumulated points
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.deck: List[Card] = make_deck()
        self.hand: List[Optional[Card]] = [None] * HAND_SIZE
        self.answer_area: List[Card] = []
        self.discarded: List[Card] = []
        self.score: int = 0
        self.combos_scored: int = 0
        self.game_over: bool = False
        self._fill_hand()

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _fill_hand(self) -> None:
        for i, slot in enumerate(self.hand):
            if slot is None and self.deck:
                self.hand[i] = self.deck.pop(0)

    # ── Player actions ───────────────────────────────────────────────────────

    def move_to_answer(self, card: Card) -> bool:
        """Move a card from hand → answer area. Returns False if impossible."""
        if len(self.answer_area) >= ANSWER_SIZE:
            return False
        try:
            idx = self.hand.index(card)
        except ValueError:
            return False
        self.hand[idx] = None
        self.answer_area.append(card)
        return True

    def return_from_answer(self, card: Card) -> bool:
        """Return a card from answer area → first empty hand slot."""
        if card not in self.answer_area:
            return False
        self.answer_area.remove(card)
        for i, slot in enumerate(self.hand):
            if slot is None:
                self.hand[i] = card
                return True
        self.hand.append(card)   # shouldn't happen in normal play
        return True

    def discard_and_draw(self) -> int:
        """
        Discard all non-None hand cards, draw the same count from the deck.
        Returns number of cards discarded.
        """
        to_discard = [c for c in self.hand if c is not None]
        if not to_discard:
            return 0
        self.discarded.extend(to_discard)
        self.hand = [None] * HAND_SIZE
        self._fill_hand()
        return len(to_discard)

    def submit_answer(self) -> Tuple[bool, int, str]:
        """
        Validate and score the 3-card answer area.
        On success  → cards go to discarded, answer_area cleared.
        On failure  → cards stay in answer_area.
        Returns (success, points, description).
        """
        if len(self.answer_area) != ANSWER_SIZE:
            return False, 0, f"Need exactly {ANSWER_SIZE} cards (have {len(self.answer_area)})"

        valid, pts, desc = score_combo(self.answer_area)
        if valid:
            self.discarded.extend(self.answer_area)
            self.answer_area.clear()
            self.score += pts
            self.combos_scored += 1
            self._check_game_over()
            return True, pts, desc
        return False, 0, "Invalid combination — no points awarded"

    def _check_game_over(self) -> None:
        hand_empty = all(c is None for c in self.hand)
        if hand_empty and not self.deck:
            self.game_over = True

    # ── Derived properties ───────────────────────────────────────────────────

    @property
    def hand_cards(self) -> List[Card]:
        return [c for c in self.hand if c is not None]

    @property
    def deck_remaining(self) -> int:
        return len(self.deck)

    @property
    def total_drawn(self) -> int:
        return 24 - len(self.deck)

    @property
    def can_draw(self) -> bool:
        return bool(self.deck) and any(c is None for c in self.hand)

    @property
    def is_stuck(self) -> bool:
        """No cards in hand, deck empty, and answer area incomplete."""
        return (
            all(c is None for c in self.hand)
            and not self.deck
            and len(self.answer_area) < ANSWER_SIZE
        )
