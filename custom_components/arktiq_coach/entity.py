"""Base entity for ArktIQ Coach."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_BASE_URL, DOMAIN, MANUFACTURER
from .coordinator import ArktiqCoachCoordinator


class ArktiqCoachEntity(CoordinatorEntity[ArktiqCoachCoordinator]):
    """Entity tied to one account's coordinator/device.

    Entity IDs are suggested explicitly from the stable English keys
    (``<domain>.arktiq_coach_<person>_<key>``) so they never depend on the
    HA server language or the account locale; only friendly names are
    localized. The registry keeps whatever ID an entity was first created
    with, so this is a suggestion for new entities, not a rename.
    """

    _attr_has_entity_name = True
    # Set by platform subclasses ("sensor", "todo", ...) to opt in to
    # explicit entity-ID suggestions.
    _entity_domain: str | None = None

    def __init__(
        self,
        coordinator: ArktiqCoachCoordinator,
        key: str,
        object_id: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        if self._entity_domain:
            suggested = slugify(
                f"arktiq_coach_{coordinator.person_name}_{object_id or key}"
            )
            self.entity_id = async_generate_entity_id(
                f"{self._entity_domain}.{{}}", suggested, hass=coordinator.hass
            )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"ArktIQ Coach {coordinator.person_name}",
            manufacturer=MANUFACTURER,
            model="Personal coach",
            configuration_url=entry.data.get(CONF_BASE_URL),
        )
