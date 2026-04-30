def run() -> None:
    from pbsbot.slack.app import run as app_run

    app_run()

__all__ = ["run"]
