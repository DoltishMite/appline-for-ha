"""Constants for Appline for HA."""
from __future__ import annotations

import logging

DOMAIN = "appline"
LOGGER = logging.getLogger(__package__)
VERSION = "0.1.0"   # keep in step with manifest.json

BASE = "https://launcher.hedgepig.uk"
SYNC_URL = f"{BASE}/api/sync"
LIVE_URL = "wss://launcher.hedgepig.uk/api/live"
APPS_URL = f"{BASE}/kit/apps.json"
# The backend lets this client read (GET /api/sync, the live link) when it sends no Origin and names itself here.
HEADERS = {"X-Appline-Client": f"ha/{VERSION}"}

CONF_CODE = "code"     # a personal sync code or one shared thing's code (a secret: never log it)
CONF_KIND = "kind"     # "sync" or "together"
CONF_PANELS = "panels" # [{ id, name, path }] apps shown in the sidebar

PANEL_PREFIX = "appline-"
APP_ICONS = {"petline": "mdi:paw", "worldline": "mdi:clock-outline", "weatherline": "mdi:weather-partly-cloudy",
             "pulseline": "mdi:list-status", "gridline": "mdi:flash", "deadline": "mdi:calendar-alert",
             "pingline": "mdi:access-point-network", "tideline": "mdi:waves", "tools": "mdi:apps"}
