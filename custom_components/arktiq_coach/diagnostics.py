"""Diagnostics for ArktIQ Coach."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .coordinator import ArktiqCoachConfigEntry

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ArktiqCoachConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with the API key redacted."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "title": entry.title,
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
