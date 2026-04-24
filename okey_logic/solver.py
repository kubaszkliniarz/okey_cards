"""
AI solver for the Okey card game.

Strategy layers (in priority order):
  1. If a valid 3-card combo exists in hand+answer → recommend the highest-scoring one.
     But first compare against the best near-combo EV — if a near-combo is drastically
     better and the deck is still large, flag it.
  2. Near-combo: a pair of cards that need exactly one more card to complete a valid combo.
     Uses hypergeometric probability to calculate P(drawing the needed card).
     EV = P × score.  Compared against "fresh draw" EV estimated by Monte Carlo.
  3. Draw fresh: discard all hand cards and draw from the deck.

Probability model
─────────────────
Drawing k cards without replacement from a deck of N that contains K "good" cards:
  P(≥1 good card drawn) = 1 − C(N−K, k) / C(N, k)   [hypergeometric complement]

When multiple completing cards exist (e.g., any of several can finish the combo):
  K = total count of all completing cards in the remaining deck.

Two-pair strategy
─────────────────
If you have two independent pairs (P1 and P2) each needing a different completer,
keeping both pairs (4 cards) and drawing 1 can be better than keeping just one pair
and drawing 3.  We evaluate this explicitly.
"""

from __future__ import annotations
import random
from itertools import combinations
from math import comb
from typing import List, Dict, Any, Tuple, Optional

from okey_logic.game import Card, COLORS, NUMBERS, score_combo, completing_cards


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
    for trio in combinations(cards, 3):
        ok, pts, desc = score_combo(list(trio))
        if ok and (best is None or pts > best[1]):
            best = (list(trio), pts, desc)
    return best


def _all_combos_in(cards: List[Card]) -> List[Tuple[List[Card], int, str]]:
    results = []
    for trio in combinations(cards, 3):
        ok, pts, desc = score_combo(list(trio))
        if ok:
            results.append((list(trio), pts, desc))
    return sorted(results, key=lambda x: -x[1])


def _monte_carlo_ev(deck: List[Card], n_draw: int, trials: int = 800) -> float:
    """Expected score of the best playable combo from *n_draw* fresh cards."""
    if len(deck) < 3 or n_draw < 3:
        return 0.0
    n_draw = min(n_draw, len(deck))
    total = 0.0
    for _ in range(trials):
        sample = random.sample(deck, n_draw)
        best = _best_combo_in(sample)
        total += best[1] if best else 0
    return total / trials


# ── Near-combo analysis ───────────────────────────────────────────────────────

def _analyse_pairs(
    all_cards: List[Card],
    hand: List[Card],
    deck: List[Card],
) -> List[Dict[str, Any]]:
    """
    For every 2-card subset of all_cards, find completing cards still in the deck,
    compute P and EV if we keep that pair and discard the rest of the hand.
    """
    deck_set = list(deck)  # keep ordering for indexing
    results = []

    for pair in combinations(all_cards, 2):
        pair = list(pair)
        completers = completing_cards(tuple(pair))  # type: ignore[arg-type]
        if not completers:
            continue

        # Count completing cards still in the deck
        compl_in_deck = [c for (c, _, _) in completers if c in deck_set]
        K = len(compl_in_deck)
        if K == 0:
            continue

        # How many hand cards would we draw after keeping this pair?
        hand_kept = [c for c in pair if c in hand]
        n_discard = len(hand) - len(hand_kept)  # hand cards we'd throw away
        n_draw = n_discard  # we redraw the same count

        N = len(deck)
        prob = _hyper_prob(N, K, n_draw) if n_draw > 0 else 0.0

        # Best score achievable with this pair + any one completer
        best_score = max(pts for (_, pts, _) in completers)
        ev = prob * best_score

        best_desc = max(completers, key=lambda x: x[1])

        results.append({
            "pair": pair,
            "need_count": K,
            "need_examples": [str(c) for c, _, _ in completers[:3]],
            "prob": prob,
            "n_draw": n_draw,
            "best_score": best_score,
            "best_desc": best_desc[2],
            "ev": ev,
        })

    return sorted(results, key=lambda x: -x["ev"])


