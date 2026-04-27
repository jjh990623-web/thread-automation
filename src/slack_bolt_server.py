"""Slack Bolt 서버 — 버튼 클릭 처리."""

import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from .main import cmd_approve
from .storage import DraftStorage


app = App(token=os.getenv("SLACK_BOT_TOKEN"), signing_secret=os.getenv("SLACK_SIGNING_SECRET"))


@app.action("approve_draft")
def handle_approve_button(ack, body, client, logger):
    """수정/게시 버튼 클릭 → 본문 편집 모달 오픈."""
    ack()
    draft_id = body["actions"][0]["value"]
    trigger_id = body["trigger_id"]
    logger.info(f"approve_draft 클릭됨: {draft_id}")

    storage = DraftStorage()
    draft = storage.get_pending(draft_id)
    if draft is None:
        logger.error(f"pending에 {draft_id} 없음")
        return

    try:
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "approve_modal",
                "private_metadata": draft_id,
                "title": {"type": "plain_text", "text": "초안 검토/게시"},
                "submit": {"type": "plain_text", "text": "게시"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "text_block",
                        "label": {"type": "plain_text", "text": "본문 (수정 가능)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "edited_text",
                            "multiline": True,
                            "initial_value": draft.text,
                        },
                    }
                ],
            },
        )
    except Exception as e:
        import traceback
        logger.error(f"모달 오픈 실패: {e}")
        logger.error(traceback.format_exc())


@app.view("approve_modal")
def handle_approve_submission(ack, view, logger):
    """모달 제출 → 수정된 본문으로 게시."""
    ack()
    draft_id = view["private_metadata"]
    edited_text = view["state"]["values"]["text_block"]["edited_text"]["value"]
    logger.info(f"approve_modal 제출됨: {draft_id}")

    try:
        from argparse import Namespace
        args = Namespace(draft_id=draft_id, edited_text=edited_text)
        result = cmd_approve(args)
        if result == 0:
            logger.info(f"✅ 게시 완료: {draft_id}")
        else:
            logger.error(f"❌ 게시 실패 (code={result}): {draft_id}")
    except Exception as e:
        import traceback
        logger.error(f"❌ 에러 발생: {e}")
        logger.error(traceback.format_exc())


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
