"""Sensors for ArktIQ Coach."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import STATUS_PENDING
from .coordinator import (
    ArktiqCoachConfigEntry,
    ArktiqCoachCoordinator,
    ArktiqCoachData,
)
from .entity import ArktiqCoachEntity

PARALLEL_UPDATES = 0

# Units/device classes for the metrics the app's packs seed today; anything
# else falls back to the unit string the API reports.
METRIC_PRESETS: dict[str, tuple[SensorDeviceClass | None, str | None]] = {
    "weight_kg": (SensorDeviceClass.WEIGHT, UnitOfMass.KILOGRAMS),
    "plank_hold": (None, UnitOfTime.SECONDS),
    "pushups": (None, "reps"),
}


def _completion(data: ArktiqCoachData) -> int:
    total = data.today.get("totalCount", 0)
    if total == 0:
        return 100
    return round(100 * data.today.get("doneCount", 0) / total)


def _next_task(data: ArktiqCoachData) -> datetime | None:
    due = [
        parsed
        for task in data.today.get("tasks", [])
        if task.get("status") == STATUS_PENDING and task.get("dueAt")
        and (parsed := dt_util.parse_datetime(task["dueAt"])) is not None
    ]
    return min(due, default=None)


def _task_attributes(data: ArktiqCoachData) -> dict[str, Any]:
    return {
        "date": data.today.get("date"),
        "timezone": data.today.get("timezone"),
        "tasks": [
            {
                "title": task.get("title"),
                "goal": task.get("goalTitle"),
                "slot": task.get("slot"),
                "status": task.get("status"),
                "due_at": task.get("dueAt"),
                "checked": task.get("checkedCount"),
                "checklist_items": task.get("itemCount"),
            }
            for task in data.today.get("tasks", [])
        ],
    }


def _goal_attributes(data: ArktiqCoachData) -> dict[str, Any]:
    return {
        "goals": [
            {
                "title": goal.get("title"),
                "type": goal.get("goalTypeKey"),
                "level": goal.get("level"),
                "plan_ends_at": goal.get("planEndsAt"),
            }
            for goal in data.summary.get("goals", [])
        ]
    }


def _badge_attributes(data: ArktiqCoachData) -> dict[str, Any]:
    return {
        "recent": [
            {
                "title": badge.get("title"),
                "badge_key": badge.get("badgeKey"),
                "icon": badge.get("icon"),
                "awarded_at": badge.get("awardedAt"),
            }
            for badge in data.badges[:5]
        ]
    }


@dataclass(frozen=True, kw_only=True)
class ArktiqSensorDescription(SensorEntityDescription):
    """Sensor description with value/attribute extractors."""

    value_fn: Callable[[ArktiqCoachData], StateType | datetime]
    attributes_fn: Callable[[ArktiqCoachData], dict[str, Any] | None] = (
        lambda data: None
    )


SENSORS: tuple[ArktiqSensorDescription, ...] = (
    ArktiqSensorDescription(
        key="tasks_done",
        translation_key="tasks_done",
        value_fn=lambda data: data.today.get("doneCount"),
        attributes_fn=_task_attributes,
    ),
    ArktiqSensorDescription(
        key="tasks_total",
        translation_key="tasks_total",
        value_fn=lambda data: data.today.get("totalCount"),
    ),
    ArktiqSensorDescription(
        key="tasks_remaining",
        translation_key="tasks_remaining",
        value_fn=lambda data: (
            data.today.get("totalCount", 0) - data.today.get("doneCount", 0)
        ),
    ),
    ArktiqSensorDescription(
        key="completion",
        translation_key="completion",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_completion,
    ),
    ArktiqSensorDescription(
        key="streak",
        translation_key="streak",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.summary.get("streakDays"),
    ),
    ArktiqSensorDescription(
        key="badge_count",
        translation_key="badge_count",
        value_fn=lambda data: data.summary.get("badgeCount"),
        attributes_fn=_badge_attributes,
    ),
    ArktiqSensorDescription(
        key="last_badge",
        translation_key="last_badge",
        value_fn=lambda data: (
            data.badges[0].get("title") if data.badges else None
        ),
        attributes_fn=lambda data: (
            {
                "badge_key": data.badges[0].get("badgeKey"),
                "icon": data.badges[0].get("icon"),
                "awarded_at": data.badges[0].get("awardedAt"),
            }
            if data.badges
            else None
        ),
    ),
    ArktiqSensorDescription(
        key="next_task",
        translation_key="next_task",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_task,
    ),
    ArktiqSensorDescription(
        key="active_goals",
        translation_key="active_goals",
        value_fn=lambda data: len(data.summary.get("goals", [])),
        attributes_fn=_goal_attributes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArktiqCoachConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up static sensors, then track goals/metrics as they appear."""
    coordinator = entry.runtime_data
    async_add_entities(
        ArktiqCoachSensor(coordinator, description) for description in SENSORS
    )

    known_goals: set[str] = set()
    known_metrics: set[str] = set()

    @callback
    def _sync_dynamic_entities() -> None:
        if not coordinator.last_update_success:
            return
        new_entities: list[SensorEntity] = []
        for goal in coordinator.data.summary.get("goals", []):
            goal_id = goal.get("id")
            if goal_id and goal_id not in known_goals:
                known_goals.add(goal_id)
                new_entities.append(
                    ArktiqGoalLevelSensor(
                        coordinator, goal_id, goal.get("goalTypeKey") or "goal"
                    )
                )
        for key, payload in coordinator.data.metrics.items():
            if payload is not None and key not in known_metrics:
                known_metrics.add(key)
                new_entities.append(ArktiqMetricSensor(coordinator, key, payload))
        if new_entities:
            async_add_entities(new_entities)

    _sync_dynamic_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_dynamic_entities))


