"""Why did an entity change? Follow the logbook context chain back to the real cause.

Home Assistant stores the context of every state change: which automation, script or user caused it,
and for an automation what triggered it ("triggered by state of input_select.room"). This follows that
chain up to `depth` steps back, so a light switched by an automation that was triggered by a helper that
was set by another automation that reacted to a presence sensor shows up as exactly that.
"""
import datetime as dt
import re

from .client import parse_time


def _when(t, now):
    if t is None:
        return "at an unknown time"
    t = t.astimezone(now.tzinfo)
    if t.date() == now.date():
        day = ""
    elif t.date() == now.date() - dt.timedelta(days=1):
        day = "yesterday "
    else:
        day = t.strftime("on %Y-%m-%d ")
    return f"{day}at {t:%H:%M}"


def state_word(state):
    return {"on": "on", "off": "off", "playing": "playing", "idle": "idle",
            "unavailable": "unavailable"}.get(state, f"to {state}")


def _change_phrase(state):
    if state in ("on", "off"):
        return f"turned {state}"
    if state in ("unavailable", "unknown"):
        return f"became {state}"
    return f"changed to {state}"


def friendly_name(entity_id, states):
    s = states.get(entity_id) or {}
    return (s.get("attributes") or {}).get("friendly_name") or entity_id


def source_entity(entry):
    """The entity an automation was triggered by: 'state of input_select.room' -> input_select.room."""
    m = re.search(r"state of ([a-z_]+\.[a-z0-9_]+)", entry.get("context_source") or entry.get("source") or "")
    return m.group(1) if m else None


def _is_automation(entry):
    return entry.get("context_event_type") == "automation_triggered" or entry.get("context_domain") == "automation"


def change_before(ha, entity_id, before):
    """The last state change of entity_id up to `before` (looks at the 10 minutes before)."""
    if before is None:
        return None
    rows = [r for r in ha.logbook(entity_id, before - dt.timedelta(minutes=10), before + dt.timedelta(seconds=2))
            if "state" in r and (parse_time(r.get("when")) or before) <= before]
    return rows[-1] if rows else None


def cause(ha, entry, states, depth=2):
    """A clause naming what caused one logbook entry, following triggers back up to `depth` steps."""
    who = entry.get("context_name") or entry.get("context_entity_id_name")
    if _is_automation(entry):
        text = f'the automation "{who}"'
        src = source_entity(entry)
        if src:
            prev = change_before(ha, src, parse_time(entry.get("when"))) if depth > 0 else None
            text += f', triggered by "{friendly_name(src, states)}"'
            if prev and prev.get("state"):
                text += f" ({state_word(prev['state'])})"
                if depth > 1 and _is_automation(prev):
                    text += ", which was set by " + cause(ha, prev, states, depth - 1)
        elif (entry.get("context_message") or entry.get("context_source") or "").startswith(("triggered by time", "time")):
            text += " (time trigger)"
        return text
    if entry.get("context_event_type") == "script_started" or entry.get("context_domain") == "script":
        return f'the script "{who}"'
    if who:
        return str(who)
    if entry.get("context_user_id"):
        return "a user, by hand in Home Assistant"
    if entry.get("state") in ("unavailable", "unknown"):
        return "the device stopped reporting (offline, empty battery or its integration is down)"
    return "nothing in Home Assistant: switched on the device itself or in its own app"


def explain(ha, entity_id, hours=24, now=None, states=None, depth=2):
    """One sentence on the last change of entity_id within `hours`, or None when the logbook has nothing."""
    now = now if now is not None and now.tzinfo else (now or dt.datetime.now()).astimezone()
    states = states if states is not None else ha.states()
    rows = [r for r in ha.logbook(entity_id, now - dt.timedelta(hours=hours)) if "state" in r]
    if not rows:
        return None
    last = rows[-1]
    name = friendly_name(entity_id, states)
    return (f"{name} {_change_phrase(last.get('state'))} {_when(parse_time(last.get('when')), now)}. "
            f"Cause: {cause(ha, last, states, depth)}.")


def find_entities(query, states):
    """Entity ids matching a query: an exact entity id, or every word found in the friendly name."""
    if query in states:
        return [query]
    words = query.lower().split()
    return [eid for eid, s in states.items()
            if all(w in (friendly_name(eid, states) + " " + eid).lower() for w in words)]
