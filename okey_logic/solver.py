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
    capacity: int,
) -> List[Dict[str, Any]]:
    """
    Every hand-subset to keep, with EV of redrawing into all open slots.

    `capacity` is the number of hand slots available (5 − len(stack)).
    n_draw = capacity − keep_size.  Critically this is *not* len(hand) −
    keep_size: when the user has only entered 2 cards but their hand can
    hold 5, refilling will draw 3 — not 0 — fresh cards.

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
            discard = [c for c in hand if c not in keep_list]
            # Cards we'll draw from the deck = open slots after keeping.
            n_draw = max(0, capacity - keep_size)
            info = _ev_keep_and_redraw(keep_list, stack, deck, n_draw)
            entry = {
                "keep": keep_list,
                "discard": discard,
                "n_discard": len(discard),
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

HAND_CAPACITY_DEFAULT = 5  # 5 hand slots in the reference game


def solve(
    hand: List[Card],
    stack: List[Card],
    deck: List[Card],
    capacity: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Analyse current position and return a structured recommendation.

    `capacity` is the number of hand slots available right now
    (HAND_CAPACITY_DEFAULT − len(stack)).  When the user has only partly
    filled their hand (e.g. they've only entered 2 cards out of 5), this
    is what tells the solver "you'll be drawing 3 more cards into those
    empty slots".  Defaults to MAX_VISIBLE − len(stack) which matches the
    real game.
    """
    all_cards = hand + stack
    if capacity is None:
        capacity = HAND_CAPACITY_DEFAULT - len(stack)
    capacity = max(capacity, len(hand))   # never below current hand size

    immediate = _all_combos_in(all_cards)
    near = _analyse_pairs(all_cards, hand, deck)
    keep_sets = _analyse_keep_sets(hand, stack, deck, capacity)

    # Per-card single-discard EV — the action space the game actually
    # supports ("drop one card, draw one card").  Used both to rank discards
    # and to compare against playing a combo right now.
    short_hand = len(hand) < capacity
    single_discards: List[Dict[str, Any]] = []
    if hand and not short_hand:
        single_discards = _rank_single_discards(hand, stack, deck)

    # Per-combo play evaluation — total EV is "points scored now" plus the
    # expected best follow-up from the residual hand once the play refills
    # the empty slots.  This is what lets us prefer Play(R3) over Play(B3)
    # when both score 10 but B3 has more 100-pt completers still in deck.
    play_options: List[Dict[str, Any]] = []
    capacity_after_play = HAND_CAPACITY_DEFAULT  # stack empties after a play
    for combo in immediate:
        play_options.append(
            _eval_play(combo, hand, stack, deck, capacity_after_play)
        )
    play_options.sort(key=lambda p: -p["total_ev"])

    # Group alternatives by *cards-discarded-from-hand* (n_discard, what the
    # user actually clicks).  n_draw lives separately — it's whatever empty
    # slots remain after the discards, including pre-existing empties.
    alt_by_size: Dict[int, Dict[str, Any]] = {}
    for k in keep_sets:
        nd = k["n_discard"]
        if nd not in alt_by_size or k["adjusted_ev"] > alt_by_size[nd]["adjusted_ev"]:
            alt_by_size[nd] = k
    alt_keeps = [alt_by_size[nd] for nd in sorted(alt_by_size.keys())]

    # Fresh-draw baseline = keep-set with empty keep
    fresh_rec = next((k for k in keep_sets if len(k["keep"]) == 0), None)
    fresh_ev = fresh_rec["ev"] if fresh_rec else 0.0

    rec = _make_recommendation(
        immediate, play_options, single_discards, keep_sets,
        near, fresh_ev, hand, stack, deck, capacity, short_hand,
    )

    return {
        "immediate_combos": immediate,
        "play_options": play_options,
        "single_discards": single_discards,
        "near_combos": near[:6],
        "keep_sets": keep_sets[:8],
        "alt_keeps": alt_keeps,
        "fresh_ev": fresh_ev,
        "capacity": capacity,
        "short_hand": short_hand,
        "recommendation": rec,
    }


