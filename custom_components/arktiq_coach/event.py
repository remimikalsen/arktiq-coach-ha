"""Event entities for ArktIQ Coach (device triggers for automations)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    EVENT_TYPE_ALL_TASKS_DONE,
    EVENT_TYPE_BADGE_EARNED,
    EVENT_TYPE_STREAK_INCREASED,
    EVENT_TYPE_STREAK_LOST,
    SIGNAL_BADGE_EVENT,
    SIGNAL_COACH_EVENT,
)
from .coordinator import ArktiqCoachConfigEntry, ArktiqCoachCoordinator
from .entity import ArktiqCoachEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArktiqCoachConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the badge and coach event entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ArktiqCoachEventEntity(
                coordinator,
                key="badge",
                event_types=[EVENT_TYPE_BADGE_EARNED],
                signal=SIGNAL_BADGE_EVENT.format(entry.entry_id),
            ),
            ArktiqCoachEventEntity(
                coordinator,
                key="coach",
                event_types=[
                    EVENT_TYPE_ALL_TASKS_DONE,
                    EVENT_TYPE_STREAK_INCREASED,
                    EVENT_TYPE_STREAK_LOST,
                ],
                signal=SIGNAL_COACH_EVENT.format(entry.entry_id),
            ),
        ]
    )


class ArktiqCoachEventEntity(ArktiqCoachEntity, EventEntity):
    """Relays coordinator-detected changes as event entity events."""

    def __init__(
        self,
        coordinator: ArktiqCoachCoordinator,
        key: str,
        event_types: list[str],
        signal: str,
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._attr_event_types = event_types
        self._signal = signal

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._signal, self._handle_event)
        )

    @callback
    def _handle_event(self, event_type: str, data: dict[str, Any]) -> None:
        self._trigger_event(event_type, data)
        self.async_write_ha_state()
