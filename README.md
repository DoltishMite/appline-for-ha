# Appline for HA

Brings the apps at [launcher.hedgepig.uk](https://launcher.hedgepig.uk) into Home Assistant:

- **Sensors that follow your apps.** Enter a sync code and the integration makes entities from what's in that setup. Add a pet or a
  task and it appears; remove one and it goes; rename one and it keeps its history. Changes arrive the moment they're saved.
- **Apps in the sidebar.** Pick apps to show in Home Assistant's sidebar (Configure on the integration).

Apps with sensors so far: **Petline**. More are coming.

## Install (HACS)
1. HACS → ⋮ → **Custom repositories** → `https://github.com/DoltishMite/appline-for-ha`, type **Integration** → Add.
2. Find **Appline for HA** in HACS → **Download**, then restart Home Assistant.
3. **Settings → Devices & services → Add integration → Appline for HA**, and enter a code:
   - a **sync code** (any app → Settings → Sync & Backup) brings in everything in that setup, including pets other people share with you;
   - or one **shared thing's code** (👥 Share) brings in just that one thing.
4. Optional: **Configure** to choose apps for the sidebar. The sidebar apps only load when Home Assistant is opened at its `hedgepig.uk`
   address (they refuse to be embedded anywhere else).

You can add the integration more than once, once per code.

## Petline
For each pet (a device):

| Entity | What it is |
|---|---|
| *Task* (e.g. `sensor.biscuit_feeding`) | `Due now`, `Late`, `Overdue`, `Soon`, `Later` or `Done`, worked out as the app does. Attributes: when it's due, last done and by whom, the meal slot (2 of 2), times or how often. |
| *Task* next due | When it's next due (a timestamp: use it in a time trigger). Treatments and appointments without a time use the app's reminder time. |
| To do now | How many of the pet's tasks need doing now (and which, in `tasks`). |
| Needs care | On while anything needs doing. |

And on the Petline device: **Pets to do now**, the total for all pets.

Example automation: notify when a pet's breakfast is late.
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

## Privacy
Your data is stored on the apps' server **sealed** (encrypted in the browser with a key made from your code), and the server can't read it.
Home Assistant downloads the sealed copy and opens it locally. The code is kept in Home Assistant's own storage on your Home
Assistant machine (`.storage/core.config_entries`), like any integration's settings, so keep your backups safe. The integration only reads.
It never changes anything in your apps.

## Troubleshooting
- *"The apps' server isn't letting Home Assistant in yet"*: the server needs the update that allows this integration to read.
- Sensors go **unavailable** while the apps' server is off. They come back by themselves.
- **Settings → System → Logs**, search "appline". Diagnostics (on the integration's ⋮) contain counts only, never your code or data.