def _analyse_two_pairs(
    hand: List[Card],
    answer_area: List[Card],
    deck: List[Card],
) -> Optional[Dict[str, Any]]:
    """
    Check if keeping two independent pairs (4 cards, draw 1) has higher EV
    than keeping one pair (2 cards, draw 3).
    Only applicable when hand has ≥ 4 cards.
    """
    all_cards = hand + answer_area
    if len(all_cards) < 4:
        return None

    N = len(deck)
    best = None

    for p1, p2 in combinations(combinations(all_cards, 2), 2):
        p1, p2 = list(p1), list(p2)
        # Pairs must be disjoint
        if set(map(id, p1)) & set(map(id, p2)):
            continue

        c1 = completing_cards(tuple(p1))   # type: ignore
        c2 = completing_cards(tuple(p2))   # type: ignore

        k1_cards = [c for c, _, _ in c1 if c in deck]
        k2_cards = [c for c, _, _ in c2 if c in deck]
        if not k1_cards or not k2_cards:
            continue

        # Number of hand cards NOT in either pair
        both_pair = set(id(c) for c in p1 + p2)
        n_discard = sum(1 for c in hand if id(c) not in both_pair)
        n_draw = n_discard

        K_either = len(set(k1_cards) | set(k2_cards))
        prob_either = _hyper_prob(N, K_either, n_draw) if n_draw > 0 else 0.0

        best_score_1 = max((pts for _, pts, _ in c1), default=0)
        best_score_2 = max((pts for _, pts, _ in c2), default=0)
        avg_score = (best_score_1 + best_score_2) / 2
        ev = prob_either * avg_score

        if best is None or ev > best["ev"]:
            best = {
                "pair1": p1,
                "pair2": p2,
                "prob": prob_either,
                "ev": ev,
                "n_draw": n_draw,
            }

    return best


# ── Main solver entry point ───────────────────────────────────────────────────

def solve(
    hand: List[Card],
    answer_area: List[Card],
    deck: List[Card],
) -> Dict[str, Any]:
    """
    Analyse current position and return a structured recommendation.

    Keys in the returned dict:
      immediate_combos   – list of valid combos available right now
      near_combos        – top near-combo opportunities (sorted by EV)
      two_pair           – optional two-pair opportunity
      fresh_ev           – estimated EV of discarding all and drawing fresh
      recommendation     – dict with keys: action, cards/keep/discard, ev, reasoning
    """
    all_cards = hand + answer_area
    N = len(deck)

    # ── 1. Immediate combos ──────────────────────────────────────────────────
    immediate = _all_combos_in(all_cards)

    # ── 2. Near combos ──────────────────────────────────────────────────────
    near = _analyse_pairs(all_cards, hand, deck)

    # ── 3. Two-pair opportunity ──────────────────────────────────────────────
    two_pair = _analyse_two_pairs(hand, answer_area, deck)

    # ── 4. Fresh draw EV ────────────────────────────────────────────────────
    n_fresh = len(hand)  # if we discarded everything in hand
    fresh_ev = _monte_carlo_ev(deck, n_fresh) if N >= 3 else 0.0

    # ── 5. Build recommendation ──────────────────────────────────────────────
    rec = _make_recommendation(
        immediate, near, two_pair, fresh_ev, hand, answer_area, deck
    )

    return {
        "immediate_combos": immediate,
        "near_combos": near[:6],
        "two_pair": two_pair,
        "fresh_ev": fresh_ev,
        "recommendation": rec,
    }


