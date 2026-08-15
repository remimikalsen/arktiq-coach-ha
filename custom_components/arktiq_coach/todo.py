"""Read-only todo list showing today's coach tasks."""
from __future__ import annotations

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import STATUS_DONE
from .coordinator import ArktiqCoachConfigEntry
from .entity import ArktiqCoachEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArktiqCoachConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the todo list."""
    async_add_entities([ArktiqCoachTodoList(entry.runtime_data)])


class ArktiqCoachTodoList(ArktiqCoachEntity, TodoListEntity):
    """Today's tasks as a native (read-only) todo list.

    No TodoListEntityFeature flags are set: the personal API is read-only,
    so tasks are checked off in the app, not from Home Assistant.
    """

    _entity_domain = "todo"
    _attr_translation_key = "today"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "today")

    @property
    def todo_items(self) -> list[TodoItem] | None:
        items: list[TodoItem] = []
        for task in self.coordinator.data.today.get("tasks", []):
            description = task.get("goalTitle") or ""
            item_count = task.get("itemCount") or 0
            if item_count > 1:
                description = (
                    f"{description} · {task.get('checkedCount', 0)}/{item_count}"
                ).strip(" ·")
            due = (
                dt_util.parse_datetime(task["dueAt"]) if task.get("dueAt") else None
            )
            items.append(
                TodoItem(
                    uid=task.get("id"),
                    summary=task.get("title") or "",
                    status=(
                        TodoItemStatus.COMPLETED
                        if task.get("status") == STATUS_DONE
                        else TodoItemStatus.NEEDS_ACTION
                    ),
                    due=due,
                    description=description or None,
                )
            )
        return items
