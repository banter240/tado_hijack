# A 100-call day

Tado publishes three daily figures. The help center (27 January 2026) says 100 requests, and 20,000 with Auto-Assist or AI Assist. A later note (26 May 2026) says the maintained figure is 1,000 and that they plan to cut it further. Auto-Assist and AI Assist stay at 20,000.

Hijack does not switch modes when `q=` changes. Auto quota spends a share of whatever is left after the fixed polls. This page is the fixed part, counted for a classic home, and the settings that keep a 100-call day inside that header.

The numbers below use the same reserve as `estimate_daily_reserved_cost()` and the same start-of-day budget as `calculate_remaining_polling_budget()`: `(limit − background − throttle) × auto-quota percent`, then minus the safety reserve. The zone poll costs 1. The economy window is off, so the interval is about `86400 / that budget` seconds. Throttle default is 20. Auto quota default is 80%. Safety reserve default is 2.

## What one poll is

A zone poll is one `GET` of the zone states. Fourteen rooms are still one call. Sensors on those rooms do not add calls.

| Track | Calls | When |
| --- | --- | --- |
| Zone states | 1 | The auto-quota interval. This is the burn. |
| Presence | 1 | Every 12 h by default. 2 per day. |
| Hardware sync | 2 | `GET /zones` and `GET /devices`, every 24 h by default. |
| Capabilities | 1 per classic zone | On the hardware sync, when the copy is older than `capabilities_refresh_interval`. No bulk endpoint. Tado X has no capabilities call. |
| Weekly plan | 1 per zone, or 2 | Only when the reset switch is on and the stored plan is missing or older than `plan_refresh_max_age_s`. The extra call is `activeTimetable` while that id is not cached. |
| Offset GET | 1 per valve with an inside temperature | Only when `offset_poll_interval` is above 0. Default 0. |
| Offset calibration | 1 PUT per linked measuring device | `on_reset` and `threshold`. An hour interval is one PUT per clock slot of that zone. Off reserves nothing. |
| Early start, away, active timetable | 0 on the clock | A GET runs when the value is unknown, or from a button or `manual_poll`. |

`capabilities_total` is `zones × 86400 / interval`, truncated. Fourteen zones at 86400 seconds reserve 14. The same zones at 604800 seconds reserve 2.

## A normal day off the schedule

The schedule itself sends nothing. A change on the radiator or in the Tado app sends nothing either. Tado writes that itself. Hijack sees it on the next zone poll, which is already counted. A call happens when Home Assistant leaves the plan: a warmer room for an hour, a window opened to air, home and away for work. The command queue waits 5 seconds. Rooms that change in that window share one request. On Classic, manual temperatures and offs share one `POST /overlay`. Resumes share one bulk delete. The window resume batch is on by default and holds those resumes for 120 seconds, so one airing of several rooms is still one delete.

With a linked climate the open is local and is not a Tado call. The count below is the cloud path.

| | What happens | Calls |
| --- | --- | --- |
| Morning | Bedroom and bathroom set warmer, a few seconds apart | 1 |
| | Both back on the schedule | 1 |
| | Those two rooms aired together: one off, one resume | 2 |
| | Leave for work, presence set to away | 1 |
| Day | The schedule runs. No one touches a room | 0 |
| Evening | Come home, presence set to home | 1 |
| | Living room and bedroom set warmer for the evening | 1 |
| | Living room aired once | 2 |
| | Both rooms back on the schedule | 1 |
| | **Writes** | **10** |

Airing the bedroom and the bathroom together costs the same two calls as airing one room. Doing it an hour apart is two calls per room. Tado's own geofence is not one of these writes. The 12-hour presence poll notices it. Setting home or away from Home Assistant is the one call in the table.

Ten writes on top of the fixed background. Heating resumes do not add a zone poll. The extra refresh after a resume is only for hot water and air conditioning. The day does not fit if every radiator is written on its own, over and over.

## Offset, the other choice

Calibration is separate from that day. It writes a device offset when a linked thermometer and the valve disagree by at least the spread, default 0.5 °C. Each device is its own `PUT`. The batch does not fold them into the room overlay.

`on_reset` checks once after the quota reset. `threshold` checks when the linked thermometer changes. There is no clock. Rough daily averages from one home, spread 0.5 °C:

| Room | Mode | About per day |
| --- | --- | --- |
| Bedroom | threshold | 19 |
| Living room | threshold | 4 |
| Bathroom | on_reset | 1 |
| Study | on_reset | 1 |

Use `threshold` only on a room that needs it, such as a living room or a bedroom. Leave the others on `on_reset`. The reserve still guesses one write per threshold device, so the extra writes come out of the zone polls.

