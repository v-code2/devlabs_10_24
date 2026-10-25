import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    slack_bot_token: str
    slack_app_token: str
    anthropic_api_key: str
    anthropic_model: str
    database_url: str
    timezone: str
    quiet_hours_start: int
    quiet_hours_end: int
    nudge_lookahead_days: int
    stalled_vendor_days: int


def load_config() -> Config:
    return Config(
        slack_bot_token=os.environ.get("SLACK_BOT_TOKEN", ""),
        slack_app_token=os.environ.get("SLACK_APP_TOKEN", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///pab_event_bot.db"),
        timezone=os.environ.get("TIMEZONE", "America/Phoenix"),
        quiet_hours_start=int(os.environ.get("QUIET_HOURS_START", "21")),
        quiet_hours_end=int(os.environ.get("QUIET_HOURS_END", "8")),
        nudge_lookahead_days=int(os.environ.get("NUDGE_LOOKAHEAD_DAYS", "3")),
        stalled_vendor_days=int(os.environ.get("STALLED_VENDOR_DAYS", "5")),
    )


config = load_config()