def _make_recommendation(
    immediate: List,
    near: List,
    two_pair: Optional[Dict],
    fresh_ev: float,
    hand: List[Card],
    answer_area: List[Card],
    deck: List[Card],
) -> Dict[str, Any]:
    reasoning: List[str] = []

    best_immediate = immediate[0] if immediate else None
    best_near = near[0] if near else None

    # ── Case A: Immediate combo available ────────────────────────────────────
    if best_immediate:
        cards, score, desc = best_immediate
        reasoning.append(f"Valid combo ready: {desc}")

        # Should we wait instead? Only if near-combo EV is substantially higher
        # AND there is still deck left AND probability is high (≥ 60 %)
        wait_candidate = None
        if best_near and deck:
            nc = best_near
            # Waiting is tempting only if EV > immediate score * 1.3 and prob > 0.55
            if nc["ev"] > score * 1.3 and nc["prob"] > 0.55:
                wait_candidate = nc
                reasoning.append(
                    f"However: keeping {[str(c) for c in nc['pair']]} gives "
                    f"{nc['prob']:.0%} chance of {nc['best_score']}pts "
                    f"(EV {nc['ev']:.0f}). Risky — decide based on remaining deck."
                )

        if wait_candidate and len(deck) >= 6:
            # Suggest waiting — flag it clearly
            nc = wait_candidate
            discard = [c for c in hand if c not in nc["pair"] and c not in answer_area]
            reasoning.append("Deck is large enough — waiting recommended.")
            return {
                "action": "keep_and_draw",
                "keep": nc["pair"],
                "discard": discard,
                "need_examples": nc["need_examples"],
                "prob": nc["prob"],
                "ev": nc["ev"],
                "alt_play_score": score,
                "reasoning": reasoning,
            }

        reasoning.append("Play it now for a certain score.")
        return {
            "action": "play",
            "cards": cards,
            "score": score,
            "desc": desc,
            "reasoning": reasoning,
        }

    # ── Case B: No immediate combo — evaluate near-combos ───────────────────
    if best_near:
        nc = best_near

        # Compare against two-pair EV
        two_pair_ev = two_pair["ev"] if two_pair else 0.0

        # Compare against fresh draw EV
        candidates = [
            ("near_combo", nc["ev"]),
            ("two_pair",   two_pair_ev),
            ("fresh",      fresh_ev),
        ]
        best_strategy = max(candidates, key=lambda x: x[1])

        if best_strategy[0] == "near_combo":
            discard = [c for c in hand if c not in nc["pair"] and c not in answer_area]
            reasoning.append(
                f"Keep {[str(c) for c in nc['pair']]} — "
                f"{nc['prob']:.0%} chance of completing '{nc['best_desc']}'"
            )
            reasoning.append(
                f"EV: {nc['ev']:.0f}pts vs fresh draw: {fresh_ev:.0f}pts"
            )
            if len(nc["need_examples"]) == 1:
                reasoning.append(f"Exactly one completer: {nc['need_examples'][0]}")
            else:
                reasoning.append(
                    f"Any of {nc['need_count']} cards completes it "
                    f"(e.g. {', '.join(nc['need_examples'])})"
                )
            return {
                "action": "keep_and_draw",
                "keep": nc["pair"],
                "discard": discard,
                "need_examples": nc["need_examples"],
                "prob": nc["prob"],
                "ev": nc["ev"],
                "reasoning": reasoning,
            }

        if best_strategy[0] == "two_pair" and two_pair:
            tp = two_pair
            discard = [
                c for c in hand
                if c not in tp["pair1"] and c not in tp["pair2"]
                and c not in answer_area
            ]
            reasoning.append(
                f"Keep TWO pairs: {[str(c) for c in tp['pair1']]} "
                f"and {[str(c) for c in tp['pair2']]}"
            )
            reasoning.append(
                f"{tp['prob']:.0%} chance of completing at least one "
                f"by drawing {tp['n_draw']} card(s). EV: {tp['ev']:.0f}pts"
            )
            return {
                "action": "keep_two_pairs",
                "pair1": tp["pair1"],
                "pair2": tp["pair2"],
                "discard": discard,
                "prob": tp["prob"],
                "ev": tp["ev"],
                "reasoning": reasoning,
            }

    # ── Case C: Draw fresh ───────────────────────────────────────────────────
    best_prob = best_near["prob"] if best_near else 0.0
    if best_near:
        reasoning.append(
            f"Best partial combo probability only {best_prob:.0%} "
            f"(EV {best_near['ev']:.0f}pts)"
        )
    reasoning.append(
        f"Fresh draw EV ({fresh_ev:.0f}pts) is better — discard everything."
    )
    return {
        "action": "draw_fresh",
        "ev": fresh_ev,
        "reasoning": reasoning,
    }
