import datetime as dt
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ha_why import __main__ as cli
from ha_why.explain import cause, explain, find_entities
from ha_why.night import analyse, report, window

TZ = dt.timezone(dt.timedelta(hours=1))


class FakeHA:
    """Logbook per entity; returns the rows inside the asked window."""

    def __init__(self, books, states):
        self.books, self._states = books, states

    def states(self):
        return self._states

    def logbook(self, entity_id, start, end=None):
        out = []
        for r in self.books.get(entity_id, []):
            t = dt.datetime.fromisoformat(r["when"])
            if t >= start and (end is None or t <= end):
                out.append(r)
        return out


def row(t, state=None, **ctx):
    r = {"when": t.isoformat()}
    if state is not None:
        r["state"] = state
    r.update(ctx)
    return r


def names(*pairs, cls=None):
    return {eid: {"entity_id": eid, "attributes": {"friendly_name": n, **({"device_class": cls} if cls else {})}}
            for eid, n in pairs}


class ExplainTest(unittest.TestCase):
    def test_chain_two_steps_back(self):
        t = dt.datetime(2026, 11, 10, 23, 12, tzinfo=TZ)
        states = names(("light.living_room", "Living room light"), ("input_select.room", "Room"),
                       ("binary_sensor.presence_living", "Presence living room"))
        books = {
            "light.living_room": [row(t, "on", context_event_type="automation_triggered",
                                      context_name="Light follows me",
                                      context_source="state of input_select.room")],
            "input_select.room": [row(t - dt.timedelta(seconds=3), "Living room", context_domain="automation",
                                      context_name="Where am I",
                                      context_source="state of binary_sensor.presence_living")],
            "binary_sensor.presence_living": [row(t - dt.timedelta(seconds=5), "on")],
        }
        text = explain(FakeHA(books, states), "light.living_room", now=t + dt.timedelta(minutes=5), states=states)
        self.assertEqual(text, 'Living room light turned on at 23:12. Cause: the automation "Light follows me", '
                               'triggered by "Room" (to Living room), which was set by the automation "Where am I", '
                               'triggered by "Presence living room" (on).')

    def test_no_context(self):
        self.assertIn("on the device itself", cause(FakeHA({}, {}), {"state": "on"}, {}))

    def test_user_and_script(self):
        ha = FakeHA({}, {})
        self.assertEqual(cause(ha, {"context_user_id": "abc"}, {}), "a user, by hand in Home Assistant")
        self.assertEqual(cause(ha, {"context_domain": "script", "context_name": "Bedtime"}, {}), 'the script "Bedtime"')

    def test_time_trigger(self):
        e = {"context_domain": "automation", "context_name": "Sunset", "context_source": "time"}
        self.assertEqual(cause(FakeHA({}, {}), e, {}), 'the automation "Sunset" (time trigger)')

    def test_nothing_in_logbook(self):
        self.assertIsNone(explain(FakeHA({}, {}), "light.x", states={}))

    def test_find_entities(self):
        states = names(("light.desk", "Desk lamp"), ("light.hall", "Hall light"))
        self.assertEqual(find_entities("light.desk", states), ["light.desk"])
        self.assertEqual(find_entities("hall", states), ["light.hall"])
        self.assertEqual(sorted(find_entities("light", states)), ["light.desk", "light.hall"])


class NightTest(unittest.TestCase):
    def setUp(self):
        self.day = dt.date(2026, 11, 11)
        self.start, _ = window(self.day, "0-6")
        s = self.start
        self.states = {
            **names(("binary_sensor.presence_living", "Presence living room"), cls="occupancy"),
            **names(("binary_sensor.motion_bedroom", "Motion bedroom"), cls="motion"),
            **names(("light.led", "LED strip")),
            **names(("input_select.room", "Room")),
        }
        self.books = {
            "input_select.room": [row(s - dt.timedelta(hours=1), "Bedroom")],
            "binary_sensor.presence_living": [row(s + dt.timedelta(minutes=m), "on") for m in range(10, 70, 10)],
            "binary_sensor.motion_bedroom": [row(s + dt.timedelta(minutes=m), "on") for m in range(5, 60, 5)],
            "light.led": [row(s + dt.timedelta(hours=2), "on"),
                          row(s + dt.timedelta(hours=2), context_name="Light follows me")],
        }

    def test_room_tracker_drops_own_room(self):
        r = analyse(FakeHA(self.books, self.states), self.day, states=self.states, room_entity="input_select.room")
        self.assertEqual(r["ghosts"], [("Presence living room", 6)])
        self.assertEqual(r["lights"], [("LED strip", 1, "Light follows me")])
        text = report(r, min_pulses=5, tracked=True)
        self.assertIn("6x  Presence living room", text)
        self.assertIn("LED strip  (Light follows me)", text)

    def test_without_tracker_counts_all(self):
        r = analyse(FakeHA(self.books, self.states), self.day, states=self.states)
        self.assertEqual(r["ghosts"], [("Motion bedroom", 11), ("Presence living room", 6)])

    def test_exclude_and_quiet(self):
        r = analyse(FakeHA(self.books, self.states), self.day, states=self.states,
                    exclude=r"presence|motion|led")
        self.assertEqual(report(r), "")

    def test_window_over_midnight(self):
        start, end = window(self.day, "22-6")
        self.assertEqual((start.day, start.hour, end.day, end.hour), (10, 22, 11, 6))


class CliTest(unittest.TestCase):
    def test_why_ambiguous_lists_matches(self):
        ha = FakeHA({}, names(("light.desk", "Desk lamp"), ("light.hall", "Hall light")))
        out = io.StringIO()
        with mock.patch.object(cli, "_ha", lambda: ha), redirect_stdout(out):
            code = cli.main(["why", "light"])
        self.assertEqual(code, 2)
        self.assertIn("light.desk", out.getvalue())

    def test_missing_config(self):
        with mock.patch.dict(os.environ, {"HA_URL": "", "HA_TOKEN": "", "HA_WHY_ENV": "does-not-exist"}):
            with self.assertRaises(SystemExit):
                cli.main(["why", "light.x"])


if __name__ == "__main__":
    unittest.main()
