# ArktIQ Coach — Home Assistant integration: implementation plan

A HACS custom integration for [ArktIQ Coach](https://github.com/arktiq-it/arktiq-coach), built
against the stable read-only personal API (`GET /api/integration/v1/…`, `X-Api-Key` header).
Repo conventions mirror `sparebank1_pengerobot`; HA patterns follow current (2025+) developer
docs: config flow, `DataUpdateCoordinator`, `entry.runtime_data`, `has_entity_name`,
reauth flow, diagnostics, translations.

## 1. What the API gives us today

| Endpoint | Payload |
| --- | --- |
| `GET /integration/v1/summary` | `goals[] {id, title, goalTypeKey, level, planEndsAt}`, `streakDays`, `badgeCount` |
| `GET /integration/v1/today` | `date`, `timezone`, `tasks[] {id, title, goalId, goalTitle, dueAt, slot, status, itemCount, checkedCount}`, `doneCount`, `totalCount` |
| `GET /integration/v1/badges` | `[{badgeKey, title, icon, awardedAt, …}]` newest first |
| `GET /integration/v1/metrics/{key}/latest` | `{key, name, unit, value, recordedAt}` |

- Task `status`: `PENDING | DONE | SKIPPED | MISSED`.
- Global metric keys (from packs): `pushups` (reps), `plank_hold` (s), `weight_kg` (kg).
- Packs (goalTypeKey): `fitness`, `nutrition`, `social`.
- Auth: `X-Api-Key: akq_…`, read-only, revocable. 401/403 ⇒ key revoked ⇒ reauth.
- Rate limit: 120 req/min per IP; poll ≥ 1 min apart. `today` is in the account's timezone.
- Strings arrive in the account's profile locale — entities just display them.

## 2. Core design

### One config entry per API key = one person

Each entry holds `{base_url, api_key, name}` where **name** is the person label
("Remi", "Big sister"). Each entry creates one HA **device** ("ArktIQ Coach Remi") carrying all
of that person's entities. Multiple entries are native HA behaviour — no special handling needed
beyond a `unique_id` (SHA-256 of the API key, truncated) so the same key can't be added twice.
Different entries may point at different `base_url`s (self-hosted instances).

### Polling

One `DataUpdateCoordinator` per entry. Tiered fetch inside a single coordinator:

- **Every refresh (default 5 min):** `today` + `summary` (2 requests).
- **Every 6th refresh (~30 min):** also `badges` + each tracked metric's `latest` (up to 4 more).

≈ 30–35 req/hour/key — far under limits even with 4–5 family keys behind one IP.
On HTTP 429: exponential backoff (same pattern as the sparebank1 coordinator).
On 401/403: raise `ConfigEntryAuthFailed` → HA opens the **reauth** flow (paste a new key).

The coordinator keeps the previous snapshot and diffs it after every refresh to **fire events**
(section 4).

### Modern-HA checklist

- `ArktiqCoachConfigEntry = ConfigEntry[ArktiqCoachCoordinator]`, stored in `entry.runtime_data`.
- `await coordinator.async_config_entry_first_refresh()` in `async_setup_entry`.
- All entities: `has_entity_name = True` + `translation_key`; device name carries the person.
- `DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=f"ArktIQ Coach {name}", manufacturer="ArktIQ", configuration_url=base_url)`.
- `PARALLEL_UPDATES = 0` (coordinator-driven).
- `strings.json` + `translations/en.json` + `translations/nb.json`, `icons.json` for entity icons.
- Diagnostics platform with the API key redacted.

## 3. Entities (per person/entry)

### Sensors (`sensor.py`)

| Entity (translation_key) | State | Notes |
| --- | --- | --- |
| `tasks_done` | `doneCount` | attrs: task list (title, goal, slot, status, checklist progress) |
| `tasks_total` | `totalCount` | |
| `tasks_remaining` | `total - done` | the "nag number" for automations |
| `completion` | `done/total` in % (100 when total = 0) | `state_class: measurement` → long-term statistics; **the competition number** |
| `streak` | `streakDays` | unit `d`, `state_class: measurement` |
| `badge_count` | `badgeCount` | attrs: 5 most recent badges |
| `last_badge` | latest badge title | attrs: `badgeKey`, `icon`, `awardedAt` |
| `next_task` | earliest `dueAt` among PENDING | `device_class: timestamp` |
| `active_goals` | number of goals | attrs: full goals list with levels + `planEndsAt` |
| `goal_level_<goalId>` (dynamic) | current `level` | one per active goal, named after `title`; added/removed as goals change |
| metric sensors (dynamic) | latest `value` | one per tracked metric key; `weight_kg` → `device_class: weight`, `state_class: measurement` (long-term stats/graphs); attrs: `recordedAt`; unavailable while never logged |

### Binary sensor (`binary_sensor.py`)

- `all_done` — on when `doneCount == totalCount` and `totalCount > 0`. Drives "🏆 finished!"
  automations and lights up the competition dashboard.

### Todo (`todo.py`)

- `todo.<name>_coach_today` — `TodoListEntity` rendering today's tasks (DONE → completed,
  checklist tasks show `checkedCount/itemCount` in the description). **Read-only**: no
  `TodoListEntityFeature` flags set, since the API is read-only. Gives a native checklist card
  on every person's dashboard for free.

