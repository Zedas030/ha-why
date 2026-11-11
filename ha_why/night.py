"""Night report: ghost pulses of presence/motion sensors and lights that went on at night.

Presence sensors (mmWave, PIR) pick up fans, air purifiers or a TV and fire while nobody is in the room.
This counts, for a night window, every "on" pulse of each occupancy/motion/presence sensor. With a room
tracker (an input_select or sensor whose state is the room you are in), only pulses while you were in
another room count: a sensor belongs to a room when the room's name is part of its friendly name or id.
It also lists the lights that went on in that window, with the automation or user behind them.
"""
import datetime as dt
import re

from .client import parse_time

SENSOR_CLASSES = ("occupancy", "motion", "presence")


def window(day, spec="0-6"):
    """'0-6' -> (start, end) as aware datetimes on `day`; '22-6' starts on the evening before."""
    a, _, b = spec.partition("-")
    a, b = int(a or 0), int(b or 6)
    start_day = day - dt.timedelta(days=1) if a > b else day
    start = dt.datetime.combine(start_day, dt.time(a)).astimezone()
    end = dt.datetime.combine(day, dt.time(min(23, b))).astimezone()
    return start, end


def _timeline(rows):
    out = []
    for r in rows:
        t = parse_time(r.get("when"))
        if "state" in r and t:
            out.append((t, (r.get("state") or "").lower()))
    return sorted(out)


def _room_at(timeline, before, t):
    room = before
    for when, state in timeline:
        if when > t:
            break
        room = state
    return room


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _in_room(sensor_text, room):
    room = _norm(room)
    return bool(room) and room in _norm(sensor_text)


def analyse(ha, day=None, spec="0-6", states=None, room_entity=None, exclude=None):
    """{"window": (start, end), "ghosts": [(name, count)], "lights": [(name, count, cause)]}."""
    day = day or dt.date.today()
    start, end = window(day, spec)
    states = states if states is not None else ha.states()
    skip = re.compile(exclude, re.I) if exclude else None

    def wanted(eid):
        text = eid + " " + ((states[eid].get("attributes") or {}).get("friendly_name") or "")
        return not (skip and skip.search(text))

    sensors = [eid for eid, s in states.items() if eid.startswith("binary_sensor.")
               and (s.get("attributes") or {}).get("device_class") in SENSOR_CLASSES and wanted(eid)]
    lights = [eid for eid in states if eid.startswith("light.") and wanted(eid)]

    timeline, before = [], ""
    if room_entity and room_entity in states:
        timeline = _timeline(ha.logbook(room_entity, start - dt.timedelta(hours=12), end))
        before = next((s for t, s in reversed(timeline) if t <= start), "")
        timeline = [(t, s) for t, s in timeline if t > start]

    ghosts, lit = [], []
    for eid in sensors:
        name = (states[eid].get("attributes") or {}).get("friendly_name") or eid
        pulses = [t for t, s in _timeline(ha.logbook(eid, start, end)) if s == "on"]
        if room_entity and room_entity in states:
            pulses = [t for t in pulses if not _in_room(name + " " + eid, _room_at(timeline, before, t))]
        if pulses:
            ghosts.append((name, len(pulses)))
    for eid in lights:
        rows = ha.logbook(eid, start, end)
        on = [r for r in rows if r.get("state") == "on"]
        if on:
            name = (states[eid].get("attributes") or {}).get("friendly_name") or eid
            # the state row often lacks the context; the automation's own logbook line next to it has it
            why = next((r.get("context_name") for r in reversed(rows) if r.get("context_name")), None)
            lit.append((name, len(on), why or "no visible cause"))
    ghosts.sort(key=lambda g: -g[1])
    lit.sort(key=lambda g: -g[1])
    return {"window": (start, end), "ghosts": ghosts, "lights": lit}


def report(result, min_pulses=5, tracked=False):
    """Plain-text report; empty string when nothing reaches `min_pulses` and no light went on."""
    ghosts = [g for g in result["ghosts"] if g[1] >= min_pulses]
    lights = result["lights"]
    if not ghosts and not lights:
        return ""
    start, end = result["window"]
    lines = [f"Night {start:%Y-%m-%d %H:%M} to {end:%H:%M}"]
    if ghosts:
        lines.append("Sensor pulses" + (" while you were in another room:" if tracked else ":"))
        lines += [f"  {count:4d}x  {name}" for name, count in ghosts]
    if lights:
        lines.append("Lights that went on:")
        lines += [f"  {count:4d}x  {name}  ({why})" for name, count, why in lights]
    return "\n".join(lines)
