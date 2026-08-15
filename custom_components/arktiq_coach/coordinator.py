"""Data update coordinator for ArktIQ Coach."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ArktiqApiError,
    ArktiqAuthError,
    ArktiqCoachClient,
    ArktiqRateLimitError,
)
from .const import (
    CONF_TRACK_BADGES,
    CONF_TRACKED_METRICS,
    DEFAULT_METRICS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_ALL_TASKS_DONE,
    EVENT_BADGE_EARNED,
    EVENT_STREAK_CHANGED,
    EVENT_TYPE_ALL_TASKS_DONE,
    EVENT_TYPE_BADGE_EARNED,
    EVENT_TYPE_STREAK_INCREASED,
    EVENT_TYPE_STREAK_LOST,
    SIGNAL_BADGE_EVENT,
    SIGNAL_COACH_EVENT,
    SLOW_CYCLE,
)

_LOGGER = logging.getLogger(__name__)

type ArktiqCoachConfigEntry = ConfigEntry[ArktiqCoachCoordinator]


@dataclass
class ArktiqCoachData:
    """Snapshot of everything the integration polls."""

    summary: dict[str, Any]
    today: dict[str, Any]
    badges: list[dict[str, Any]] = field(default_factory=list)
    # metric key -> latest payload, or None when the key is unknown to the API
    metrics: dict[str, dict[str, Any] | None] = field(default_factory=dict)


def _all_done(today: dict[str, Any]) -> bool:
    total = today.get("totalCount", 0)
    return total > 0 and today.get("doneCount", 0) >= total


def _badge_id(badge: dict[str, Any]) -> tuple[Any, Any]:
    return (badge.get("badgeKey"), badge.get("awardedAt"))


class ArktiqCoachCoordinator(DataUpdateCoordinator[ArktiqCoachData]):
    """Polls the API in two tiers and diffs snapshots into events."""

    config_entry: ArktiqCoachConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ArktiqCoachConfigEntry,
        client: ArktiqCoachClient,
    ) -> None:
        scan_interval = int(
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._cycle = 0
        self._backoff_until: datetime | None = None

    @property
    def person_name(self) -> str:
        return self.config_entry.title

    async def _async_update_data(self) -> ArktiqCoachData:
        if self._backoff_until and dt_util.utcnow() < self._backoff_until:
            raise UpdateFailed("Rate limited, backing off")
        self._backoff_until = None

        options = self.config_entry.options
        track_badges = options.get(CONF_TRACK_BADGES, True)
        tracked_metrics: list[str] = list(
            options.get(CONF_TRACKED_METRICS, DEFAULT_METRICS)
        )
        slow = self._cycle % SLOW_CYCLE == 0

        try:
            today = await self.client.get_today()
            summary = await self.client.get_summary()

            badges = self.data.badges if self.data else []
            if slow and track_badges:
                badges = await self.client.get_badges()

            metrics: dict[str, dict[str, Any] | None] = (
                dict(self.data.metrics) if self.data else {}
            )
            if slow:
                for key in tracked_metrics:
                    try:
                        metrics[key] = await self.client.get_metric_latest(key)
                    except ArktiqApiError as err:
                        if err.status == 404:
                            _LOGGER.debug("Metric %s unknown to the API", key)
                            metrics[key] = None
                        else:
                            raise
                # Drop metrics deselected in the options flow.
                metrics = {k: v for k, v in metrics.items() if k in tracked_metrics}
        except ArktiqAuthError as err:
            raise ConfigEntryAuthFailed(
                f"API key for {self.person_name} was rejected"
            ) from err
        except ArktiqRateLimitError as err:
            backoff = err.retry_after or 300
            self._backoff_until = dt_util.utcnow() + timedelta(seconds=backoff)
            raise UpdateFailed(f"Rate limited, backing off {backoff}s") from err
        except ArktiqApiError as err:
            raise UpdateFailed(str(err)) from err

        self._cycle += 1
        new_data = ArktiqCoachData(
            summary=summary, today=today, badges=badges, metrics=metrics
        )
        self._fire_events(self.data, new_data)
        return new_data

    def _fire_events(
        self, old: ArktiqCoachData | None, new: ArktiqCoachData
    ) -> None:
        """Diff snapshots and fire bus events + event-entity signals.

        Nothing fires on the first refresh after (re)load, so a HA restart
        never replays notifications.
        """
        if old is None:
            return

        base = {"name": self.person_name, "entry_id": self.config_entry.entry_id}
        badge_signal = SIGNAL_BADGE_EVENT.format(self.config_entry.entry_id)
        coach_signal = SIGNAL_COACH_EVENT.format(self.config_entry.entry_id)

        old_badge_ids = {_badge_id(b) for b in old.badges}
        for badge in new.badges:
            if _badge_id(badge) in old_badge_ids:
                continue
            data = {
                **base,
                "badge_key": badge.get("badgeKey"),
                "title": badge.get("title"),
                "icon": badge.get("icon"),
                "awarded_at": badge.get("awardedAt"),
            }
            self.hass.bus.async_fire(EVENT_BADGE_EARNED, data)
            async_dispatcher_send(
                self.hass, badge_signal, EVENT_TYPE_BADGE_EARNED, data
            )

        old_streak = old.summary.get("streakDays", 0)
        new_streak = new.summary.get("streakDays", 0)
        if old_streak != new_streak:
            data = {**base, "old": old_streak, "new": new_streak}
            self.hass.bus.async_fire(EVENT_STREAK_CHANGED, data)
            event_type = (
                EVENT_TYPE_STREAK_INCREASED
                if new_streak > old_streak
                else EVENT_TYPE_STREAK_LOST
            )
            async_dispatcher_send(self.hass, coach_signal, event_type, data)

        # Only celebrate a completion on the same calendar day; a day rollover
        # resets the list rather than finishing it.
        if (
            not _all_done(old.today)
            and _all_done(new.today)
            and old.today.get("date") == new.today.get("date")
        ):
            data = {**base, "date": new.today.get("date")}
            self.hass.bus.async_fire(EVENT_ALL_TASKS_DONE, data)
            async_dispatcher_send(
                self.hass, coach_signal, EVENT_TYPE_ALL_TASKS_DONE, data
            )