def _ev_after_single_discard(
    drop: Card,
    hand: List[Card],
    stack: List[Card],
    deck: List[Card],
    lookahead: int = 2,
) -> Dict[str, Any]:
    """
    EV of the atomic move "discard *drop* and draw exactly one card",
    averaged over every possible drawn card.  By default uses 2-step
    lookahead — important because some keeps (e.g. holding 4 same-colour
    cards) gain most of their value over CHAINS of subsequent draws, not
    in a single turn.

    The 1-step term counts: if we land an immediate combo, take its score.
    The 2-step term: if the first draw doesn't complete anything, simulate
    the optimal next single-discard and average over its possible draws.

    Returns ev / prob / best_outcome / hit_count.
    """
    keep = [c for c in hand if c is not drop]
    base = keep + list(stack)
    if not deck:
        b = _best_combo_in(base)
        return {
            "drop": drop, "keep": keep,
            "ev": float(b[1]) if b else 0.0,
            "prob": 1.0 if b else 0.0,
            "best_outcome": b,
            "hit_count": 1 if b else 0,
            "deck_size": 0,
        }

    total = 0.0
    hits = 0
    best_outcome: Optional[Tuple[List[Card], int, str]] = None
    for d in deck:
        new_pool = base + [d]
        b = _best_combo_in(new_pool)
        if b:
            total += b[1]
            hits += 1
            if best_outcome is None or b[1] > best_outcome[1]:
                best_outcome = b
            continue
        # No immediate combo — extend horizon by one more step if asked.
        if lookahead > 1:
            new_hand = keep + [d]
            new_deck = [c for c in deck if c is not d]
            if not new_deck:
                continue
            # Greedy: pick the best second discard from the new hand.
            best_step2 = 0.0
            for y in new_hand:
                sub_keep = [c for c in new_hand if c is not y]
                sub_pool = sub_keep + list(stack)
                sub_total = 0.0
                for d2 in new_deck:
                    b2 = _best_combo_in(sub_pool + [d2])
                    if b2:
                        sub_total += b2[1]
                ev_y = sub_total / len(new_deck)
                if ev_y > best_step2:
                    best_step2 = ev_y
            total += best_step2
    n = len(deck)
    return {
        "drop": drop, "keep": keep,
        "ev": total / n,
        "prob": hits / n,
        "best_outcome": best_outcome,
        "hit_count": hits,
        "deck_size": n,
    }


def _rank_single_discards(
    hand: List[Card],
    stack: List[Card],
    deck: List[Card],
) -> List[Dict[str, Any]]:
    """One entry per hand card, sorted best-to-worst by 1-step EV."""
    if not hand:
        return []
    return sorted(
        (_ev_after_single_discard(c, hand, stack, deck) for c in hand),
        key=lambda r: -r["ev"],
    )


def _eval_play(
    combo: Tuple[List[Card], int, str],
    hand: List[Card],
    stack: List[Card],
    deck: List[Card],
    capacity_after_play: int,
) -> Dict[str, Any]:
    """
    Total EV of playing this combo:  score_now + E[best combo achievable
    from the residual hand once 3 (or fewer at end-of-deck) refill cards
    are drawn].

    This is what makes the solver pick the *right* combo when several share
    the same point value — e.g. when [Y1,Y2,B3] and [Y1,Y2,R3] both score
    10, we want the one that leaves the higher-EV card behind in hand.
    """
    cards, pts, desc = combo
    new_hand = [c for c in hand if c not in cards]
    new_stack = [c for c in stack if c not in cards]
    open_slots = capacity_after_play - len(new_hand)
    n_draw = max(0, min(open_slots, len(deck)))

    if n_draw == 0 or not deck:
        b = _best_combo_in(new_hand + new_stack)
        future = float(b[1]) if b else 0.0
    else:
        space = comb(len(deck), n_draw)
        if space <= EXACT_THRESHOLD:
            total = 0.0
            for sample in combinations(deck, n_draw):
                b = _best_combo_in(new_hand + new_stack + list(sample))
                total += b[1] if b else 0.0
            future = total / space
        else:
            total = 0.0
            for _ in range(MC_TRIALS):
                sample = random.sample(deck, n_draw)
                b = _best_combo_in(new_hand + new_stack + sample)
                total += b[1] if b else 0.0
            future = total / MC_TRIALS

    return {
        "combo": combo,
        "score": pts,
        "desc": desc,
        "future_ev": future,
        "total_ev": pts + future,
        "residual": new_hand,
    }


