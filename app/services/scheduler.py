"""APScheduler setup. Idempotent across restarts via SQLAlchemy jobstore."""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

from app.config import config
from app.services.nudges import run_nudge_sweep, send_pending_approvals
from app.services.digest import post_weekly_digest

log = logging.getLogger("pab.scheduler")

_scheduler: BackgroundScheduler | None = None


def start_scheduler(slack_client) -> BackgroundScheduler:
    """Start a BackgroundScheduler. Jobs are keyed by stable ids with replace_existing=True
    so restarts never duplicate them."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    tz = ZoneInfo(config.timezone)

    jobstores = {
        "default": SQLAlchemyJobStore(url=config.database_url),
    }
    scheduler = BackgroundScheduler(jobstores=jobstores, timezone=tz)

    scheduler.add_job(
        run_nudge_sweep, trigger=CronTrigger(hour="9,13,17", minute=0, timezone=tz),
        args=[slack_client], id="nudge_sweep", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        send_pending_approvals, trigger=CronTrigger(hour="10", minute=0, timezone=tz),
        args=[slack_client], id="approvals_sweep", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        post_weekly_digest, trigger=CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=tz),
        args=[slack_client], id="weekly_digest", replace_existing=True, max_instances=1,
    )

    scheduler.start()
    log.info("Scheduler started with jobs: %s", [j.id for j in scheduler.get_jobs()])
    _scheduler = scheduler
    return scheduler