### Event entities (`event.py`)

- `event.<name>_badge` — event type `badge_earned`, payload = badge fields.
- `event.<name>_coach` — event types `all_tasks_done`, `streak_increased`, `streak_lost`.

Event entities make these usable as **device triggers** in the automation UI (no YAML needed).

## 4. Notifications

The integration never sends notifications itself — it exposes triggers; HA automations deliver
via `notify.mobile_app_*`, TTS, etc. Two mechanisms:

1. **Event entities** (above) for UI-built automations.
2. **Bus events** for power users, fired from the coordinator diff:
   - `arktiq_coach_badge_earned` — `{name, entry_id, badge_key, title, awarded_at}`
   - `arktiq_coach_all_tasks_done` — `{name, entry_id, date}`
   - `arktiq_coach_streak_changed` — `{name, entry_id, old, new}`

README ships copy-paste automations (and later blueprints in `blueprints/` linked from the
README):
- **Evening nudge** — at 19:00, if `tasks_remaining > 0`, notify that person's phone.
- **Badge fanfare** — on `badge_earned`, notify everyone: "🏅 Remi earned *{title}*!"
- **Competition taunt** — when sibling A's `all_done` turns on while sibling B still has tasks:
  "Big sister is done — you have 2 left 😏".
- **Streak guard** — at 21:00, if streak would break (nothing done today), high-priority notify.

## 5. Dashboards & competition

### Per-person dashboard (README YAML, works with stock cards)

- Header: person name + `completion` gauge.
- `todo-list` card bound to `todo.<name>_coach_today`.
- Entities card: streak, badges, next task, goal levels.
- `history-graph` / `statistics-graph`: weight & metrics over time (long-term statistics come
  free from `state_class`).

### Competition dashboard ("Coach Arena", README YAML)

- Side-by-side **gauge cards** of every person's `completion`.
- **Bar comparison** of `streak` and `badge_count`.
- Trophy row: `all_done` binary sensors as glowing badges.
- **Leader template sensor** (documented helper):
  `sensor.coach_leader` = name of the entry with highest completion (tiebreak: streak) — built
  as a template sensor over the per-person sensors, usable in notifications
  ("👑 Today's leader: Big sister").
- `statistics-graph` comparing everyone's `completion` week over week — because `completion` has
  `state_class: measurement`, HA records long-term statistics per person automatically, so
  **weekly/monthly compliance comparison needs no extra API support**.

*Stretch (later release):* an in-integration "leaderboard" device with ranked sensors computed
across all loaded entries. Deferred — cross-entry entities complicate unload/reload, and template
sensors cover it. Revisit if the template approach annoys users.

## 6. Config flow (`config_flow.py`)

- **user** step: `base_url` (default `https://coach.arktiq.no` — confirm), `api_key`, `name`.
  Validate by calling `/summary`; map errors → `cannot_connect` / `invalid_auth`.
  `unique_id` = key hash; `title` = name.
- **reauth** step: new key only; validate, update entry data + unique_id via
  `async_update_reload_and_abort`.
- **reconfigure** step: change `base_url`/`name` without re-adding.
- **Options flow**: scan interval (min 60 s, default 300 s), tracked metric keys
  (multi-select, default all three), toggle badge polling.

## 7. Repository layout (mirrors sparebank1_pengerobot)

