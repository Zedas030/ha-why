# ha-why

**Why did that light just turn on?** `ha-why` answers that from the Home Assistant logbook, in one sentence,
following the chain of automations back to the real trigger.

```
$ ha-why why living room light
Living room light turned on at 23:12. Cause: the automation "Light follows me", triggered by "Room"
(to Living room), which was set by the automation "Where am I", triggered by "Presence living room" (on).
```

It also writes a **night report**: how often each presence or motion sensor fired at night while you were
in another room (ghost pulses from fans, air purifiers, a TV), and which lights went on and why.

```
$ ha-why night --room-entity input_select.current_room
Night 2026-11-11 00:00 to 06:00
Sensor pulses while you were in another room:
    46x  Presence living room
     7x  Motion hallway
Lights that went on:
     3x  LED strip  (Light follows me)
```

Python standard library only, no dependencies, read-only: it never changes anything in Home Assistant.

## How it works

Every state change in Home Assistant carries a *context*: the automation, script or user that caused it.
For an automation the logbook also stores the trigger ("triggered by state of input_select.room").
`ha-why` reads `/api/logbook` for the entity, takes the last change, and if an automation caused it, looks
up the change of the triggering entity just before, and so on (two steps by default, `--depth` to change).
No context means the device was switched directly or by an app that does not report to Home Assistant.

For the night report, a sensor belongs to a room when the room tracker's state (e.g. `Living room`) is part
of the sensor's friendly name or entity id. Without `--room-entity`, every pulse in the window is counted.

## Install

```bash
pip install git+https://github.com/Zedas030/ha-why.git
```

Or clone the repository and run `python -m ha_why …` from its folder.

## Usage

```bash
ha-why why light.desk_lamp          # by entity id
ha-why why hall light --hours 48    # by words of the friendly name; lists matches if several fit
ha-why night                        # last night, 00:00 to 06:00
ha-why night --window 22-6 --date 2026-11-11 --min-pulses 3 --exclude "zone|grow_tent"
ha-why night --json                 # for scripts and dashboards
```

| Option | Environment variable | Default |
|---|---|---|
| `night --room-entity` | `HA_WHY_ROOM_ENTITY` | none |
| `night --window` | `HA_WHY_NIGHT_WINDOW` | `0-6` |
| `night --min-pulses` | `HA_WHY_MIN_PULSES` | `5` |
| `night --exclude` | `HA_WHY_EXCLUDE` | none |
| path of the .env file | `HA_WHY_ENV` | `.env` in the current folder |

To get the night report every morning, run `ha-why night` from cron or Task Scheduler, or call it from a
Home Assistant `shell_command` and send the output as a notification.

## Secrets

`ha-why` needs two values. Put them in a `.env` file in the folder you run it from (copy `.env.example`),
or set them as environment variables. `.env` is listed in `.gitignore`; never commit it.

| Variable | What it is | Where to get it |
|---|---|---|
| `HA_URL` | Base URL of Home Assistant, e.g. `http://homeassistant.local:8123` | your instance |
| `HA_TOKEN` | Long-lived access token | Home Assistant, your profile, *Security*, *Long-lived access tokens*, *Create token* |

**Changing or rotating the token:** create a new token on the same page, replace the value of `HA_TOKEN`
in `.env`, then delete the old token there. A token gives full API access as your user, so if it ever leaks,
delete it in Home Assistant right away. A dedicated Home Assistant user for tools like this keeps the logbook
readable while you can revoke it independently.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## License

MIT, see [LICENSE](LICENSE).