The plan reserve is not an average. On the day the plans are due it is the full set. On the other days it is 0.

## A 14-zone classic home

This is a counted home: 14 capability zones, 17 devices, 7 of those devices linked for offset calibration, and 16 plan GETs while two zones still have no timetable id. After those two ids are cached the plan line is 14.

Background at the defaults, plan switch off, calibration off, offset poll 0:

| Line | Calls |
| --- | --- |
| Presence | 2 |
| Hardware sync | 2 |
| Capabilities, every 24 h | 14 |
| Plans, offset poll, calibration | 0 |
| **Fixed** | **18** |

Start of a 100-call day: `(100 − 18 − 20) × 0.8 − 2 = 47.6` zone polls. About every **30 minutes**. The day fits. The ten writes of the normal day above are not in that 18. They come out of what is left, and auto quota slows down by about that many polls. The 1800-second status interval is only the fallback for when that budget is gone.

The same home with the plan switch on at age 0, capabilities still daily, and calibration on for the 7 linked devices (`on_reset` or `threshold`, one write each):

| Line | Calls |
| --- | --- |
| Presence, hardware, capabilities | 18 |
| Plans, every reset | 16 |
| Calibration | 7 |
| **Fixed** | **41** |

`(100 − 41 − 20) × 0.8 − 2 = 29.2` zone polls. About every **49 minutes**. Still inside 100, with less room for a button that refetches every zone.

An hourly offset GET does not fit. Seven valves once an hour are `7 × 24 = 168` calls before any other poll. Fifteen valves are 360. Leave `offset_poll_interval` at 0.

A home with 40 classic zones and a daily capabilities refetch plus a daily plan refetch reserves `2 + 2 + 40 + 40 = 84` before calibration. `(100 − 84 − 20)` is already negative. Auto quota then has nothing to burn and the status poll falls back to 1800 seconds until remaining drops under the throttle floor of 20. That day goes through the header.

## Settings for 100

Leave the clocks that are already cheap. Stretch the two that grow with the room count. The fields are in the options flow, General Polling.

| Setting | Default | For a 100-call day |
| --- | --- | --- |
| Status poll | 1800 s, fallback only | Leave it. Auto quota replaces it. |
| Presence | 43200 s | Leave it. |
| Hardware sync | 86400 s | Leave it. |
| `capabilities_refresh_interval` | 86400 s, or the hardware sync when the key is unset | **604800** (7 days). `0` refetches only a zone with no copy. |
| Refresh plans after reset | off | On only if the calendar must track app edits. |
| `plan_refresh_max_age_s` | 0, every reset while the switch is on | **604800** when the switch is on. |
| `offset_poll_interval` | 0 | Leave it at 0. |
| Offset calibration | off | `on_reset` if it has to run. `threshold` is still reserved as one write per device; a noisy sensor can write more, and those writes come out of the burn or the floor of 20. |
| Auto quota | 80% | Leave it. This is the burn. |
| Throttle | 20 | Leave it. That floor is for the app and for automations. |
| Safety reserve | 2 | Leave it. |

On the 14-zone home, capabilities at 7 days, plans left off, calibration on for the 7 devices:

| Line | Calls |
| --- | --- |
| Presence | 2 |
| Hardware sync | 2 |
| Capabilities | 2 |
| Calibration | 7 |
| **Fixed** | **13** |

`(100 − 13 − 20) × 0.8 − 2 = 51.6` zone polls. About every **28 minutes**. The day the plans are also due, add 16: the fixed line is 29 and the zone poll is about every **37 minutes**.

A button or `manual_poll` of type `all`, `schedule`, `timetable`, or `capabilities` is extra. On this home a full plan pass is 14 to 16 calls, and a full capabilities pass is 14. One of those on a tight day lands on the throttle floor.

## Rehearsing it

`simulated_daily_limit` pretends `q=` is lower. Consumed calls still come from the real header, so a real reset refills the pretended budget too. Set it to **100** just after a reset. If the real header has already recorded more than 100 calls that day, the pretended remaining is 0 until the real reset.

The first full poll runs only when the header limit is at least 1000 (`API_QUOTA_STANDARD`). A home whose header is already 100 skips that pass. The first hardware sync still loads capabilities for zones that have no copy. Timetable types and weekly plans stay uncached until the reset switch fires or someone uses the button.

## What does not belong in the 100

- An offset GET interval above 0.
- A plan age of 0 on a large home. That is one or two GETs per zone per day.
- A capabilities interval of 86400 on a home with dozens of zones.
- Full cloud mode on a V3 or Tado X home that already has a HomeKit or Matter climate. Temperature changes are then cloud calls. The header budget is for schedules, presence, hot water, and hardware settings.
