"""
AI solver for the Okey card game (open-sourced game clone).

Aim: maximise total points per session.  The highest-paying rewards kick in
above 400 pts across the whole game, so we favour strategies that have high
expected value — even if they mean redrawing instead of cashing in a small
combo now.

Strategy space
──────────────
At each decision point the user can:
  • Play a valid 3-card combo (certain score, end of round).
  • Keep any subset of their hand, discard the rest, redraw the same count.
    Subset size can be 0 (discard everything → fresh draw) up to
    len(hand) − 1 (keep all but one, e.g. discard a single bad card).
  • Stack cards (cards already committed on the answer stack) always stay.

We evaluate every keep-subset for expected value and pick the best, with
"play now" as a baseline for certain scoring.

Probability model
─────────────────
Hypergeometric for single-card completers.  For general subset-EV we
enumerate all possible draws exactly when the space is small
(C(deck, n_draw) ≤ 5000) and fall back to Monte Carlo sampling otherwise.
"""

from __future__ import annotations
import random
from itertools import combinations
from math import comb
from typing import List, Dict, Any, Tuple, Optional

from okey_logic.game import Card, COLORS, NUMBERS, score_combo, completing_cards


EXACT_THRESHOLD = 5_000      # max combinations enumerated exactly
MC_TRIALS = 500              # Monte Carlo trials when enumeration too big


# ── Deck-conservation penalty ────────────────────────────────────────────────
#
# Pure EV is misleading because drawing more cards *always* broadens the
# combinatorial space — so "discard all 5" often has the highest raw EV even
# when "keep 2, draw 3" is strategically the smarter play.
#
# Each card drawn is a permanent deck slot consumed.  A 24-card session
# supports ~4–5 full combos; every unnecessary discard shortens the session.
# We subtract a per-draw penalty proportional to deck scarcity so that, when
# two keep-subsets have comparable EV, the one that spends fewer deck cards
# wins.

def _deck_penalty(deck_size: int) -> float:
    if deck_size <= 0:
        return 0.0
    if deck_size >= 18:
        return 5.0       # deck is deep — conservation matters less
    if deck_size >= 10:
        return 9.0       # middling
    return 14.0          # shallow — burn a card and you lose a whole round


