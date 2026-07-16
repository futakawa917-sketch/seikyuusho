import base64
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("GMAIL_ADDRESS", "snshack.online@gmail.com")
os.environ.setdefault("GITHUB_REPO", "futakawa917-sketch/seikyuusho")
os.environ.setdefault("GITHUB_TOKEN", "test-token")

from app import app


def envelope(email="snshack.online@gmail.com", history_id="123"):
    payload = base64.urlsafe_b64encode(
        json.dumps({"emailAddress": email, "historyId": history_id}).encode()
    ).decode().rstrip("=")
    return {"message": {"data": payload, "messageId": "message-1"}}


class ReceiverTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("app.requests.post")
    def test_dispatches_valid_notification(self, post):
        post.return_value.status_code = 204

        response = self.client.post("/", json=envelope())

        self.assertEqual(response.status_code, 204)
        self.assertEqual(post.call_args.kwargs["json"]["event_type"], "new-invoice")
        self.assertNotIn("emailAddress", post.call_args.kwargs["json"]["client_payload"])

    @patch("app.requests.post")
    def test_rejects_unexpected_account(self, post):
        response = self.client.post("/", json=envelope(email="other@example.com"))

        self.assertEqual(response.status_code, 403)
        post.assert_not_called()

    @patch("app.requests.post")
    def test_retries_when_github_fails(self, post):
        post.return_value.status_code = 500

        response = self.client.post("/", json=envelope())

        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