def _pick_first_to_drop(
    hand: List[Card],
    keep: List[Card],
    discard: List[Card],
    stack: List[Card],
    deck: List[Card],
    capacity: int,
) -> Optional[Card]:
    """
    Of the cards we plan to throw away, which single one should the user
    discard *first*?  Pick the candidate whose true 1-step EV is highest —
    that's the move that maximises this turn's outcome.  If no draw is
    possible the answer is trivially the first item.
    """
    if not discard:
        return None
    if len(discard) == 1:
        return discard[0]
    if not deck:
        return discard[0]

    best: Optional[Card] = None
    best_ev = -1.0
    for c in discard:
        info = _ev_after_single_discard(c, hand, stack, deck)
        if info["ev"] > best_ev:
            best_ev = info["ev"]
            best = c
    return best or discard[0]


def _make_recommendation(
    immediate: List[Tuple[List[Card], int, str]],
    play_options: List[Dict[str, Any]],
    single_discards: List[Dict[str, Any]],
    keep_sets: List[Dict[str, Any]],
    near: List[Dict[str, Any]],
    fresh_ev: float,
    hand: List[Card],
    stack: List[Card],
    deck: List[Card],
    capacity: int,
    short_hand: bool,
) -> Dict[str, Any]:
    """
    Build a single-atomic-action recommendation that matches how the game
    is actually played: at any moment the user either plays a 3-card combo
    or discards exactly ONE card (which triggers exactly one redraw).  The
    longer-term plan ("eventually you'll drop these N cards") is shown as
    context, not as the headline action.
    """
    reasoning: List[str] = []

    # ── 0. Hand not yet full — wait for more cards ───────────────────────────
    if short_hand:
        missing = capacity - len(hand)
        reasoning.append(
            f"Your hand is {len(hand)}/{capacity}; the game will deal "
            f"{missing} more before you face any decision."
        )
        if hand:
            same_col_pair_count = sum(
                1 for a, b in combinations(hand, 2)
                if a.color == b.color and abs(a.number - b.number) <= 2
            )
            if same_col_pair_count:
                reasoning.append(
                    f"You already have {same_col_pair_count} same-colour "
                    f"close pair(s) in hand — strong start, those can target 100-pt runs."
                )
        reasoning.append(
            "Enter the rest using the picker.  No discard is required yet."
        )
        return {
            "action": "draw_more",
            "missing": missing,
            "reasoning": reasoning,
        }

    # Best play (by total EV including residual), best single-discard.
    best_play = play_options[0] if play_options else None
    best_disc = single_discards[0] if single_discards else None

    # keep_sets is sorted by adjusted_ev so [0] is the strategic best.
    actionable = [k for k in keep_sets if k["n_discard"] > 0 or k["n_draw"] > 0]
    best_keep = actionable[0] if actionable else None

    # ── A. Valid combo available — play vs continue, with residual EV ────────
    if best_play:
        cards = best_play["combo"][0]
        score = best_play["score"]
        desc = best_play["desc"]
        residual = best_play["residual"]
        future = best_play["future_ev"]
        play_total = best_play["total_ev"]

        reasoning.append(
            f"Best playable combo: {desc} for +{score} pts."
        )
        if residual:
            reasoning.append(
                f"Leaves {[str(c) for c in residual]} in hand; that residual "
                f"projects {future:.0f} pts on the next move (EV total {play_total:.0f})."
            )
        # Mention the runner-up if it's a tie on score but different residual
        if len(play_options) > 1:
            second = play_options[1]
            if second["score"] == score and second["combo"][0] != cards:
                reasoning.append(
                    f"(Runner-up {second['combo'][2]} would leave "
                    f"{[str(c) for c in second['residual']]}; future EV "
                    f"{second['future_ev']:.0f} → total {second['total_ev']:.0f}.)"
                )

        # Skip the play only if continuing has clearly higher EV.
        continue_ev = best_disc["ev"] if best_disc else 0.0
        if (
            best_disc
            and continue_ev > play_total + 10
            and len(deck) >= 6
        ):
            reasoning.append(
                f"However discarding {best_disc['drop']} (1-step EV "
                f"{continue_ev:.0f}) clearly beats playing now — wait."
            )
            return _build_discard_rec(best_disc, deck, reasoning,
                                       alt_play_score=score)

        reasoning.append("Play it now for the certain score.")
        return {
            "action": "play",
            "cards": cards,
            "score": score,
            "desc": desc,
            "future_ev": future,
            "total_ev": play_total,
            "residual": residual,
            "reasoning": reasoning,
        }

    # ── B. No immediate combo — pick the SINGLE best card to discard ────────
    if best_disc:
        reasoning.append(
            f"No combo playable right now.  Discard {best_disc['drop']} — "
            f"that gives the highest 1-step EV ({best_disc['ev']:.0f})."
        )
        if best_disc["best_outcome"]:
            be_cards, be_score, _ = best_disc["best_outcome"]
            reasoning.append(
                f"Best draw outcome: {[str(c) for c in be_cards]} → {be_score} pts."
            )
        # Show why this beats the alternatives
        if len(single_discards) > 1:
            others = single_discards[1:3]
            descs = ", ".join(
                f"{o['drop']} (EV {o['ev']:.0f})" for o in others
            )
            reasoning.append(f"Next-best alternatives: {descs}.")
        # Surface the long-term plan from keep-set analysis as context only
        if best_keep and best_keep["keep"]:
            reasoning.append(
                f"Long-term target: keep {[str(c) for c in best_keep['keep']]} "
                f"toward {_describe_keep_target(best_keep)}."
            )
        return _build_discard_rec(best_disc, deck, reasoning)

    # ── C. Fallback ──────────────────────────────────────────────────────────
    reasoning.append(
        f"Nothing useful in hand yet — enter the {capacity - len(hand)} "
        f"card(s) you'll draw using the picker."
    )
    return {
        "action": "keep_and_draw",
        "keep": [],
        "discard": list(hand),
        "n_discard": len(hand),
        "n_draw": capacity - 0,
        "first_drop": None,
        "prob": 0.0,
        "ev": fresh_ev,
        "adjusted_ev": fresh_ev,
        "need_cards": [],
        "need_examples": [],
        "best_expected": None,
        "reasoning": reasoning,
    }


