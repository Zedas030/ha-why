"""Minimal Home Assistant REST client (standard library only)."""
import datetime as dt
import json
import os
import pathlib
import urllib.parse
import urllib.request


def load_dotenv(path=".env"):
    """Read KEY=VALUE lines from a .env file into os.environ (existing variables win)."""
    p = pathlib.Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class HomeAssistant:
    """Talks to the Home Assistant REST API with a long-lived access token."""

    def __init__(self, url=None, token=None, timeout=20):
        self.url = (url or os.environ.get("HA_URL", "")).strip().rstrip("/")
        self.token = (token or os.environ.get("HA_TOKEN", "")).strip()
        self.timeout = timeout
        if not self.url or not self.token:
            raise ValueError("HA_URL and HA_TOKEN must be set (see .env.example)")

    def get(self, path):
        req = urllib.request.Request(self.url + path, headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read() or b"null")

    def states(self):
        """{entity_id: state dict} of every entity."""
        return {s["entity_id"]: s for s in self.get("/api/states") or []}

    def logbook(self, entity_id, start, end=None):
        """Logbook entries of one entity between start and end (aware datetimes)."""
        q = "?entity=" + urllib.parse.quote(entity_id)
        if end:
            q += "&end_time=" + urllib.parse.quote(end.isoformat())
        return self.get("/api/logbook/" + urllib.parse.quote(start.isoformat()) + q) or []


def parse_time(value):
    """ISO timestamp from Home Assistant -> aware datetime, or None."""
    try:
        t = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.astimezone()
