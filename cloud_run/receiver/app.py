import base64
import json
import os

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/")
def receive_gmail_notification():
    envelope = request.get_json(silent=True)
    if not envelope or not isinstance(envelope.get("message"), dict):
        return jsonify({"error": "invalid Pub/Sub envelope"}), 400

    message = envelope["message"]
    encoded_data = message.get("data")
    if not encoded_data:
        return jsonify({"error": "missing Pub/Sub message data"}), 400

    try:
        padding = "=" * (-len(encoded_data) % 4)
        notification = json.loads(base64.urlsafe_b64decode(encoded_data + padding))
    except (ValueError, json.JSONDecodeError):
        return jsonify({"error": "invalid Gmail notification data"}), 400

    expected_email = os.environ["GMAIL_ADDRESS"].lower()
    notified_email = str(notification.get("emailAddress", "")).lower()
    if notified_email != expected_email:
        return jsonify({"error": "unexpected Gmail account"}), 403

    response = requests.post(
        "https://api.github.com/repos/{}/dispatches".format(os.environ["GITHUB_REPO"]),
        headers={
            "Authorization": "Bearer {}".format(os.environ["GITHUB_TOKEN"]),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "event_type": "new-invoice",
            "client_payload": {
                "gmail_history_id": str(notification.get("historyId", "")),
                "pubsub_message_id": str(message.get("messageId", "")),
            },
        },
        timeout=15,
    )

    if response.status_code != 204:
        # 5xxを返すことでPub/Subに再配信させる。
        return jsonify({"error": "GitHub dispatch failed", "status": response.status_code}), 502

    return "", 204
