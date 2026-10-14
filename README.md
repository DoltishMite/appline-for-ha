# Appline for HA

Brings the apps at [launcher.hedgepig.uk](https://launcher.hedgepig.uk) into Home Assistant, for a whole household:

- **Each person chooses what's sent.** In their apps, each person ticks the things that go to Home Assistant, thing by thing. Nothing else leaves their devices.
- **Sensors, calendars and buttons that follow the apps.** Add a pet or a task and it appears; remove one and it goes; rename one and it keeps its history. Changes arrive the moment they're saved.
- **Two-way.** Tick a task off from a dashboard or an automation, or add an appointment from a pet's calendar, and it shows in the app.
- **Apps in the sidebar.** Pick apps to show in Home Assistant's sidebar.

Apps so far: **Petline**, **Countline**, **Dayline**, **Renewline**, **Listline** (as Home Assistant to-do lists), **Carline** and **Binline**. More are coming.

## Install (HACS)
1. HACS → ⋮ → **Custom repositories** → `https://github.com/DoltishMite/appline-for-ha`, type **Integration** → Add.
2. Find **Appline for HA** in HACS → **Download**, then restart Home Assistant.
3. In the apps, each person: **Appline → Settings → Sync & Backup → Integrations → 🏠 Home Assistant → Connect**. They tick what to send
   and get a **link code**. Sync must be on.
4. In Home Assistant: **Settings → Devices & services → Add integration → Appline for HA**. Name the household and enter the first
   person's link code. Add the others with **Configure → Add a person**.
5. Optional: **Configure → Sidebar apps and calendars**. The sidebar apps only load when Home Assistant is opened at its
   `hedgepig.uk` address (they refuse to be embedded anywhere else).

## Who owns what
- Things only one person has show under them (a pet's `owner` attribute). If two people both have a "Biscuit", the devices say whose.
- Things shared between people (👥 Share in the app) show **once**, with `shared_with` listing who sent them. Changes made in Home
  Assistant go straight into the shared copy, so everyone sharing it sees them.
- A shared thing only reaches Home Assistant if someone in the household ticks it. Everyone else in that share sees "🏠 In Home
  Assistant via …" in its share dialog. Unticked shared things, like the kids' own shared stuff, never reach Home Assistant.
- Removing a person removes their things. Shared things stay while someone else still sends them.

## Petline
For each pet (a device):

| Entity | What it is |
|---|---|
| *Task* (e.g. `sensor.biscuit_feeding`) | `Due now`, `Late`, `Overdue`, `Soon`, `Later` or `Done`, worked out as the app does. Attributes: when it's due, last done and by whom, the meal slot (2 of 2), times or how often, owner or who it's shared with. |
| *Task* next due | When it's next due (a timestamp: use it in a time trigger). Treatments and appointments without a time use the app's reminder time. |
| *Task* done (button) | Ticks it off in the app, as its ✓ Done does. The tick shows the Home Assistant user who pressed it ("Home Assistant" for automations). |
| To do now / Needs care | How many of the pet's tasks need doing now (and which), and on while any do. |
| Care (calendar, off at first) | The pet's calendar. **Add an event to it and it becomes an appointment in Petline.** |

On the Petline device: **Pets to do now** (the household total), **Pet care** (everyone's calendar), and **<person>'s pet care**
calendars. Calendars show what was ticked (✓, by whom), each feed and walk at its time (optional: Configure), treatments all day on the
day they're due, and appointments.

Example automation: remind someone when breakfast is late, and let them tick it from the notification's dashboard.
```yaml
triggers:
  - trigger: state
    entity_id: sensor.biscuit_feeding
    to: late
actions:
  - action: notify.notify
    data:
      message: "Biscuit hasn't been fed yet"
```
Tick it from an automation: `action: button.press` with `target: { entity_id: button.biscuit_feeding_done }`.

## Countline, Dayline, Renewline, Listline
| App | Entities |
|---|---|
| Countline | per countdown: *Name* (days until it; a repeating one moves on to its next date as in the app) and *Name* date (a timestamp); a **Countdowns** calendar |
| Dayline | per birthday or yearly date: *Name's birthday* (days until, `turning` the age); a **Calendar** with those and Dayline's own events (repeats, multi-day, times) |
| Renewline | per item: *Name* (days left, `status`: bad / warn / maint / soon / ok / zz), **Expired** and **Due soon** counts, **Needs attention**, a **Renewals** calendar |
| Carline | per car (a device): each due date (*MOT*, *Road tax*, …: days left, `state` over / soon / ok, `miles_left` for a service due at a mileage), a *… renewed* button (moves the date on as the app's Done does), **Mileage**, **Needs attention**; a **Car dates** calendar |
| Binline | **Next collection** (days, which bins), each bin's next collection, **Put out tonight** (from noon the day before until marked out in the app), a **Bin days** calendar; skips, moves, pauses and bank holidays as in the app |
| Listline | each list as a **to-do list** (add, tick, edit, remove, reorder from Home Assistant; due dates on to-do lists), and *Name* left (how many) |

## Privacy
Each person's things are stored on the apps' server **sealed**, encrypted in their browser with a key made from their link code, and
the server can't read them. Home Assistant downloads the sealed copies and opens them locally. The link codes are kept in Home
Assistant's own storage on your Home Assistant machine (`.storage/core.config_entries`), like any integration's settings, so keep your
backups safe. Anyone with a link code can see and change what that person ticked. Disconnecting in the apps deletes that copy.

## Troubleshooting
- *"The apps' server isn't letting Home Assistant in yet"*: the server needs the update that lets this integration read and save.
- Sensors go **unavailable** while the apps' server is off. They come back by themselves.
- **Settings → System → Logs**, search "appline". Diagnostics (on the integration's ⋮) contain counts only, never codes or data.
