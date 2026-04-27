"""Slack Bolt 서버 — 버튼 클릭 처리."""

import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from .main import cmd_approve


app = App(token=os.getenv("SLACK_BOT_TOKEN"), signing_secret=os.getenv("SLACK_SIGNING_SECRET"))


@app.action("approve_draft")
def handle_approve_button(ack, body, logger):
    """OK 버튼 클릭 처리."""
    ack()
    draft_id = body["actions"][0]["value"]
    logger.info(f"approve_draft clicked: {draft_id}")

    # approve 실행
    try:
        from argparse import Namespace
        args = Namespace(draft_id=draft_id)
        result = cmd_approve(args)
        if result == 0:
            logger.info(f"✅ 게시 완료: {draft_id}")
        else:
            logger.error(f"❌ 게시 실패: {draft_id}")
    except Exception as e:
        logger.error(f"❌ 에러: {e}")


@app.action("reject_draft")
def handle_reject_button(ack, body, logger):
    """Reject 버튼 클릭 처리."""
    ack()
    draft_id = body["actions"][0]["value"]
    logger.info(f"reject_draft clicked: {draft_id}")

    # reject 실행
    try:
        from argparse import Namespace
        args = Namespace(draft_id=draft_id)
        from .main import cmd_reject
        result = cmd_reject(args)
        if result == 0:
            logger.info(f"✅ 거절 완료: {draft_id}")
        else:
            logger.error(f"❌ 거절 실패: {draft_id}")
    except Exception as e:
        logger.error(f"❌ 에러: {e}")


def create_flask_app():
    """Flask 앱 생성 (Render용)."""
    from flask import Flask, request

    flask_app = Flask(__name__)
    handler = SlackRequestHandler(app)

    @flask_app.route("/slack/events", methods=["POST"])
    def slack_events():
        return handler.handle(request)

    @flask_app.route("/health", methods=["GET"])
    def health():
        return "OK", 200

    return flask_app


if __name__ == "__main__":
    flask_app = create_flask_app()
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
