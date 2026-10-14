# Appline for HA: design notes

For whoever changes this next: read it first.

## Decisions (2026-10-14, with the owner)
- **Name** "Appline for HA", domain `appline`, repo `DoltishMite/appline-for-ha` (public: HACS). Installed through HACS by the owner; nothing is
  ever copied to the Home Assistant machine by hand or by an assistant.
- **A household, each person choosing what's sent.** Nobody hands HA their sync code. In the apps (the launcher's Settings → Sync & Backup →
  **Integrations** → 🏠 Home Assistant; the kit's `tools/halink.js`) a person connects, gets an **HA link code**, and ticks what goes, per app
  and per item. "Include new …" ticks a new item of their own when first seen; shared things always start unticked. Only ticked items are in
  their **link copy**. In HA: one entry per household, people added with their link codes (Configure → Add a person).
- **Shared things:** anyone in a share can tick it; the others see "🏠 In Home Assistant via <name>" in its share dialog (the thing's `_ha`
  field, which travels with the share). In HA a shared thing is keyed by its shared copy's id (the same for everyone), so it shows **once**,
  with `shared_with`; things only one person has show with `owner` (and their name in the device when two pets share a name).
- **Two-way:** a ✓ done button per task, and a pet's calendar takes new events as appointments. A change to a shared thing is saved in its
  shared copy (everyone's apps merge it, three ways, as they do now); a change to someone's own thing in their link copy with `by: 'ha'` (their
  apps merge it back the same way: `halink.js` `takeBack`). Ticks record the HA user's name ("Home Assistant" for automations).
- **Dynamic entities (owner's request):** entities follow the data. Everything is rebuilt from the documents on every change: new
  things get entities, removed things lose them (entity and device registry tidy in `__init__._tidy`, only after a successful update),
  renamed things keep them (keys are the apps' item ids; a task rename reloads the entry once because HA caches entity names).
  This must hold for every app added later, including ones with presets (Clockline: one device per preset, keyed by the preset's id).
- **Minimum HA:** 2025.8 (`OptionsFlowWithReload`, `AddConfigEntryEntitiesCallback`-era platform setup, typed `runtime_data`).
- **The backend's Origin check:** the backend must let a request with no `Origin` and `X-Appline-Client: ha/<version>` read (`GET /api/sync`),
  save over an **existing** copy (`PUT` with a base version; never start one or delete one) and watch (`/api/live`, room messages and games
  ignored). Browsers can't pass for it: a page elsewhere sending that header gets a preflight with its Origin, which is refused. Live since
  2026-10-14 (`site/_scripts/apply-ha-backend.js`; tests `site/backend/test/test-ha-client.mjs`).

## How it works
```
household entry (people's link codes) ──▶ coordinator ── GET /api/sync (each link copy + each shared copy they name) ──▶ open ──▶ parsers ──▶ Parsed
                     ▲   │   ▲                                                                                                             │
     wss /api/live ──┘   │   └── PUT (a button, a calendar event: the thing changed in its own copy, again after a 409)       sensor / binary_sensor /
                         └── every 1 min: rebuild (time-based states), every 5 min: pull (safety net)                        calendar / button
```
- `hpcrypto.py`, `parsers/` are pure Python (no HA imports) and tested on any PC: `pytest tests`.
- A link copy has the shape of a sync copy (`{ format: 1, link: 1, name, by, apps: { <app>: { t, data: { <key>: <string> } } } }`) with the
  ticked items only, and `<app>_shared_v1` holding the ticked shared things' share codes.
- Keys: a person is `<10 hex of their link id>`; an own pet `petline.<person>.<pet id>`, a shared one `petline.shared.<12 hex of its copy id>`;
  things under them (`….<task id>.status` …); unique_id `<entry id>_<thing key>`. `parse()` (one copy, keys `petline.<pet id>`) remains for
  a single copy and the tests.

## Adding an app
1. `parsers/<app>.py` with `APP`, `NAME`, `LIST_KEY`, `parse`, `parse_people`, `share_codes`, `from_shared`, and the change hooks it supports
   (`press`, `create_event`; see `parsers/__init__.py`, `parsers/petline.py`), registered in `PARSERS`.
2. In the apps: an entry in `halink.js` `ADAPTERS` (its list key, what else HA needs, how an item is labelled). Bump `HPHA`'s `SRC` in kit.js.
3. Read the app's `APP.md` and saved keys; port any logic exactly and add a parity test against the app's own code where it computes
   something (as `tests/test_parity.py` does for Petline's `status()`).
4. Translations in `translations/en.json` (custom integrations have no strings.json); an icon in `const.APP_ICONS` for its panel.
5. A row in README's tables and the entity list below; a changelog line; bump `manifest.json` and `const.VERSION`.

## Entities
| App | Device | Thing key | Platform / kind | Translation key |
|---|---|---|---|---|
| Petline | Petline | `petline.todo` | sensor / count | `pets_todo` |
| | | `petline.calendar` | calendar: every pet (ticks from the log, feeds/walks at their times, treatments all day every N days, appointments) | `pets_calendar` |
| | | `petline.<person>.calendar` | calendar: their own pets and the shared ones they send (on when the household has 2+) | `person_calendar` (`{person}`) |
| | each pet | `….todo` | sensor / count | `pet_todo` |
| | | `….needs_care` | binary_sensor / problem | `pet_needs_care` |
| | | `….<task>.status` | sensor / enum (over, late, due, soon, later, done) | `pet_task` (`{task}`) |
| | | `….<task>.next` | sensor / timestamp | `pet_task_next` (`{task} next due`) |
| | | `….<task>.done` | button: tick it off | `pet_task_done` (`{task} done`) |
| | | `….calendar` | calendar (disabled at first); new events → appointments | `pet_calendar` |

## More apps (0.3.0)
Same pattern as Petline: `parsers/<app>.py` (shared household logic in `parsers/common.py`: whose, shared once, where a change goes),
the app's own rules ported and parity-tested against its page (`tests/js/app-fns.mjs` copies named functions out of a page and runs them
with a fixed clock; `tests/test_apps.py`), and an entry in the kit's `halink.js` ADAPTERS (an app can have several lists: Dayline's people
and events).
| App | Ported from | Entities |
|---|---|---|
| Countline (`countline`) | countdown.html `nextDate`, `over`, rollRepeats | `countline.….days` (duration, days), `.at` (timestamp), `countline.calendar` |
| Dayline (`birthline`) | `onYear`, `next`, `starts` | `birthline.….days`, `birthline.calendar` (yearly dates + events) |
| Renewline (`deadline`) | renewals.html `status`, `daysLeft` | `deadline.….days` (+ status), `deadline.expired`, `.due`, `.attention`, `.calendar` |
| Listline (`listline`) | lists.html add box, checkbox (repeat `last`), `key()` | `listline.….todo` (to-do list, two-way), `.left` |
| Carline (`carline`) | car.html `dueState`, `addMonths`, `doneDialog` defaults (renew) | device per car: `….<due>.days`, `.renew` (button), `.odo`, `.attention`; `carline.calendar`. Fuelline/Chargeline odometers aren't sent |
| Binline (`binline`) | bins.html `collections`, the Put-out-tonight banner | `binline.next`, `binline.<signature>.next` per bin (the same bin in two people's Binline, by name + date + how often, is one), `binline.put_out`, `binline.out` (button: adds to each person's `binline_out_v1` log, a halink.js *log*), `binline.calendar` (+ ✓ when out) |
| Homeline (`homeline`) | home.html `nextOf`, `stateOf`, Done, Later | device per home: `….<job>.days`, `.done`, `.later`, `.overdue`, `.soon`, `.attention`; `homeline.calendar` |
| Plantline (`plantline`) | plants.html `season`, `stretch`, `nextWater`, `nextFeed`, `nextEvery`, `logIt` | device per plant: `.water`, `.feed`, `.repot`, `.prune`, `.water.done`, `.feed.done`, `.snooze`; `plantline.today`, `.calendar` |
| Cookline (`cookline`) | kitchen.html `dayItems` | `cookline.timers`, `.timer_next`, `.timer_done`, `.today`, `.calendar` (meals) |
Next batches (agreed scope "minus ones where it makes zero sense"): Carline, Medline, Homeline, Plantline, Binline, Rotaline, Habitline,
Clockline alarms and timers; then Pantryline, Leaveline, Budgetline, Meterline, Studyline, Packline, Readline, Mileline; then the live-data
apps (Pingline, Statusline, Powerline, Fuelline, Tideline, Breathline, Riverline, Departline, Auroraline, Solarline…). Left out (nothing to
sense): the launcher, Netline, Byteline, Meetline, Convertline, Speedline, Downloadline, Loanline, Paceline, Colourline, Randomline,
Gameline, Wordline, Scanline, Sleepline, Noteline, Scoreline.

## Tested
- Here: crypto against the kit's own sealing (Node, `tests/js/make-vector.mjs`), Petline parsing, households (owners, a shared pet once,
  per-person calendars, the changes), parity with `pets.html` `status()` over five days in 37-minute steps (Europe/London), and a link copy
  made by the real `halink.js` (`site/backend/test/test-halink.mjs`) opened and parsed here. Home Assistant itself doesn't install on
  Windows, so the HA-facing modules are checked by `pyflakes` here and by hassfest / the HACS action on GitHub; the rest is checked in Home
  Assistant by the owner.

## Changelog
- 0.5.1 (2026-10-15): Configure saves (Who's who, sidebar apps, calendars) apply without a reload, so entities no longer blink unavailable; only adding or removing a person reloads. A server that can't be reached for up to 30 minutes keeps the last copies (worked out afresh each minute) instead of making everything unavailable.
- 0.5.0 (2026-10-14): Homeline, Plantline, Cookline; Carline Details; Binline They're out (+ calendar ✓), the same bins shown once across a household.
- 0.4.0 (2026-10-14): Carline (due dates, renewed buttons, mileage) and Binline (collections, put out tonight).
- 0.3.0 (2026-10-14): Countline, Dayline, Renewline and Listline (to-do lists, two-way).
- 0.2.3 (2026-10-14): panels open with ?hp=ha (the apps hide what a panel can't do), Scanline and Gameline left out of Sidebar apps; Configure → Who's who links app names to Home Assistant people (done_by_person; HA ticks saved under the linked name).
- 0.2.2 (2026-10-14): Appline (the launcher) in the sidebar opens the launcher (it pointed at /tools/, a blank page).
- 0.2.1 (2026-10-14): an app unticked in Sidebar apps leaves the sidebar (it stayed until a restart).
- 0.2.0 (2026-10-14): households: people with their own HA link codes (chosen thing by thing in the apps), shared things once, ✓ done buttons,
  appointments from a pet's calendar, per-person calendars.
- 0.1.0 (2026-10-14, not released): Petline entities and calendars from a sync code, sidebar panels, live link.
