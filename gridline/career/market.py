"""Contracts, market value and the offers teams make to the human drivers.

Offers are generated deterministically from the career seed, the season, the
round and the member id. Every PC therefore computes exactly the same offers
from the same event log, and only the player's accept/decline has to be synced.
"""
from __future__ import annotations

import math
import random

from ..telemetry.constants import TEAMS_2026
from .models import Contract, Offer

# Offer windows as fractions of the season. The last round always opens one.
WINDOWS = (0.34, 0.67)
OFFER_LIFETIME_ROUNDS = 2
MAX_OFFERS_PER_WINDOW = 3


def market_value(rating: float, championship_pos: int | None = None) -> float:
    """€ millions. ~1M at 50, ~7M at 70, ~20M at 80, ~55M at 90."""
    v = math.exp((rating - 50) / 10.0)
    if championship_pos is not None and championship_pos <= 3:
        v *= 1.0 + (4 - championship_pos) * 0.08
    return round(v, 2)


def team_salary_cap(rank: int) -> float:
    """Most a team will pay a driver, by its current strength rank (0 = best)."""
    return round(42.0 * (0.8 ** rank), 1)


def team_requirement(rank: int) -> float:
    """Rating a team wants before it takes a driver seriously."""
    return 84.0 - rank * 3.2


def offer_windows(n_rounds: int) -> list[int]:
    rounds = sorted({max(1, round(n_rounds * f)) for f in WINDOWS} | {n_rounds})
    return [r for r in rounds if r <= n_rounds]


def initial_contract(member_id: str, team_key: str, rank: int, season: int) -> Contract:
    salary = round(min(team_salary_cap(rank) * 0.35, max(1.0, market_value(62) * 1.2)), 2)
    return Contract(
        member_id=member_id, team_key=team_key, salary=salary,
        start_season=season, end_season=season,
        win_bonus=round(salary * 0.04, 2), podium_bonus=round(salary * 0.015, 2),
        source="initial",
    )


def generate_offers(
    seed: int,
    season: int,
    rnd: int,
    n_rounds: int,
    member_id: str,
    rating: float,
    championship_pos: int | None,
    current: Contract | None,
    has_next_season_deal: bool,
    team_ranks: dict[str, int],
    occupied_by_players: set[str],
) -> list[Offer]:
    rng = random.Random(f"{seed}:{season}:{rnd}:{member_id}")
    value = market_value(rating, championship_pos)
    expiring = current is None or current.end_season <= season
    season_end = rnd >= n_rounds
    offers: list[Offer] = []

    if has_next_season_deal:
        return offers

    candidates = []
    for key in TEAMS_2026:
        if current and key == current.team_key:
            continue
        rank = team_ranks.get(key, 5)
        req = team_requirement(rank)
        # Buy-out offers only come from teams that are a clear step up.
        if not expiring and rank >= team_ranks.get(current.team_key, 5):
            continue
        interest = 1 / (1 + math.exp(-(rating - req) / 3.5))
        if not expiring:
            interest *= 0.45
        if key in occupied_by_players:
            interest *= 0.6   # a seat already held by a human is harder to free up
        candidates.append((interest, key, rank))

    candidates.sort(reverse=True)
    for interest, key, rank in candidates:
        if len(offers) >= MAX_OFFERS_PER_WINDOW:
            break
        if rng.random() > interest * 0.75:
            continue
        cap = team_salary_cap(rank)
        salary = round(min(cap, value * rng.uniform(0.85, 1.2)), 2)
        years = rng.choice((1, 2, 2, 3)) if rank > 2 else rng.choice((2, 3))
        offers.append(Offer(
            id=f"{season}-{rnd}-{member_id[:6]}-{key}",
            member_id=member_id, team_key=key, salary=max(salary, 0.5), years=years,
            win_bonus=round(salary * rng.uniform(0.03, 0.06), 2),
            podium_bonus=round(salary * rng.uniform(0.01, 0.02), 2),
            season=season, made_after_round=rnd,
            expires_after_round=n_rounds if season_end else min(n_rounds, rnd + OFFER_LIFETIME_ROUNDS),
            kind="transfer", interest=round(interest, 2),
        ))

    # The current team always tables a renewal at season end if the deal runs out.
    if current and expiring and season_end:
        rank = team_ranks.get(current.team_key, 5)
        salary = round(min(team_salary_cap(rank), value * rng.uniform(0.95, 1.1)), 2)
        offers.append(Offer(
            id=f"{season}-{rnd}-{member_id[:6]}-{current.team_key}-renew",
            member_id=member_id, team_key=current.team_key, salary=max(salary, 0.5),
            years=rng.choice((1, 2, 3)),
            win_bonus=round(salary * 0.04, 2), podium_bonus=round(salary * 0.015, 2),
            season=season, made_after_round=rnd, expires_after_round=n_rounds,
            kind="renewal", interest=1.0,
        ))
    return offers
