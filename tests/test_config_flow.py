"""Tests for the ArktIQ Coach config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.arktiq_coach.api import ArktiqApiError, ArktiqAuthError
from custom_components.arktiq_coach.const import (
    CONF_BASE_URL,
    CONF_TRACK_BADGES,
    CONF_TRACKED_METRICS,
    DOMAIN,
)

USER_INPUT = {
    CONF_NAME: "Remi",
    CONF_BASE_URL: "https://coach.example.com",
    CONF_API_KEY: "akq_test_key",
}

ENTRY_DATA = {
    CONF_NAME: "Remi",
    CONF_BASE_URL: "https://coach.example.com",
    CONF_API_KEY: "akq_test_key",
}


async def test_user_flow_success(hass: HomeAssistant, mock_api) -> None:
    """A valid key creates an entry titled with the person's name."""
    with patch(
        "custom_components.arktiq_coach.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Remi"
    assert result["data"] == ENTRY_DATA


async def test_user_flow_invalid_auth(hass: HomeAssistant, mock_api) -> None:
    """A rejected key shows the invalid_auth error."""
    mock_api["get_summary"].side_effect = ArktiqAuthError("rejected", status=401)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass: HomeAssistant, mock_api) -> None:
    """A connection problem shows the cannot_connect error."""
    mock_api["get_summary"].side_effect = ArktiqApiError("boom")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_key_aborts(hass: HomeAssistant, mock_api) -> None:
    """Adding the same API key twice aborts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        title="Remi",
        # sha256("akq_test_key")[:16]
        unique_id="48bd9d65b74a8e08",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(hass: HomeAssistant, mock_api) -> None:
    """Reauth swaps in the new key and updates the unique id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        title="Remi",
        unique_id="48bd9d65b74a8e08",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.arktiq_coach.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "akq_new_key"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "akq_new_key"
    assert entry.unique_id != "48bd9d65b74a8e08"


async def test_options_flow(hass: HomeAssistant, mock_api) -> None:
    """Options are stored with the scan interval cast to int."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        title="Remi",
        unique_id="48bd9d65b74a8e08",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.arktiq_coach.async_setup_entry", return_value=True
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_SCAN_INTERVAL: 600.0,
                CONF_TRACKED_METRICS: ["weight_kg"],
                CONF_TRACK_BADGES: False,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_SCAN_INTERVAL: 600,
        CONF_TRACKED_METRICS: ["weight_kg"],
        CONF_TRACK_BADGES: False,
    }
