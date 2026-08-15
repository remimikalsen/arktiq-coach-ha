"""Constants for the ArktIQ Coach integration."""

__version__ = "0.0.1"

DOMAIN = "arktiq_coach"
MANUFACTURER = "ArktIQ"

CONF_BASE_URL = "base_url"
CONF_TRACKED_METRICS = "tracked_metrics"
CONF_TRACK_BADGES = "track_badges"

DEFAULT_BASE_URL = "https://coach.arktiq.no"
DEFAULT_SCAN_INTERVAL = 300
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600

# Global metrics seeded by the app's packs; the options flow accepts custom
# values too, so future pack metrics work without a code change.
KNOWN_METRICS = {
    "weight_kg": "Body weight",
    "pushups": "Max push-ups",
    "plank_hold": "Plank hold",
}
DEFAULT_METRICS = list(KNOWN_METRICS)

# Badges and metrics change rarely; fetch them only every Nth refresh cycle.
SLOW_CYCLE = 6

# Task status values from the API (OccurrenceStatus).
STATUS_PENDING = "PENDING"
STATUS_DONE = "DONE"
STATUS_SKIPPED = "SKIPPED"
STATUS_MISSED = "MISSED"

# Bus events (for YAML automations).
EVENT_BADGE_EARNED = f"{DOMAIN}_badge_earned"
EVENT_ALL_TASKS_DONE = f"{DOMAIN}_all_tasks_done"
EVENT_STREAK_CHANGED = f"{DOMAIN}_streak_changed"

# Dispatcher signals feeding the event entities (formatted with entry_id).
SIGNAL_BADGE_EVENT = f"{DOMAIN}_badge_event_{{}}"
SIGNAL_COACH_EVENT = f"{DOMAIN}_coach_event_{{}}"

# Event entity event types.
EVENT_TYPE_BADGE_EARNED = "badge_earned"
EVENT_TYPE_ALL_TASKS_DONE = "all_tasks_done"
EVENT_TYPE_STREAK_INCREASED = "streak_increased"
EVENT_TYPE_STREAK_LOST = "streak_lost"