```
arktiq-coach-ha/
├── .github/workflows/
│   ├── hacs.yaml          # hacs/action (category: integration), push+PR+daily cron
│   ├── hassfest.yaml      # home-assistant/actions/hassfest
│   ├── tests.yaml         # NEW vs reference: pytest on push/PR
│   └── publish.yaml       # semver from tags ([minor]/[major] in commit msg),
│                          #   sed version into manifest.json + const.py + VERSION,
│                          #   tag + GitHub release with notes (adapted from reference)
├── brand/arktiq_coach/    # icon.png, icon@2x.png, logo.png (+ later PR to home-assistant/brands)
├── custom_components/arktiq_coach/
│   ├── __init__.py        # setup/unload, runtime_data, platform forwarding
│   ├── api.py             # aiohttp client: get_summary/today/badges/metric_latest,
│   │                      #   ArktiqAuthError / ArktiqRateLimitError / ArktiqApiError
│   ├── config_flow.py
│   ├── const.py           # DOMAIN="arktiq_coach", conf keys, defaults, __version__
│   ├── coordinator.py     # tiered fetch, 429 backoff, snapshot diff → events
│   ├── sensor.py
│   ├── binary_sensor.py
│   ├── todo.py
│   ├── event.py
│   ├── diagnostics.py     # redacts api_key
│   ├── manifest.json      # domain, name "ArktIQ Coach", codeowners [@remimikalsen],
│   │                      #   config_flow: true, integration_type: "service",
│   │                      #   iot_class: "cloud_polling", version, documentation, issue_tracker
│   ├── strings.json
│   ├── icons.json
│   └── translations/en.json, nb.json
├── tests/                 # pytest-homeassistant-custom-component; mocked API fixtures:
│                          #   config flow (happy/invalid/reauth), coordinator tiers & backoff,
│                          #   entity states, event firing on diff
├── hacs.json              # { "name": "ArktIQ Coach", "homeassistant": "2025.7", "hacs": "2.0" }
├── LICENSE (MIT) · README.md · VERSION
```

HACS requirements: single integration under `custom_components/`, manifest with
domain/documentation/issue_tracker/codeowners/name/version, GitHub releases (publish.yaml),
repo description + topics (`home-assistant`, `hacs`, `integration`). Install as custom
repository first; default-store submission + `home-assistant/brands` PR once stable.

## 8. Build order

1. **Scaffold** — repo layout, manifest, hacs.json, workflows, README skeleton, brand
   placeholders. hassfest + HACS action green.
2. **API client + config flow** — `api.py`, user/reauth/reconfigure steps, options flow,
   strings/translations. Tests for the flow.
3. **Coordinator + sensors + binary sensor** — tiered polling, backoff, all static sensors,
   dynamic goal-level + metric sensors. Add against the live instance with 2 keys.
4. **Todo + events** — read-only todo list, event entities, bus events from coordinator diff.
5. **Polish** — diagnostics, icons.json, nb translations, README: install, per-person dashboard
   YAML, Coach Arena dashboard YAML, leader template sensor, notification automations.
6. **Release** — 0.1.0 via publish.yaml, install through HACS custom repo on the family HA,
   run the competition for a week, then iterate.

## 9. Suggested app-side additions (arktiq-coach backlog, not blockers)

The integration ships against `/integration/v1` as-is. These would upgrade it later:

1. **`GET /integration/v1/whoami`** — account display name, key label, timezone, stable account
   id → prefills the entry name, gives a proper `unique_id` that survives key rotation.
2. **`GET /integration/v1/metrics`** — enumerate available metrics *with* latest values → one
   request instead of N, no hardcoded key list, auto-discovery of new pack metrics.
3. **`GET /integration/v1/stats?days=30`** — per-day `done/total` history → true compliance
   windows (7/30-day) server-side, backfillable statistics, fair "who won this week" without
   requiring HA to have been recording since day one.
4. **Webhook push** (per-key callback URL) → `iot_class: cloud_push`, instant badge/task
   notifications instead of ≤5-min polling lag.
5. **Per-task points/weights** in `today` → weighted competition scoring instead of raw %.

(1)–(3) fit the versioned surface additively; the `docs/home-assistant.md` "Future: a proper
HACS custom component" note already anticipates this repo.
