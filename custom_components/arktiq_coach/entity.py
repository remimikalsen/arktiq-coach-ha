"""Base entity for ArktIQ Coach."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BASE_URL, DOMAIN, MANUFACTURER
from .coordinator import ArktiqCoachCoordinator


class ArktiqCoachEntity(CoordinatorEntity[ArktiqCoachCoordinator]):
    """Entity tied to one account's coordinator/device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ArktiqCoachCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"ArktIQ Coach {coordinator.person_name}",
            manufacturer=MANUFACTURER,
            model="Personal coach",
            configuration_url=entry.data.get(CONF_BASE_URL),
        )
