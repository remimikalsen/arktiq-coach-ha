"""Diagnostics for ArktIQ Coach."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_NAME
from homeassistant.core import HomeAssistant

from .coordinator import ArktiqCoachConfigEntry

TO_REDACT = {CONF_API_KEY, CONF_NAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ArktiqCoachConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with the API key and person's name redacted."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "title": REDACTED,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "data": {
            "summary": coordinator.data.summary,
            "today": coordinator.data.today,
            "badge_count": len(coordinator.data.badges),
            "metrics": coordinator.data.metrics,
        },
    }
