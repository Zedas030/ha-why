"""Command line: `ha-why why <entity>` and `ha-why night`."""
import argparse
import datetime as dt
import json
import os
import sys

from . import __version__
from .client import HomeAssistant, load_dotenv
from .explain import explain, find_entities, friendly_name
from .night import analyse, report


def _ha():
    try:
        return HomeAssistant()
    except ValueError as e:
        sys.exit(f"ha-why: {e}")


def cmd_why(args):
    ha = _ha()
    states = ha.states()
    hits = find_entities(" ".join(args.entity), states)
    if not hits:
        sys.exit("ha-why: no entity matches " + " ".join(args.entity))
    if len(hits) > 1:
        print("Several entities match, pick one:")
        for eid in hits[:20]:
            print(f"  {eid}  ({friendly_name(eid, states)})")
        return 2
    text = explain(ha, hits[0], hours=args.hours, states=states, depth=args.depth)
    print(text or f"The logbook has nothing for {hits[0]} in the last {args.hours} hours.")
    return 0


def cmd_night(args):
    ha = _ha()
    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    result = analyse(ha, day, args.window, room_entity=args.room_entity, exclude=args.exclude)
    if args.json:
        start, end = result["window"]
        print(json.dumps({"start": start.isoformat(), "end": end.isoformat(),
                          "ghosts": [{"name": n, "pulses": c} for n, c in result["ghosts"]],
                          "lights": [{"name": n, "times_on": c, "cause": w} for n, c, w in result["lights"]]},
                         indent=2))
        return 0
    text = report(result, args.min_pulses, tracked=bool(args.room_entity))
    print(text or "Quiet night: no sensor reached the threshold and no light went on.")
    return 0


def main(argv=None):
    load_dotenv(os.environ.get("HA_WHY_ENV", ".env"))
    p = argparse.ArgumentParser(prog="ha-why", description="Explain Home Assistant state changes from the logbook.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("why", help="why did an entity last change?")
    w.add_argument("entity", nargs="+", help="entity id or words of its friendly name")
    w.add_argument("--hours", type=int, default=24, help="how far back to look (24)")
    w.add_argument("--depth", type=int, default=2, help="how many trigger steps to follow back (2)")
    w.set_defaults(func=cmd_why)

    n = sub.add_parser("night", help="ghost pulses and lights of the last night")
    n.add_argument("--window", default=os.environ.get("HA_WHY_NIGHT_WINDOW", "0-6"), help="hours, e.g. 0-6 or 22-6")
    n.add_argument("--date", help="the morning to report on, YYYY-MM-DD (today)")
    n.add_argument("--room-entity", default=os.environ.get("HA_WHY_ROOM_ENTITY") or None,
                   help="entity whose state is the room you are in, e.g. input_select.current_room")
    n.add_argument("--min-pulses", type=int, default=int(os.environ.get("HA_WHY_MIN_PULSES", "5")),
                   help="pulses a sensor needs to be listed (5)")
    n.add_argument("--exclude", default=os.environ.get("HA_WHY_EXCLUDE") or None,
                   help="regex of entity ids/names to ignore")
    n.add_argument("--json", action="store_true", help="machine-readable output")
    n.set_defaults(func=cmd_night)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except OSError as e:
        sys.exit(f"ha-why: cannot reach Home Assistant: {e}")


if __name__ == "__main__":
    sys.exit(main())
