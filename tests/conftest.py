"""Shared fixtures for the ArktIQ Coach tests."""
from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.arktiq_coach.api import ArktiqCoachClient

SUMMARY = {
    "goals": [
        {
            "id": "goal-1",
            "title": "Get fit",
            "goalTypeKey": "fitness",
            "level": 3,
            "planEndsAt": "2026-08-31T00:00:00.000Z",
        }
    ],
    "streakDays": 4,
    "badgeCount": 2,
}

TODAY = {
    "date": "2026-08-15",
    "timezone": "Europe/Oslo",
    "tasks": [
        {
            "id": "task-1",
            "title": "Morning workout",
            "goalId": "goal-1",
            "goalTitle": "Get fit",
            "dueAt": "2026-08-15T18:00:00.000Z",
            "slot": "morning",
            "status": "DONE",
            "itemCount": 0,
            "checkedCount": 0,
        },
        {
            "id": "task-2",
            "title": "Evening stretch",
            "goalId": "goal-1",
            "goalTitle": "Get fit",
            "dueAt": "2026-08-15T20:00:00.000Z",
            "slot": "evening",
            "status": "PENDING",
            "itemCount": 3,
            "checkedCount": 1,
        },
    ],
    "doneCount": 1,
    "totalCount": 2,
}

BADGES = [
    {
        "badgeKey": "first_week",
        "title": "First week",
        "icon": "🔥",
        "awardedAt": "2026-08-10T12:00:00.000Z",
    },
    {
        "badgeKey": "starter",
        "title": "Getting started",
        "icon": "🌱",
        "awardedAt": "2026-08-03T12:00:00.000Z",
    },
]

WEIGHT = {
    "key": "weight_kg",
    "name": "Body weight",
    "unit": "kg",
    "value": 82.5,
    "recordedAt": "2026-08-14T07:00:00.000Z",
}

PUSHUPS = {
    "key": "pushups",
    "name": "Max push-ups",
    "unit": "reps",
    "value": 30,
    "recordedAt": "2026-08-12T07:00:00.000Z",
}

PLANK = {
    "key": "plank_hold",
    "name": "Plank hold",
    "unit": "s",
    "value": 90,
    "recordedAt": "2026-08-12T07:00:00.000Z",
}

METRICS = {"weight_kg": WEIGHT, "pushups": PUSHUPS, "plank_hold": PLANK}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield


@pytest.fixture(autouse=True)
def use_threaded_resolver(monkeypatch):
    """Keep aiohttp off the aiodns/pycares resolver in tests.

    pycares spawns a permanent daemon thread on first use, which the test
    harness's thread-leak check flags on whichever test happens to run first.
    """
    import aiohttp.connector
    import aiohttp.resolver

    monkeypatch.setattr(
        aiohttp.connector, "DefaultResolver", aiohttp.resolver.ThreadedResolver
    )


@pytest.fixture
def mock_api(aioclient_mock):
    """Patch the API client with canned responses.

    Yields a dict of AsyncMocks whose return_values tests may mutate.
    Depends on aioclient_mock so async_get_clientsession never builds a real
    aiohttp session (whose DNS resolver leaks a thread the harness flags).
    """
    mocks = {
        "get_summary": AsyncMock(return_value=copy.deepcopy(SUMMARY)),
        "get_today": AsyncMock(return_value=copy.deepcopy(TODAY)),
        "get_badges": AsyncMock(return_value=copy.deepcopy(BADGES)),
        "get_metric_latest": AsyncMock(
            side_effect=lambda key: copy.deepcopy(METRICS[key])
        ),
    }
    with (
        patch.object(ArktiqCoachClient, "get_summary", mocks["get_summary"]),
        patch.object(ArktiqCoachClient, "get_today", mocks["get_today"]),
        patch.object(ArktiqCoachClient, "get_badges", mocks["get_badges"]),
        patch.object(
            ArktiqCoachClient, "get_metric_latest", mocks["get_metric_latest"]
        ),
    ):
        yield mocks
