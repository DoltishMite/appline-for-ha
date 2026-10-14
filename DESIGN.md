# Appline for HA: design notes

For whoever changes this next (the `hedgepig-ha-integration` skill reads this first).

## Decisions (2026-10-14, with the owner)
- **Name** "Appline for HA", domain `appline`, repo `DoltishMite/appline-for-ha` (public: HACS). Installed through HACS by the owner; nothing is
  ever copied to the Home Assistant machine by hand or by an assistant.
- **Scope:** sidebar panels for chosen apps + entities from the apps' data. **Read-only.** HA → apps and actions both ways: not now.
- **Private data is unlocked in HA:** the user enters a sync code or a share code; HA opens the sealed copies itself.
- **Dynamic entities (owner's request):** entities follow the data. Everything is rebuilt from the documents on every change: new
  things get entities, removed things lose them (entity and device registry tidy in `__init__._tidy`, only after a successful update),
  renamed things keep them (keys are the apps' item ids; a task rename reloads the entry once because HA caches entity names).
  This must hold for every app added later, including ones with presets (Clockline: one device per preset, keyed by the preset's id).
- **Minimum HA:** 2025.8 (`OptionsFlowWithReload`, `AddConfigEntryEntitiesCallback`-era platform setup, typed `runtime_data`).
- **Getting past the backend's Origin check:** proposed, **not yet approved or deployed**: the backend lets a request with no `Origin` and
  `X-Appline-Client: ha/<version>` read (`GET /api/sync`, and `/api/live` with room messages and games ignored for it). Browsers can't pass
  for it: a page elsewhere sending that header gets a preflight with its Origin, which is refused. Until it's deployed, setup fails with "refused".

## How it works
```
config entry (code) ──▶ coordinator ── GET /api/sync?id=… (main doc + each shared thing's doc) ──▶ open (hpcrypto) ──▶ parsers ──▶ Parsed
                          ▲   │                                                                                            │
         wss /api/live ───┘   └─ every 1 min: rebuild (time-based states), every 5 min: pull (safety net)          sensor / binary_sensor
```
- `hpcrypto.py`, `parsers/` are pure Python (no HA imports) and tested on any PC: `pytest tests`.
- A personal sync copy also lists the share codes of the things it shares (`<app>_shared_v1`), so the coordinator follows those copies
  too: another person's tick shows here at once, without waiting for one of the owner's devices to merge it.
- Keys: thing `petline.<pet id>.<task id>.status` → unique_id `<entry id>_<thing key>`; device `petline.<pet id>` (via `petline`).

## Adding an app
1. `parsers/<app>.py` with `APP`, `NAME`, `parse`, `share_codes`, `from_shared` (see `parsers/__init__.py`), registered in `PARSERS`.
2. Read the app's `APP.md` and saved keys; port any logic exactly and add a parity test against the app's own code where it computes
   something (as `tests/test_parity.py` does for Petline's `status()`).
3. Translations in `translations/en.json` (custom integrations have no strings.json); an icon in `const.APP_ICONS` for its panel.
4. A row in README's tables and the entity list below; a changelog line; bump `manifest.json` and `const.VERSION`.

## Entities
| App | Device | Thing key | Platform / kind | Translation key |
|---|---|---|---|---|
| Petline | Petline | `petline.todo` | sensor / count | `pets_todo` |
| | each pet | `petline.<pet>.todo` | sensor / count | `pet_todo` |
| | | `petline.<pet>.needs_care` | binary_sensor / problem | `pet_needs_care` |
| | | `petline.<pet>.<task>.status` | sensor / enum (over, late, due, soon, later, done) | `pet_task` (`{task}`) |
| | | `petline.<pet>.<task>.next` | sensor / timestamp | `pet_task_next` (`{task} next due`) |

## Tested
- Here: crypto against the kit's own sealing (Node, `make-vector.mjs`), Petline parsing, and parity with `pets.html` `status()` over five days
  in 37-minute steps (Europe/London). Home Assistant itself doesn't install on Windows, so the HA-facing modules are checked by
  `compileall` + `pyflakes` here and by hassfest / the HACS action on GitHub; the rest is checked in Home Assistant by the owner.

## Changelog
- 0.1.0 (2026-10-14): first version. Petline entities, sidebar panels, live link.
