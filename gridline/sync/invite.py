"""Invite codes: everything a second player needs to join, in one pasteable string.

The code carries the Supabase project URL, its public (anon / publishable) key
and the career id. The anon key is designed by Supabase to be public; the
database rules in schema.sql only allow reading and appending events.
"""
from __future__ import annotations

import base64
import json
import zlib

PREFIX = "GRID-"


class InvalidInvite(ValueError):
    pass


def encode(url: str, key: str, career_id: str, name: str) -> str:
    blob = json.dumps({"v": 1, "u": url, "k": key, "c": career_id, "n": name}, separators=(",", ":"))
    packed = base64.urlsafe_b64encode(zlib.compress(blob.encode(), 9)).decode().rstrip("=")
    return PREFIX + packed


def decode(code: str) -> dict:
    code = "".join(code.split())
    if not code.startswith(PREFIX):
        raise InvalidInvite("Invite codes start with GRID-")
    body = code[len(PREFIX):]
    body += "=" * (-len(body) % 4)
    try:
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(body)))
    except Exception as exc:
        raise InvalidInvite("That invite code is damaged — copy it again") from exc
    if not all(k in data for k in ("u", "k", "c")):
        raise InvalidInvite("That invite code is incomplete")
    return {"url": data["u"], "key": data["k"], "career_id": data["c"], "name": data.get("n", "Career")}
