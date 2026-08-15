"""Config flow for the ArktIQ Coach integration."""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ArktiqApiError, ArktiqAuthError, ArktiqCoachClient
from .const import (
    CONF_BASE_URL,
    CONF_TRACK_BADGES,
    CONF_TRACKED_METRICS,
    DEFAULT_BASE_URL,
    DEFAULT_METRICS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    KNOWN_METRICS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


class ArktiqCoachConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle adding one API key (= one person) per entry."""

    VERSION = 1

    async def _async_validate(self, base_url: str, api_key: str) -> str | None:
        """Try the key against /summary; return an error key or None."""
        client = ArktiqCoachClient(
            async_get_clientsession(self.hass), base_url, api_key
        )
        try:
            await client.get_summary()
        except ArktiqAuthError:
            return "invalid_auth"
        except ArktiqApiError as err:
            _LOGGER.debug("Validation failed: %s", err)
            return "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initial step: name, instance URL and API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].rstrip("/")
            error = await self._async_validate(base_url, user_input[CONF_API_KEY])
            if error is None:
                await self.async_set_unique_id(_key_hash(user_input[CONF_API_KEY]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_BASE_URL: base_url,
                        CONF_API_KEY: user_input[CONF_API_KEY],
                    },
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=(user_input or {}).get(CONF_NAME, "")
                ): TextSelector(),
                vol.Required(
                    CONF_BASE_URL,
                    default=(user_input or {}).get(CONF_BASE_URL, DEFAULT_BASE_URL),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The key was revoked; ask for a replacement."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store the replacement key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            error = await self._async_validate(entry.data[CONF_BASE_URL], api_key)
            if error is None:
                new_unique_id = _key_hash(api_key)
                for other in self._async_current_entries():
                    if (
                        other.entry_id != entry.entry_id
                        and other.unique_id == new_unique_id
                    ):
                        return self.async_abort(reason="already_configured")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: api_key},
                    unique_id=new_unique_id,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the name or instance URL without re-adding."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].rstrip("/")
            error = await self._async_validate(base_url, entry.data[CONF_API_KEY])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    title=user_input[CONF_NAME],
                    data_updates={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_BASE_URL: base_url,
                    },
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=entry.data.get(CONF_NAME, entry.title)
                ): TextSelector(),
                vol.Required(
                    CONF_BASE_URL, default=entry.data[CONF_BASE_URL]
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> ArktiqCoachOptionsFlow:
        """Create the options flow."""
        return ArktiqCoachOptionsFlow()


class ArktiqCoachOptionsFlow(OptionsFlow):
    """Options: polling cadence and which extras to track."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        metric_options = [
            SelectOptionDict(value=key, label=label)
            for key, label in KNOWN_METRICS.items()
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=30,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_TRACKED_METRICS,
                    default=list(
                        options.get(CONF_TRACKED_METRICS, DEFAULT_METRICS)
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=metric_options, multiple=True, custom_value=True
                    )
                ),
                vol.Required(
                    CONF_TRACK_BADGES,
                    default=options.get(CONF_TRACK_BADGES, True),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
