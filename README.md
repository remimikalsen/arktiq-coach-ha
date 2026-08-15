![Build Status](https://img.shields.io/github/actions/workflow/status/remimikalsen/arktiq-coach-ha/publish.yaml)
![Tests](https://img.shields.io/github/actions/workflow/status/remimikalsen/arktiq-coach-ha/tests.yaml?label=Tests)
![HACS Test](https://img.shields.io/github/actions/workflow/status/remimikalsen/arktiq-coach-ha/hacs.yaml?label=HACS)
![Hassfest Test](https://img.shields.io/github/actions/workflow/status/remimikalsen/arktiq-coach-ha/hassfest.yaml?label=Hassfest)
![License](https://img.shields.io/github/license/remimikalsen/arktiq-coach-ha)
![Version](https://img.shields.io/github/tag/remimikalsen/arktiq-coach-ha)

# ArktIQ Coach for Home Assistant 🎯🔥

A Home Assistant integration for [ArktIQ Coach](https://github.com/arktiq-it) — the personal
coaching app. Track everyone's daily tasks, streaks, badges and measurements in Home Assistant,
get notified when someone earns a badge or finishes their day, and build a family **competition
dashboard**.

## Features ✨

- 👤 **One entry per person** — add each API key with a name ("Remi", "Big sister"); every
  person gets their own device with a full set of entities
- ✅ **Today's tasks** — done/total/remaining sensors plus a native **to-do list** card
- 📊 **Completion %** — the competition number, recorded as long-term statistics automatically
- 🔥 **Streaks, badges and goal levels** — including a sensor per active goal
- ⚖️ **Measurements** — body weight (proper `weight` device class), push-ups, plank hold
- 🔔 **Events for notifications** — badge earned, all tasks done, streak changed — as both
  event entities (device triggers in the automation UI) and bus events for YAML
- 🔑 **Key lifecycle handled** — revoked keys trigger Home Assistant's re-authentication flow
- 🌍 **English and Norwegian** translations

## Prerequisites 📋

For each person you want to add:

1. Log in to ArktIQ Coach as that person.
2. Go to **Settings → Personal API → Create key**, name it (e.g. "Home Assistant").
3. Copy the `akq_…` token — it is shown exactly once.

Keys are **read-only**: they can read programs, today's tasks, badges and latest measurements —
nothing else. Revoking a key in Settings cuts Home Assistant off immediately (the integration
will then ask for a new key).

## Installation 📦

### Via HACS (recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed
2. HACS → **⋮** (top right) → **Custom repositories**
3. Add `https://github.com/remimikalsen/arktiq-coach-ha`, category **Integration**
4. Find "ArktIQ Coach" in HACS and download it
5. **Restart Home Assistant**

### Manual

1. Download the latest release
2. Copy `custom_components/arktiq_coach` into your `custom_components` directory
3. Restart Home Assistant

## Configuration 🔧

1. **Settings → Devices & Services → + Add Integration** → "ArktIQ Coach"
2. Fill in:
   - **Name** — who this key belongs to (used in device and entity names)
   - **ArktIQ Coach URL** — your instance address
   - **API key** — the `akq_…` token
3. Repeat for every family member. Each key becomes its own device.

### Options (per entry, via **Configure**)

| Option | Default | Notes |
| --- | --- | --- |
| Update interval | 300 s | Tasks + summary each poll; badges + metrics every 6th poll |
| Tracked metrics | weight, push-ups, plank | Custom keys allowed for future packs |
| Track badges | on | Disable to skip badge polling entirely |

The default cadence is ~35 requests/hour per person — far below the API's rate limit, even
with several people behind one IP.

## Entities 📊

Per person (device "ArktIQ Coach *Name*"):

| Entity | Type | Description |
| --- | --- | --- |
| Tasks done / total / remaining | sensor | Today's counts; done-sensor carries the task list as attributes |
| Completion today | sensor (%) | `done/total` — 100 % on task-free days; long-term statistics |
| Streak | sensor (days) | Consecutive days with at least one completed task |
| Badges / Last badge | sensor | Count + most recent, with details as attributes |
| Next task due | sensor (timestamp) | Earliest pending task today |
| Active goals | sensor | Count, with goals + levels as attributes |
| *Goal title* | sensor | One per active goal — current plan level |
| Body weight, Max push-ups, Plank hold | sensor | Latest logged values (weight gets proper unit/graphs) |
| All tasks done | binary sensor | Trophy time 🏆 |
| Today's tasks | todo | Read-only checklist (check off in the app) |
| Badge / Coach event | event | Device triggers: `badge_earned`, `all_tasks_done`, `streak_increased`, `streak_lost` |

## Notifications 🔔

Use the **event entities** in the automation UI (pick the device → the event as trigger), or
listen to the bus events in YAML. All payloads include `name` (the person) and `entry_id`.

| Bus event | Extra data |
| --- | --- |
| `arktiq_coach_badge_earned` | `badge_key`, `title`, `icon`, `awarded_at` |
| `arktiq_coach_all_tasks_done` | `date` |
| `arktiq_coach_streak_changed` | `old`, `new` |

### Badge fanfare (notify the whole family)

```yaml
automation:
  - alias: "Coach: badge fanfare"
    trigger:
      - platform: event
        event_type: arktiq_coach_badge_earned
    action:
      - service: notify.notify
        data:
          title: "🏅 New badge!"
          message: "{{ trigger.event.data.name }} earned “{{ trigger.event.data.title }}”!"
```

### Evening nudge (per person)

```yaml
automation:
  - alias: "Coach: Remi's tasks still open at 19:00"
    trigger:
      - platform: time
        at: "19:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.arktiq_coach_remi_tasks_remaining
        above: 0
    action:
      - service: notify.mobile_app_remis_phone
        data:
          message: >
            {{ states('sensor.arktiq_coach_remi_tasks_remaining') }} coach task(s) left today.
```

### Competition taunt

```yaml
automation:
  - alias: "Coach: big sister finished first"
    trigger:
      - platform: state
        entity_id: binary_sensor.arktiq_coach_big_sister_all_tasks_done
        to: "on"
    condition:
      - condition: numeric_state
        entity_id: sensor.arktiq_coach_remi_tasks_remaining
        above: 0
    action:
      - service: notify.mobile_app_remis_phone
        data:
          message: >
            Big sister is done for today — you still have
            {{ states('sensor.arktiq_coach_remi_tasks_remaining') }} left 😏

  - alias: "Coach: streak guard"
    trigger:
      - platform: time
        at: "21:00:00"
    condition:
      - condition: state
        entity_id: sensor.arktiq_coach_remi_tasks_done_today
        state: "0"
    action:
      - service: notify.mobile_app_remis_phone
        data:
          title: "🔥 Streak in danger!"
          message: "Nothing done today — your {{ states('sensor.arktiq_coach_remi_streak') }}-day streak ends at midnight."
```

> 💡 Your entity IDs may differ — check **Settings → Devices & Services → ArktIQ Coach** or
> Developer Tools → States.

## Dashboards 🖥️

### Per-person view

```yaml
type: vertical-stack
cards:
  - type: gauge
    entity: sensor.arktiq_coach_remi_completion_today
    name: Remi today
    min: 0
    max: 100
    severity:
      green: 80
      yellow: 40
      red: 0
  - type: todo-list
    entity: todo.arktiq_coach_remi_today_s_tasks
  - type: entities
    entities:
      - sensor.arktiq_coach_remi_streak
      - sensor.arktiq_coach_remi_badges
      - sensor.arktiq_coach_remi_next_task_due
      - sensor.arktiq_coach_remi_body_weight
  - type: statistics-graph
    title: Weight
    entities:
      - sensor.arktiq_coach_remi_body_weight
    stat_types: [mean]
    days_to_show: 30
```

### Coach Arena — the competition dashboard 🏟️

```yaml
type: vertical-stack
cards:
  - type: horizontal-stack
    cards:
      - type: gauge
        entity: sensor.arktiq_coach_remi_completion_today
        name: Remi
        min: 0
        max: 100
      - type: gauge
        entity: sensor.arktiq_coach_big_sister_completion_today
        name: Big sister
        min: 0
        max: 100
  - type: glance
    title: Finished today 🏆
    entities:
      - entity: binary_sensor.arktiq_coach_remi_all_tasks_done
        name: Remi
      - entity: binary_sensor.arktiq_coach_big_sister_all_tasks_done
        name: Big sister
  - type: entities
    title: Streaks & badges
    entities:
      - entity: sensor.arktiq_coach_remi_streak
        name: Remi 🔥
      - entity: sensor.arktiq_coach_big_sister_streak
        name: Big sister 🔥
      - entity: sensor.arktiq_coach_remi_badges
        name: Remi 🏅
      - entity: sensor.arktiq_coach_big_sister_badges
        name: Big sister 🏅
  - type: statistics-graph
    title: Completion, last 30 days
    entities:
      - sensor.arktiq_coach_remi_completion_today
      - sensor.arktiq_coach_big_sister_completion_today
    stat_types: [mean]
    days_to_show: 30
```

Because the completion sensors record long-term statistics, the weekly/monthly comparison
works out of the box — the longer the integration runs, the better the rivalry data.

### Who's winning? A leader sensor

```yaml
template:
  - sensor:
      - name: "Coach leader"
        state: >
          {% set people = {
            'Remi': [states('sensor.arktiq_coach_remi_completion_today') | int(0),
                     states('sensor.arktiq_coach_remi_streak') | int(0)],
            'Big sister': [states('sensor.arktiq_coach_big_sister_completion_today') | int(0),
                           states('sensor.arktiq_coach_big_sister_streak') | int(0)],
          } %}
          {{ (people.items() | sort(attribute='1', reverse=true) | first)[0] }}
        icon: mdi:crown
```

Ranks by completion %, tiebreak on streak. Use it in a morning announcement:
"👑 Current leader: {{ states('sensor.coach_leader') }}".

## Polling & privacy 🔒

- Default: today + summary every 5 minutes, badges + metrics every 30 minutes per person.
- Polling counts as account activity, so integrated accounts are never flagged inactive.
- Treat the API key like a password — it is only ever sent in a header, so use HTTPS.
  Keys are stored in Home Assistant's config entry storage; secure your HA instance and backups.
- If a key leaks, revoke it in the app — the integration will prompt for a replacement.

## Troubleshooting 🔧

**"The API key was rejected"** — the key was revoked or mistyped. Create a fresh key in
**Settings → Personal API** and paste the whole `akq_…` token.

**Sensors show "unavailable"** — check that the instance URL is reachable from HA and uses
HTTPS. See the logs for details.

**Metric sensors missing** — a metric sensor only appears once that metric exists for the
account (e.g. weight appears with a weight-loss program). Manage tracked metrics under
**Configure**.

**Times look off** — `today` follows the account's profile timezone, not Home Assistant's.

### Debug logging

```yaml
logger:
  logs:
    custom_components.arktiq_coach: debug
```

## Support 💬

- 🐛 **Issues**: [GitHub Issues](https://github.com/remimikalsen/arktiq-coach-ha/issues)

## License 📄

MIT — see [LICENSE](LICENSE).