def _build_discard_rec(
    disc_info: Dict[str, Any],
    deck: List[Card],
    reasoning: List[str],
    alt_play_score: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build a single-discard recommendation.  This is the canonical "atomic"
    move the game supports: discard one card, draw one.
    """
    drop = disc_info["drop"]
    keep = disc_info["keep"]

    # Show what we'd hope to draw — the cards in the deck that maximise
    # our best combo if drawn next.
    helpful = _helpful_completers(keep, deck)
    need_cards = [c for c, _ in helpful[:6]]

    rec = {
        "action": "discard_one",
        "discard": [drop],
        "drop": drop,
        "keep": keep,
        "ev": disc_info["ev"],
        "prob": disc_info["prob"],
        "best_outcome": disc_info["best_outcome"],
        "hit_count": disc_info["hit_count"],
        "deck_size": disc_info["deck_size"],
        "need_cards": need_cards,
        "need_examples": [str(c) for c in need_cards[:3]],
        "reasoning": reasoning,
    }
    if alt_play_score is not None:
        rec["alt_play_score"] = alt_play_score
    return rec


def _describe_keep_target(keep_info: Dict[str, Any]) -> str:
    """Short text describing what combo a keep-set is aiming at."""
    be = keep_info.get("best_expected")
    if be:
        cards, pts, _ = be
        return f"{[str(c) for c in cards]} ({pts} pts)"
    return "future combo opportunities"


def _build_keep_rec(
    keep_info: Dict[str, Any],
    deck: List[Card],
    reasoning: List[str],
    capacity: int,
    first_drop: Optional[Card] = None,
    alt_play_score: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a keep_and_draw recommendation with need-card info for display."""
    keep_cards = keep_info["keep"]
    need_cards: List[Card] = []

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
        "n_discard": keep_info["n_discard"],
        "n_draw": keep_info["n_draw"],
        "first_drop": first_drop,
        "prob": keep_info["prob"],
        "ev": keep_info["ev"],
        "adjusted_ev": keep_info["adjusted_ev"],
        "best_expected": keep_info["best_expected"],
        "need_cards": need_cards,
        "need_examples": need_examples,
        "reasoning": reasoning,
    }
    if alt_play_score is not None:
        rec["alt_play_score"] = alt_play_score
    return rec
