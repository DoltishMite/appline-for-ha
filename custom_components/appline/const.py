"""Constants for Appline for HA."""
from __future__ import annotations

import logging

DOMAIN = "appline"
LOGGER = logging.getLogger(__package__)
VERSION = "0.4.0"   # keep in step with manifest.json

BASE = "https://launcher.hedgepig.uk"
SYNC_URL = f"{BASE}/api/sync"
LIVE_URL = "wss://launcher.hedgepig.uk/api/live"
APPS_URL = f"{BASE}/kit/apps.json"
# The backend lets this client read and save existing copies (GET/PUT /api/sync) and watch them (the live link) when it sends
# no Origin and names itself here.
HEADERS = {"X-Appline-Client": f"ha/{VERSION}"}

CONF_CODE = "code"     # a person's HA link code (a secret: never log it)
CONF_PEOPLE = "people" # [{ code }] the household (options)
CONF_HOUSEHOLD = "household"   # its name (the entry's title)
CONF_PANELS = "panels" # [{ id, name, path }] apps shown in the sidebar
CONF_CAL_DAILY = "calendar_daily"   # daily routines (feeds, walks) in the calendars; default on
CONF_NAMES = "names"   # { name used in the apps: person entity }: who's who (Configure → Who's who)

PANEL_PREFIX = "appline-"
APP_ICONS = {"petline": "mdi:paw", "worldline": "mdi:clock-outline", "weatherline": "mdi:weather-partly-cloudy",
             "pulseline": "mdi:list-status", "gridline": "mdi:flash", "deadline": "mdi:calendar-alert",
             "pingline": "mdi:access-point-network", "tideline": "mdi:waves", "tools": "mdi:apps", "countline": "mdi:timer-sand",
             "birthline": "mdi:calendar-star", "listline": "mdi:format-list-checks", "carline": "mdi:car",
             "binline": "mdi:trash-can"}
