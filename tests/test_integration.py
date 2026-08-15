"""Tests for setup, entities and event firing."""
from __future__ import annotations

import copy

from homeassistant.const import CONF_API_KEY, CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.arktiq_coach.const import (
    CONF_BASE_URL,
    DOMAIN,
    EVENT_ALL_TASKS_DONE,
    EVENT_BADGE_EARNED,
    SLOW_CYCLE,
)
from .conftest import BADGES, TODAY

ENTRY_DATA = {
    CONF_NAME: "Remi",
    CONF_BASE_URL: "https://coach.example.com",
    CONF_API_KEY: "akq_test_key",
}


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=ENTRY_DATA,
        title="Remi",
        unique_id="48bd9d65b74a8e08",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state_of(hass: HomeAssistant, entry: MockConfigEntry, unique_suffix: str):
    """Look an entity up by unique_id so entity_id naming stays irrelevant."""
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id == f"{entry.entry_id}_{unique_suffix}":
            return hass.states.get(entity.entity_id)
    return None


async def test_sensor_states(hass: HomeAssistant, mock_api) -> None:
    """The static, goal and metric sensors reflect the API payloads."""
    entry = await _setup_entry(hass)

    assert _state_of(hass, entry, "tasks_done").state == "1"
    assert _state_of(hass, entry, "tasks_total").state == "2"
    assert _state_of(hass, entry, "tasks_remaining").state == "1"
    assert _state_of(hass, entry, "completion").state == "50"
    assert _state_of(hass, entry, "streak").state == "4"
    assert _state_of(hass, entry, "badge_count").state == "2"
    assert _state_of(hass, entry, "last_badge").state == "First week"
    assert _state_of(hass, entry, "active_goals").state == "1"
    assert _state_of(hass, entry, "goal_goal-1").state == "3"
    assert _state_of(hass, entry, "metric_weight_kg").state == "82.5"

    tasks_done = _state_of(hass, entry, "tasks_done")
    assert len(tasks_done.attributes["tasks"]) == 2

    all_done = _state_of(hass, entry, "all_done")
    assert all_done.state == STATE_OFF


async def test_entity_ids_are_english(hass: HomeAssistant, mock_api) -> None:
    """Entity IDs come from the stable English keys, not localized names."""
    await _setup_entry(hass)
    for entity_id in (
        "sensor.arktiq_coach_remi_tasks_done",
        "sensor.arktiq_coach_remi_completion",
        "sensor.arktiq_coach_remi_streak",
        "sensor.arktiq_coach_remi_weight_kg",
        "sensor.arktiq_coach_remi_goal_fitness",
        "binary_sensor.arktiq_coach_remi_all_done",
        "todo.arktiq_coach_remi_today",
        "event.arktiq_coach_remi_badge",
    ):
        assert hass.states.get(entity_id) is not None, entity_id


async def test_todo_list(hass: HomeAssistant, mock_api) -> None:
    """The todo entity mirrors today's list and is read-only."""
    entry = await _setup_entry(hass)
    todo = _state_of(hass, entry, "today")
    assert todo is not None
    # State of a todo entity is the number of incomplete items.
    assert todo.state == "1"
    assert todo.attributes.get("supported_features", 0) == 0


async def test_events_fire_on_changes(hass: HomeAssistant, mock_api) -> None:
    """New badges and finishing the day fire bus events after a refresh."""
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data

    badge_events = []
    done_events = []

    @callback
    def _capture_badge(event) -> None:
        badge_events.append(event)

    @callback
    def _capture_done(event) -> None:
        done_events.append(event)

    hass.bus.async_listen(EVENT_BADGE_EARNED, _capture_badge)
    hass.bus.async_listen(EVENT_ALL_TASKS_DONE, _capture_done)

    # Finish the remaining task and award a new badge.
    finished = copy.deepcopy(TODAY)
    finished["tasks"][1]["status"] = "DONE"
    finished["doneCount"] = 2
    mock_api["get_today"].return_value = finished

    new_badges = copy.deepcopy(BADGES)
    new_badges.insert(
        0,
        {
            "badgeKey": "perfect_day",
            "title": "Perfect day",
            "icon": "🏆",
            "awardedAt": "2026-08-15T19:00:00.000Z",
        },
    )
    mock_api["get_badges"].return_value = new_badges

    # Badges only refresh on slow cycles: run refreshes up to the next one.
    for _ in range(SLOW_CYCLE):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(done_events) == 1
    assert done_events[0].data["name"] == "Remi"
    assert len(badge_events) == 1
    assert badge_events[0].data["badge_key"] == "perfect_day"

    binary = _state_of(hass, entry, "all_done")
    assert binary.state == STATE_ON
    assert _state_of(hass, entry, "completion").state == "100"


async def test_restart_does_not_replay_events(hass: HomeAssistant, mock_api) -> None:
    """The first refresh after setup never fires events."""
    events = []

    @callback
    def _capture(event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_BADGE_EARNED, _capture)
    await _setup_entry(hass)
    assert not events
