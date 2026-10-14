"""Adding entities as things appear in the apps (a new pet, task or preset), for each platform."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .coordinator import ApplineCoordinator


@callback
def follow(coordinator: ApplineCoordinator, platform: str, make: Callable[[ApplineCoordinator, str], Entity],
           add_entities: Callable[[list[Entity]], None]) -> Callable[[], None]:
    """Add an entity for every thing of this platform now and whenever a new one turns up. Returns the unsubscribe."""
    known: set[str] = set()

    @callback
    def check() -> None:
        things = coordinator.data.things if coordinator.data else {}
        known.intersection_update(things)   # a removed thing that comes back gets a new entity
        new = [k for k, t in things.items() if t.platform == platform and k not in known]
        if new:
            known.update(new)
            add_entities([make(coordinator, k) for k in new])

    check()
    return coordinator.async_add_listener(check)
