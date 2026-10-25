# PAB Event Bot

A Slack bot that coordinates student-org events with DM check-ins and a budget
tracker. It knows the event's budget, date, funding deadlines (RFF — Request for
Funds), and task owners, and it DMs people to hold them accountable. Pitched for
the **Cubbie Hackathon Track 3: Group Chat Assistant**, with PAB as the proof case.

## Quick start

```bash
# venv (parent dir has ":" in its name, which Python's venv refuses — install elsewhere)
python3 -m venv ~/.venvs/pab-event-bot
source ~/.venvs/pab-event-bot/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_API_KEY
python seed.py          # optional demo data
python -m app.main
```

The Slack app manifest and full setup walkthrough live in [§1 "Create the Slack app
from a manifest"](#1-create-the-slack-app-from-a-manifest) below.

## What it does

- `/newevent` → modal → generates a milestone timeline backward from the event
  date, posts and pins a channel summary.
- `/status`, `/budget` → Block Kit snapshots. Budget warns when estimated+committed+spent
  exceeds total.
- `/assign <task> @user` → sets owner and DMs them.
- `/vendor add | update | list` → outreach tracker.
- `@`-mention in the event channel to ask grounded questions ("when is the RFF
  due?", "who owns the DJ?"). Answers come only from the event data.
- DM check-ins with Done / In progress / Blocked buttons on a 3-step escalation
  ladder (gentle → firmer → final + channel + director DM). Respects quiet
  hours (9pm → 8am America/Phoenix) and max one DM per person per task per day.
- Approvals DM the approver with Approve / Request changes buttons.
- Plain-language DM updates (e.g. "got a quote from Pizza Co for $450") are
  parsed with Claude into structured JSON, then confirmed with Confirm / Edit /
  Discard before any DB write.
- Weekly digest posts Monday 9am America/Phoenix per event channel: overdue,
  upcoming 7 days, budget snapshot, stalled vendors.

## Stack

- Python 3.11+
- slack-bolt in Socket Mode (no public URL)
- SQLite via SQLAlchemy
- APScheduler with a SQLAlchemy jobstore (idempotent across restarts)
- Anthropic SDK (model via `ANTHROPIC_MODEL`)

## 1. Create the Slack app from a manifest

Go to https://api.slack.com/apps → *Create New App* → *From a manifest*. Paste:

```yaml
display_information:
  name: PAB Event Bot
  description: Campus event planner and budget tracker for student orgs.
  background_color: "#8C1D40"
features:
  app_home:
    home_tab_enabled: false
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
  bot_user:
    display_name: PAB Event Bot
    always_online: true
  slash_commands:
    - command: /ping
      description: Smoke test
      should_escape: false
    - command: /newevent
      description: Create a new event in this workspace
      should_escape: false
    - command: /eventstatus
      description: Show task status for this channel's event
      should_escape: false
    - command: /budget
      description: Show budget snapshot for this channel's event
      should_escape: false
    - command: /assign
      description: Assign a task to a user
      usage_hint: "<task name> @user"
      should_escape: true
    - command: /vendor
      description: Add, update, or list vendors
      usage_hint: "add <name> [@owner] | update <name> stage=<stage> [quote=<n>] | list"
      should_escape: true
    - command: /nudgenow
      description: Admin - run a nudge sweep immediately (demo and debug)
      should_escape: false
oauth_config:
  scopes:
    bot:
      - chat:write
      - chat:write.public
      - commands
      - app_mentions:read
      - channels:read
      - channels:history
      - channels:join
      - groups:read
      - groups:history
      - im:write
      - im:history
      - users:read
      - pins:write
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.im
  interactivity:
    is_enabled: true
  org_deploy_enabled: false
  socket_mode_enabled: true
  token_rotation_enabled: false
```

Then:

1. *Install to Workspace* → copy the **Bot User OAuth Token** (`xoxb-...`) → that's `SLACK_BOT_TOKEN`.
2. *Basic Information* → *App-Level Tokens* → *Generate Token and Scopes* → add `connections:write` → copy the token (`xapp-...`) → that's `SLACK_APP_TOKEN` : .
3. *Event Subscriptions*: confirm `app_mention` and `message.im` are subscribed. (Socket Mode handles delivery.)
4. *Socket Mode*: confirm Enabled.

## 2. Set up locally

```bash
cd pab-event-bot
# NOTE: this project's parent directory contains ":" characters, which
# Python's venv refuses (`:` is the PATH separator). Put the venv outside
# that path:
python3 -m venv ~/.venvs/pab-event-bot
source ~/.venvs/pab-event-bot/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Then edit .env and paste in your tokens + Anthropic key.
```

`.env` fields:

- `SLACK_BOT_TOKEN` — `xoxb-...`
- `SLACK_APP_TOKEN` — `xapp-...`
- `ANTHROPIC_API_KEY` — your Anthropic key
- `ANTHROPIC_MODEL` — e.g. `claude-sonnet-5-5`
- `DATABASE_URL` — default `sqlite:///pab_event_bot.db`
- `TIMEZONE` — default `America/Phoenix`
- `QUIET_HOURS_START` / `QUIET_HOURS_END` — hours (0-23). Default 21/8 → no DMs
  from 9pm to 8am.
- `NUDGE_LOOKAHEAD_DAYS` — default 3
- `STALLED_VENDOR_DAYS` — default 5

## 3. Seed demo data (optional)

```bash
python seed.py
```

Creates a Homecoming Mixer event ~6 weeks out, two owners, a director, a few
budget lines and vendors.

## 4. Run

```bash
python -m app.main
```

You should see `Starting PAB Event Bot in Socket Mode...`. Try `/ping` in any
channel; the bot replies ":wave: pong".

## 5. Demo script (end to end)

In an event channel (invite the bot via `/invite @PAB Event Bot` if needed):

1. `/newevent` → modal: name=`Homecoming Mixer`, date=~6 weeks out, budget=`2000`,
   channel=this channel. The bot posts and pins a timeline. The RFF milestone's
   `needs_approval` is true; its due date becomes the event's RFF deadline.
2. `/assign DJ outreach @you` — reassigns the DJ task and DMs you.
3. In the bot DM, reply "got a quote from Pizza Co for $450".
   The bot parses, shows a Confirm / Edit / Discard card. Confirm.
4. Back in channel: `/budget` — the Pizza Co quote shows as an estimated line.
5. `@PAB Event Bot when is the RFF due?` → answers from event data.
6. `@PAB Event Bot budget left?` → answers from event data.
7. Scheduler: nudges run at 9/13/17 local time; approval sweep at 10; weekly
   digest Monday 9am. For a live demo you can invoke
   `app.services.nudges.run_nudge_sweep(app.client)` from a Python shell.

## 6. Project layout

```
app/
  main.py            Bolt init, scheduler start
  config.py          env loader
  db.py, models.py   SQLAlchemy
  services/
    timeline.py      backward-dated milestones from YAML template
    budget.py        totals and warnings
    nudges.py        DM check-ins + escalation ladder
    scheduler.py     APScheduler with SQLAlchemy jobstore
    digest.py        weekly Monday digest
    llm.py           parse_update(), answer_question()
    llm_apply.py     apply confirmed updates to DB
    blocks.py        Block Kit builders
    events.py        domain helpers
  handlers/
    commands.py      slash commands
    mentions.py      @mention + message.im
    actions.py       button + modal handlers
  templates/
    funded_campus_event.yaml   editable milestone offsets
seed.py              demo data
```

## 7. Design notes

- **Idempotency.** Scheduled jobs use stable ids with `replace_existing=True`,
  stored in a SQLAlchemy jobstore, so restart doesn't double-schedule. DMs are
  guarded by a `nudge_log(task_id, user_id, day)` row — one DM per person per
  task per day.
- **LLM confirmation.** Every DB write that came from the LLM goes through a
  `PendingUpdate` row with Confirm / Edit / Discard buttons. The LLM never
  writes directly.
- **Grounded Q&A.** `answer_question` is instructed to use only the JSON
  snapshot and to say "I don't have that in the event data" otherwise. Dates
  and amounts are never invented.
- **Quiet hours.** `nudges._in_quiet_hours` handles the midnight-crossing
  default window (21..8).
- **Hackathon-grade shortcuts.** Fuzzy task matching is case-insensitive
  substring; DM parsing picks the most-recent event the user owns a task in;
  no multi-workspace support.

## 8. Known TODOs

- The RFF `days_before` offset in `templates/funded_campus_event.yaml` is a
  placeholder (21). Replace with PAB's real RFF lead time.
- No tests yet (hackathon demo).
- `/vendor list` + outreach don't surface which quote feeds which budget line
  beyond the Vendor row's `quote_amount`.
