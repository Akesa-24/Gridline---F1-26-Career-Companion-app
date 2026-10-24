"""Mapping telemetry cars onto career drivers, and fingerprinting results."""
from __future__ import annotations

import hashlib
import json

from .models import Member


def _norm(s: str) -> str:
    return "".join(ch for ch in s.casefold() if ch.isalnum())


def names_match(game_name: str, tag: str) -> bool:
    """Lobby names can be truncated with an ellipsis by the game; match on the prefix then."""
    n, t = _norm(game_name), _norm(tag)
    if not n or not t:
        return False
    if n == t:
        return True
    truncated = game_name.rstrip().endswith(("\u2026", "..."))
    return truncated and len(n) >= 3 and t.startswith(n)


def ai_key(driver_id: int) -> str:
    # Format 2025 sends 8-bit driver ids, format 2026 16-bit. All game driver ids fit in
    # 8 bits, so masking makes both PCs agree even if they use different UDP formats.
    return f"ai:{int(driver_id) & 0xFF}"


def assign_driver_keys(result: dict, members: dict[str, Member], local_member_id: str) -> dict:
    """Give every entry a stable `driver_key`.

    AI cars use their game driver id. The local human is always the car at the
    player index. Other humans are matched by gamertag; if names are hidden in
    the lobby and exactly one human and one member are left over, they are
    paired by elimination (the common two-player case).
    """
    entries = result["entries"]
    unmatched_members = {mid: m for mid, m in members.items() if mid != local_member_id}
    unmatched_humans = []
    for e in entries:
        if e["ai"]:
            e["driver_key"] = ai_key(e["driver_id"])
        elif e.get("is_local"):
            e["driver_key"] = f"p:{local_member_id}"
        else:
            unmatched_humans.append(e)

    for e in list(unmatched_humans):
        name = e.get("name", "")
        for mid, m in list(unmatched_members.items()):
            if names_match(name, m.gamertag) or names_match(name, m.display_name):
                e["driver_key"] = f"p:{mid}"
                unmatched_members.pop(mid)
                unmatched_humans.remove(e)
                break

    if len(unmatched_humans) == 1 and len(unmatched_members) == 1:
        unmatched_humans[0]["driver_key"] = f"p:{next(iter(unmatched_members))}"
        unmatched_humans.clear()

    for e in unmatched_humans:
        # include the car index so two unknown humans with hidden names stay separate
        e["driver_key"] = f"h:{_norm(e.get('name', '')) or 'player'}:{e['idx']}"
    return result


def fingerprint(result: dict) -> str:
    """Identity-independent summary used to check two PCs saw the same session.

    Humans are reduced to 'H' because each PC may know the other player under
    a different name; team id, laps and status still pin the order down.
    """
    rows = []
    for e in sorted(result["entries"], key=lambda e: e["position"]):
        rows.append([
            # team_key / masked driver id so PCs on UDP format 2025 and 2026 agree
            e["position"], e.get("team_key") or e["team_id"], "H" if not e["ai"] else int(e["driver_id"]) & 0xFF,
            e.get("status", 3), e.get("laps", 0) if result["kind"] == "race" else 0,
        ])
    blob = json.dumps([result["session_type"], result["track_id"], rows], separators=(",", ":"))
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def strip_for_upload(result: dict) -> dict:
    """Drop fields that only matter locally to keep events small."""
    keep = {k: v for k, v in result.items() if k not in ("player_idx",)}
    keep["entries"] = [
        {k: v for k, v in e.items() if k not in ("is_local", "network_id", "idx")}
        | {"idx": e["idx"]}
        for e in result["entries"]
    ]
    return keep
