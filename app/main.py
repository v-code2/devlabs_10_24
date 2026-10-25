import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("pab")


def build_app() -> App:
    app = App(token=config.slack_bot_token)

    @app.command("/ping")
    def handle_ping(ack, respond, command):
        ack()
        respond(f":wave: pong from PAB Event Bot ({config.anthropic_model})")

    return app


def main() -> None:
    if not config.slack_bot_token or not config.slack_app_token:
        raise SystemExit("Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN in .env")

    app = build_app()

    from app.db import init_db
    init_db()

    from app.handlers import commands, mentions, actions
    commands.register(app)
    mentions.register(app)
    actions.register(app)

    from app.services.scheduler import start_scheduler
    start_scheduler(app.client)

    log.info("Starting PAB Event Bot in Socket Mode...")
    SocketModeHandler(app, config.slack_app_token).start()


if __name__ == "__main__":
    main()