def _adjusted_ev(k: Dict[str, Any], deck_size: int) -> float:
    return k["ev"] - _deck_penalty(deck_size) * k["n_draw"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hyper_prob(N: int, K: int, n: int) -> float:
    """P(drawing at least 1 of K special cards in n draws from deck of N)."""
    if N == 0 or n == 0 or K == 0:
        return 0.0
    n = min(n, N)
    K = min(K, N)
    miss = comb(N - K, n)
    total = comb(N, n)
    return 1.0 - miss / total if total else 0.0


def _best_combo_in(cards: List[Card]) -> Optional[Tuple[List[Card], int, str]]:
    """Highest-scoring valid 3-card combo from *cards*, or None."""
    best = None
    if len(cards) < 3:
        return None
    for trio in combinations(cards, 3):
        ok, pts, desc = score_combo(list(trio))
        if ok and (best is None or pts > best[1]):
            best = (list(trio), pts, desc)
    return best


def _all_combos_in(cards: List[Card]) -> List[Tuple[List[Card], int, str]]:
    results = []
    if len(cards) < 3:
        return results
    for trio in combinations(cards, 3):
        ok, pts, desc = score_combo(list(trio))
        if ok:
            results.append((list(trio), pts, desc))
    return sorted(results, key=lambda x: -x[1])


# ── EV of keep-subset strategy ────────────────────────────────────────────────

def _ev_keep_and_redraw(
    keep: List[Card],
    stack: List[Card],
    deck: List[Card],
    n_draw: int,
) -> Dict[str, Any]:
    """
    Expected value of best combo formed from (keep ∪ stack ∪ n_draw fresh cards).

    Returns dict with:
      ev              – expected score
      prob            – P(any valid combo emerges)
      best_expected   – (cards, score, desc) of the best combo we might land on
    """
    base = list(keep) + list(stack)

    if n_draw == 0:
        best = _best_combo_in(base)
        return {
            "ev": best[1] if best else 0.0,
            "prob": 1.0 if best else 0.0,
            "best_expected": best,
        }

    if not deck or len(deck) < n_draw:
        return {"ev": 0.0, "prob": 0.0, "best_expected": None}

    total = 0.0
    hits = 0
    count = 0
    best_seen: Optional[Tuple[List[Card], int, str]] = None

    space = comb(len(deck), n_draw)
    use_exact = space <= EXACT_THRESHOLD

    if use_exact:
        for sample in combinations(deck, n_draw):
            best = _best_combo_in(base + list(sample))
            if best:
                total += best[1]
                hits += 1
                if best_seen is None or best[1] > best_seen[1]:
                    best_seen = best
            count += 1
    else:
        for _ in range(MC_TRIALS):
            sample = random.sample(deck, n_draw)
            best = _best_combo_in(base + sample)
            if best:
                total += best[1]
                hits += 1
                if best_seen is None or best[1] > best_seen[1]:
                    best_seen = best
            count += 1

    return {
        "ev": total / count if count else 0.0,
        "prob": hits / count if count else 0.0,
        "best_expected": best_seen,
    }


def _analyse_keep_sets(
    hand: List[Card],
    stack: List[Card],
    deck: List[Card],
) -> List[Dict[str, Any]]:
    """
    Every hand-subset to keep, with EV of redrawing the discarded slots.

    Each entry carries two scores:
      ev           – raw expected best-combo score after the draw
      adjusted_ev  – ev minus a per-discard deck-scarcity penalty
                     (used when picking the recommendation; see _deck_penalty)

    The list is sorted by adjusted_ev so the strategic best comes first;
    raw ev is kept for display so the user sees the unvarnished number.
    """
    deck_size = len(deck)
    results = []
    for keep_size in range(0, len(hand) + 1):
        for keep in combinations(hand, keep_size):
            keep_list = list(keep)
            n_draw = len(hand) - keep_size
            info = _ev_keep_and_redraw(keep_list, stack, deck, n_draw)
            discard = [c for c in hand if c not in keep_list]
            entry = {
                "keep": keep_list,
                "discard": discard,
                "n_draw": n_draw,
                "ev": info["ev"],
                "prob": info["prob"],
                "best_expected": info["best_expected"],
            }
            entry["adjusted_ev"] = _adjusted_ev(entry, deck_size)
            results.append(entry)
    return sorted(results, key=lambda x: -x["adjusted_ev"])


# ── Near-combo analysis (for display) ─────────────────────────────────────────

def _analyse_pairs(
    all_cards: List[Card],
    hand: List[Card],
    deck: List[Card],
) -> List[Dict[str, Any]]:
    """Pairs 1 card away from a valid combo — for the NEAR COMBOS display."""
    deck_set = list(deck)
    results = []

    for pair in combinations(all_cards, 2):
        pair_list = list(pair)
        completers = completing_cards(tuple(pair_list))  # type: ignore[arg-type]
        if not completers:
            continue

        compl_in_deck = [c for (c, _, _) in completers if c in deck_set]
        K = len(compl_in_deck)
        if K == 0:
            continue

        hand_kept = [c for c in pair_list if c in hand]
        n_discard = len(hand) - len(hand_kept)

        N = len(deck)
        prob = _hyper_prob(N, K, n_discard) if n_discard > 0 else 0.0

        best_score = max(pts for (_, pts, _) in completers)
        best_desc = max(completers, key=lambda x: x[1])[2]
        ev = prob * best_score

        # Completer cards currently still in deck, sorted by score
        completer_entries = sorted(
            [(c, pts, d) for c, pts, d in completers if c in deck_set],
            key=lambda x: -x[1],
        )
        need_cards = [c for c, _, _ in completer_entries]
        need_examples = [str(c) for c in need_cards[:3]]

        results.append({
            "pair": pair_list,
            "need_count": K,
            "need_examples": need_examples,
            "need_cards": need_cards[:6],
            "prob": prob,
            "n_draw": n_discard,
            "best_score": best_score,
            "best_desc": best_desc,
            "ev": ev,
        })

    return sorted(results, key=lambda x: -x["ev"])


def _helpful_completers(
    base: List[Card],
    deck: List[Card],
) -> List[Tuple[Card, int]]:
    """Deck cards that, added to *base*, create/improve the best combo."""
    current_best = _best_combo_in(base)
    current_score = current_best[1] if current_best else 0
    out = []
    for d in deck:
        new_best = _best_combo_in(base + [d])
        if new_best and new_best[1] > current_score:
            out.append((d, new_best[1]))
    out.sort(key=lambda x: -x[1])
    return out


# ── Main solver entry point ───────────────────────────────────────────────────

def solve(
    hand: List[Card],
    stack: List[Card],
    deck: List[Card],
) -> Dict[str, Any]:
    """Analyse current position and return a structured recommendation."""
    all_cards = hand + stack

    immediate = _all_combos_in(all_cards)
    near = _analyse_pairs(all_cards, hand, deck)
    keep_sets = _analyse_keep_sets(hand, stack, deck)

    # Fresh-draw baseline = keep-set with empty keep
    fresh_rec = next((k for k in keep_sets if len(k["keep"]) == 0), None)
    fresh_ev = fresh_rec["ev"] if fresh_rec else 0.0

    # Alternatives to show the user: the best keep-subset per n_draw size.
    # That way they see what happens if they discard 1, 2, 3, etc. — not
    # just the overall winner.
    alt_by_size: Dict[int, Dict[str, Any]] = {}
    for k in keep_sets:
        nd = k["n_draw"]
        if nd not in alt_by_size or k["adjusted_ev"] > alt_by_size[nd]["adjusted_ev"]:
            alt_by_size[nd] = k
    alt_keeps = [alt_by_size[nd] for nd in sorted(alt_by_size.keys())]

    rec = _make_recommendation(
        immediate, keep_sets, near, fresh_ev, hand, stack, deck
    )

    return {
        "immediate_combos": immediate,
        "near_combos": near[:6],
        "keep_sets": keep_sets[:8],
        "alt_keeps": alt_keeps,
        "fresh_ev": fresh_ev,
        "recommendation": rec,
    }


def _make_recommendation(
    immediate: List[Tuple[List[Card], int, str]],
    keep_sets: List[Dict[str, Any]],
    near: List[Dict[str, Any]],
    fresh_ev: float,
    hand: List[Card],
    stack: List[Card],
    deck: List[Card],
) -> Dict[str, Any]:
    reasoning: List[str] = []

    best_imm = immediate[0] if immediate else None

    # Best actionable keep-set (must actually do something: n_draw > 0).
    # keep_sets is already sorted by adjusted_ev so [0] is the strategic best.
    actionable = [k for k in keep_sets if k["n_draw"] > 0]
    best_keep = actionable[0] if actionable else None

    # The discard-all option, specifically, for comparison framing.
    discard_all = next(
        (k for k in keep_sets if k["n_draw"] == len(hand) and len(hand) > 0),
        None,
    )

    # ── A. Valid combo available ─────────────────────────────────────────────
    if best_imm:
        cards, score, desc = best_imm
        reasoning.append(f"Valid combo ready: {desc}")

        # Only wait if the deck-adjusted EV beats the certain score with room
        # to spare — the penalty already accounts for burned deck slots.
        if (
            best_keep
            and best_keep["adjusted_ev"] > score + 5
            and best_keep["prob"] >= 0.5
            and len(deck) >= 6
        ):
            reasoning.append(
                f"Holding {[str(c) for c in best_keep['keep']]} "
                f"(discard {best_keep['n_draw']}) has deck-adjusted EV "
                f"{best_keep['adjusted_ev']:.0f} vs {score} certain — "
                f"worth the gamble."
            )
            return _build_keep_rec(
                best_keep, deck, reasoning, alt_play_score=score
            )

        reasoning.append("Play it now for a certain score.")
        return {
            "action": "play",
            "cards": cards,
            "score": score,
            "desc": desc,
            "reasoning": reasoning,
        }

    # ── B. No immediate combo — pick best keep-set ───────────────────────────
    if best_keep:
        keep_size = len(best_keep["keep"])
        reasoning.append(
            f"Keep {keep_size} card(s), discard {best_keep['n_draw']}, "
            f"redraw {best_keep['n_draw']}."
        )
        if best_keep["best_expected"]:
            be_cards, be_score, _ = best_keep["best_expected"]
            reasoning.append(
                f"If it lands: {[str(c) for c in be_cards]} → {be_score} pts."
            )
        reasoning.append(
            f"EV {best_keep['ev']:.0f}  "
            f"P(any combo) {best_keep['prob']:.0%}  "
            f"(fresh-draw baseline {fresh_ev:.0f})."
        )

        # If discard-all's raw EV is higher but it lost on deck-adjusted EV,
        # call that out so the user understands the trade-off.
        if (
            discard_all
            and discard_all is not best_keep
            and discard_all["ev"] > best_keep["ev"]
        ):
            reasoning.append(
                f"Discarding all 5 has raw EV {discard_all['ev']:.0f} but "
                f"burns the deck faster — keeping is the higher-yield play."
            )
        return _build_keep_rec(best_keep, deck, reasoning)

    # ── C. Fallback ──────────────────────────────────────────────────────────
    reasoning.append("Nothing worth keeping; discard everything.")
    return {
        "action": "keep_and_draw",
        "keep": [],
        "discard": list(hand),
        "n_draw": len(hand),
        "prob": 0.0,
        "ev": fresh_ev,
        "need_cards": [],
        "need_examples": [],
        "best_expected": None,
        "reasoning": reasoning,
    }


def _build_keep_rec(
    keep_info: Dict[str, Any],
    deck: List[Card],
    reasoning: List[str],
    alt_play_score: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a keep_and_draw recommendation with need-card info for display."""
    keep_cards = keep_info["keep"]
    need_cards: List[Card] = []
    need_examples: List[str] = []

    # For a kept pair, known completers are exact.  Otherwise use helpful_completers.
    if len(keep_cards) == 2 and keep_info["n_draw"] > 0:
        completers = completing_cards(tuple(keep_cards))  # type: ignore[arg-type]
        completer_entries = sorted(
            [(c, pts, d) for c, pts, d in completers if c in deck],
            key=lambda x: -x[1],
        )
        need_cards = [c for c, _, _ in completer_entries[:6]]
    elif keep_cards and keep_info["n_draw"] > 0:
        helpful = _helpful_completers(keep_cards, deck)
        need_cards = [c for c, _ in helpful[:6]]

    need_examples = [str(c) for c in need_cards[:3]]

    rec = {
        "action": "keep_and_draw",
        "keep": keep_cards,
        "discard": keep_info["discard"],
        "n_draw": keep_info["n_draw"],
        "prob": keep_info["prob"],
        "ev": keep_info["ev"],
        "best_expected": keep_info["best_expected"],
        "need_cards": need_cards,
        "need_examples": need_examples,
        "reasoning": reasoning,
    }
    if alt_play_score is not None:
        rec["alt_play_score"] = alt_play_score
    return rec
