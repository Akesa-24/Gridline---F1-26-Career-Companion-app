"""Driver rating built from telemetry.

The idea is to rate the driver, not the car. Every weekend is scored against
what the car should achieve (the team's AI drivers set that bar), against the
team-mate, and on how clean and repeatable the laps were. The weekly score is
blended into a running rating so one bad race does not wreck a season.
"""
from __future__ import annotations

import statistics

START_RATING = 62.0
BLEND = 0.28          # weight of the newest weekend
MIN_RATING, MAX_RATING = 35.0, 99.0


def robust_stdev(laps: list[int]) -> float | None:
    """Lap time spread with in/out laps, pit laps and incidents removed."""
    if not laps or len(laps) < 4:
        return None
    med = statistics.median(laps)
    clean = [x for x in laps if x <= med * 1.03]
    if len(clean) < 3:
        return None
    return statistics.pstdev(clean)


def _entry(result: dict | None, key: str) -> dict | None:
    if not result:
        return None
    for e in result["entries"]:
        if e.get("driver_key") == key:
            return e
    return None


def _teammate(result: dict, me: dict) -> dict | None:
    for e in result["entries"]:
        if e is not me and e.get("team_key") == me.get("team_key"):
            return e
    return None


def weekend_score(
    key: str,
    race: dict | None,
    quali: dict | None,
    practice: list[dict],
    expected_pos: float,
) -> tuple[float, dict[str, float]] | None:
    """Score one weekend 0-100. Returns None if the driver did not take part."""
    parts: dict[str, float] = {}
    r = _entry(race, key)
    q = _entry(quali, key)
    if r is None and q is None:
        return None

    score = 50.0
    if r is not None:
        dnf = r.get("status") in (4, 5, 6, 7)
        if dnf:
            parts["race"] = -9.0
        else:
            delta = expected_pos - r["position"]
            parts["race"] = max(-14.0, min(16.0, delta * 2.4))
            if r["position"] == 1:
                parts["race"] += 4.0
            elif r["position"] <= 3:
                parts["race"] += 2.0
        sd = robust_stdev(r.get("lap_times_ms") or [])
        if sd is not None:
            # ~250 ms spread is solid; 900 ms+ is scrappy
            parts["consistency"] = max(-5.0, min(5.0, (550 - sd) / 70))
        pens = r.get("penalty_count", 0) + (1 if r.get("penalties_s", 0) >= 5 else 0)
        if pens:
            parts["discipline"] = -2.5 * min(pens, 4)

    if q is not None and q.get("best_lap_ms"):
        parts["qualifying"] = max(-10.0, min(10.0, (expected_pos - q["position"]) * 1.6))
        mate = _teammate(quali, q)
        if mate and mate.get("best_lap_ms"):
            gap_pct = (mate["best_lap_ms"] - q["best_lap_ms"]) / mate["best_lap_ms"] * 100
            parts["teammate"] = max(-8.0, min(8.0, gap_pct * 9))

    if practice:
        gaps = []
        for p in practice:
            e = _entry(p, key)
            best = min((x["best_lap_ms"] for x in p["entries"] if x.get("best_lap_ms")), default=0)
            if e and e.get("best_lap_ms") and best:
                gaps.append((e["best_lap_ms"] - best) / best * 100)
        if gaps:
            parts["practice"] = max(-3.0, min(3.0, 1.5 - min(gaps) * 1.5))

    score += sum(parts.values())
    return max(0.0, min(100.0, score)), parts


def blend(previous: float, score: float) -> float:
    new = previous * (1 - BLEND) + score * BLEND
    return round(max(MIN_RATING, min(MAX_RATING, new)), 1)
