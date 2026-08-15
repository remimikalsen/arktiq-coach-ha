"""Binary sensor for ArktIQ Coach."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ArktiqCoachConfigEntry
from .entity import ArktiqCoachEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArktiqCoachConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the all-done binary sensor."""
    async_add_entities([ArktiqAllDoneBinarySensor(entry.runtime_data)])


class ArktiqAllDoneBinarySensor(ArktiqCoachEntity, BinarySensorEntity):
    """On when every task today is done (and there was at least one)."""

    _attr_translation_key = "all_done"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "all_done")

    @property
    def is_on(self) -> bool:
        today = self.coordinator.data.today
        total = today.get("totalCount", 0)
        return total > 0 and today.get("doneCount", 0) >= total
