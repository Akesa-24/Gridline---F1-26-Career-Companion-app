"""Minimal Supabase (PostgREST) client for the shared event log.

Talks plain HTTPS to the project's REST endpoint, so the only dependency is
`requests`. Works with both the legacy anon JWT and the newer
`sb_publishable_...` keys.
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

TIMEOUT = (4, 8)   # (connect, read) seconds


class BackendError(Exception):
    pass


class SchemaMissing(BackendError):
    pass


def schema_sql() -> str:
    return (Path(__file__).resolve().parent.parent / "assets" / "schema.sql").read_text(encoding="utf-8")


_REF = re.compile(r"^[a-z0-9]{20}$")


def normalise_url(url: str) -> str:
    """Accept the API URL, a dashboard link or a bare project ref."""
    url = url.strip().rstrip("/")
    url = re.sub(r"/rest/v1.*$", "", url)        # pasted the REST endpoint instead of the base URL
    m = re.search(r"supabase\.com/dashboard/project/([a-z0-9]{20})", url)
    if m:
        return f"https://{m.group(1)}.supabase.co"
    if _REF.match(url):
        return f"https://{url}.supabase.co"
    if not url.startswith("http"):
        url = "https://" + url
    return url


def is_secret_key(key: str) -> bool:
    if key.startswith("sb_secret_"):
        return True
    if key.startswith("eyJ") and key.count(".") == 2:
        try:
            import base64
            import json
            part = key.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
            return claims.get("role") == "service_role"
        except Exception:
            return False
    return False


class SupabaseBackend:
    def __init__(self, url: str, key: str):
        self.url = normalise_url(url)
        self.key = key.strip()
        if is_secret_key(self.key):
            raise BackendError("That's the secret / service_role key. Use the anon or publishable key — "
                               "the secret one would give everyone with the invite code full control of your database.")
        self.session = requests.Session()
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        self.session.headers.update(headers)

    def _rest(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _check(self, r: requests.Response) -> None:
        if r.status_code < 300:
            return
        if "text/html" in r.headers.get("Content-Type", ""):
            raise BackendError("That address isn't a Supabase API endpoint. Use the Project URL, "
                               "like https://<project-ref>.supabase.co (Connect button in the dashboard).")
        try:
            body = r.json()
        except ValueError:
            body = {"message": r.text[:200]}
        code = str(body.get("code", ""))
        msg = body.get("message") or body.get("msg") or r.reason
        if code in ("PGRST205", "42P01") or "does not exist" in str(msg) or "schema cache" in str(msg):
            raise SchemaMissing(msg)
        if r.status_code in (401, 403):
            raise BackendError(f"Key rejected by Supabase ({r.status_code}): {msg}")
        raise BackendError(f"Supabase error {r.status_code}: {msg}")

    def _json(self, r: requests.Response):
        try:
            return r.json()
        except ValueError as exc:   # a captive portal or proxy answered instead of Supabase
            raise BackendError("Got an unexpected (non-JSON) answer — check your internet connection") from exc

    def _req(self, method: str, url: str, **kw) -> requests.Response:
        try:
            r = self.session.request(method, url, timeout=TIMEOUT, **kw)
        except requests.RequestException as exc:
            raise BackendError(f"Can't reach Supabase: {exc.__class__.__name__}") from exc
        self._check(r)
        return r

    # --------------------------------------------------------------- api
    def check(self) -> None:
        """Raises SchemaMissing if the tables have not been created yet."""
        self._req("GET", self._rest("gridline_careers"), params={"select": "id", "limit": "1"})
        self._req("GET", self._rest("gridline_events"), params={"select": "seq", "limit": "1"})

    def create_career(self, career_id: str, name: str) -> None:
        self._req("POST", self._rest("gridline_careers"), json={"id": career_id, "name": name},
                  headers={"Prefer": "return=minimal,resolution=ignore-duplicates"})

    def career_exists(self, career_id: str) -> str | None:
        r = self._req("GET", self._rest("gridline_careers"),
                      params={"select": "id,name", "id": f"eq.{career_id}"})
        rows = self._json(r)
        return rows[0]["name"] if rows else None

    def push(self, rows: list[dict]) -> None:
        if not rows:
            return
        self._req("POST", self._rest("gridline_events"), json=rows,
                  params={"on_conflict": "uid"},
                  headers={"Prefer": "return=minimal,resolution=ignore-duplicates"})

    def recent_ids(self, career_id: str, after_seq: int) -> list[dict]:
        """seq + uid only, cheap; used to catch rows that committed out of order."""
        r = self._req("GET", self._rest("gridline_events"), params={
            "select": "seq,uid", "career_id": f"eq.{career_id}", "seq": f"gt.{after_seq}",
            "order": "seq.asc", "limit": "1000",
        })
        return self._json(r)

    def pull_uids(self, career_id: str, uids: list[str]) -> list[dict]:
        r = self._req("GET", self._rest("gridline_events"), params={
            "select": "seq,uid,author,kind,payload,created_at",
            "career_id": f"eq.{career_id}", "uid": f"in.({','.join(uids)})", "order": "seq.asc",
        })
        return self._json(r)

    def pull(self, career_id: str, after_seq: int, limit: int = 500) -> list[dict]:
        r = self._req("GET", self._rest("gridline_events"), params={
            "select": "seq,uid,author,kind,payload,created_at",
            "career_id": f"eq.{career_id}", "seq": f"gt.{after_seq}",
            "order": "seq.asc", "limit": str(limit),
        })
        return self._json(r)