class ArktiqCoachSensor(ArktiqCoachEntity, SensorEntity):
    """A static per-account sensor."""

    _entity_domain = "sensor"
    entity_description: ArktiqSensorDescription

    def __init__(
        self,
        coordinator: ArktiqCoachCoordinator,
        description: ArktiqSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attributes_fn(self.coordinator.data)


class ArktiqGoalLevelSensor(ArktiqCoachEntity, SensorEntity):
    """Current plan level of one active goal; named after the goal."""

    _entity_domain = "sensor"
    _attr_icon = "mdi:target"

    def __init__(
        self, coordinator: ArktiqCoachCoordinator, goal_id: str, goal_type: str
    ) -> None:
        super().__init__(
            coordinator, f"goal_{goal_id}", object_id=f"goal_{goal_type}"
        )
        self._goal_id = goal_id

    def _goal(self) -> dict[str, Any] | None:
        for goal in self.coordinator.data.summary.get("goals", []):
            if goal.get("id") == self._goal_id:
                return goal
        return None

    @property
    def available(self) -> bool:
        return super().available and self._goal() is not None

    @property
    def name(self) -> str | None:
        goal = self._goal()
        return goal.get("title") if goal else None

    @property
    def native_value(self) -> StateType:
        goal = self._goal()
        return goal.get("level") if goal else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        goal = self._goal()
        if goal is None:
            return None
        return {
            "goal_type": goal.get("goalTypeKey"),
            "plan_ends_at": goal.get("planEndsAt"),
        }


class ArktiqMetricSensor(ArktiqCoachEntity, SensorEntity):
    """Latest logged value of a tracked metric (e.g. body weight)."""

    _entity_domain = "sensor"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ArktiqCoachCoordinator,
        metric_key: str,
        payload: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, f"metric_{metric_key}", object_id=metric_key)
        self._metric_key = metric_key
        device_class, unit = METRIC_PRESETS.get(
            metric_key, (None, payload.get("unit") or None)
        )
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

    def _payload(self) -> dict[str, Any] | None:
        return self.coordinator.data.metrics.get(self._metric_key)

    @property
    def available(self) -> bool:
        return super().available and self._payload() is not None

    @property
    def name(self) -> str | None:
        payload = self._payload()
        return payload.get("name") if payload else self._metric_key

    @property
    def native_value(self) -> StateType:
        payload = self._payload()
        return payload.get("value") if payload else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        payload = self._payload()
        if payload is None:
            return None
        return {"recorded_at": payload.get("recordedAt")}
