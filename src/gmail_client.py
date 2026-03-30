import base64
import json
import os
from email.utils import parsedate_to_datetime

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


def get_gmail_service():
    """Gmail APIサービスを初期化して返す（OAuth リフレッシュトークン方式）。"""
    token_data = json.loads(os.environ["GOOGLE_OAUTH_TOKEN"])
    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=SCOPES,
    )
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def get_processed_label_id(service, user_id="me"):
    """「処理済み」ラベルのIDを取得。なければ作成する。"""
    labels = service.users().labels().list(userId=user_id).execute()
    for label in labels.get("labels", []):
        if label["name"] == "請求書処理済み":
            return label["id"]

    created = service.users().labels().create(
        userId=user_id,
        body={"name": "請求書処理済み", "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    ).execute()
    return created["id"]


def fetch_invoice_emails(service, user_id="me"):
    """未処理の請求書メールを取得する。

    Returns:
        list[dict]: メール情報のリスト。各dictは以下のキーを持つ:
            - message_id: メッセージID
            - subject: 件名
            - sender: 送信者
            - date: 受信日時
            - body: メール本文
            - attachments: 添付ファイルリスト [{filename, data}]
    """
    query = "-label:請求書処理済み -from:@google.com -from:@accounts.google.com -from:noreply -category:promotions -category:social"
    results = service.users().messages().list(userId=user_id, q=query, maxResults=20).execute()
    messages = results.get("messages", [])

    emails = []
    for msg_meta in messages:
        msg = service.users().messages().get(
            userId=user_id, id=msg_meta["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "（件名なし）")
        sender = headers.get("From", "（不明）")
        date_str = headers.get("Date", "")

        try:
            date = parsedate_to_datetime(date_str)
        except Exception:
            from datetime import datetime, timezone
            date = datetime.now(timezone.utc)

        body = _extract_body(msg["payload"])
        attachments = _extract_attachments(service, user_id, msg_meta["id"], msg["payload"])

        emails.append({
            "message_id": msg_meta["id"],
            "subject": subject,
            "sender": sender,
            "date": date,
            "body": body,
            "attachments": attachments,
        })

    return emails


def mark_as_processed(service, message_id, user_id="me"):
    """メールに「請求書処理済み」ラベルを付与する。"""
    label_id = get_processed_label_id(service, user_id)
    service.users().messages().modify(
        userId=user_id,
        id=message_id,
        body={"addLabelIds": [label_id]},
    ).execute()


def _extract_body(payload):
    """メールペイロードから本文テキストを抽出する。"""
    if payload.get("mimeType", "").startswith("text/plain"):
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if part.get("parts"):
            result = _extract_body(part)
            if result:
                return result

    # text/plain がなければ text/html を試す
    for part in parts:
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return ""


def _extract_attachments(service, user_id, message_id, payload):
    """PDF添付ファイルを抽出する。"""
    attachments = []
    parts = payload.get("parts", [])

    for part in parts:
        filename = part.get("filename", "")
        if not filename:
            continue

        if not filename.lower().endswith(".pdf"):
            continue

        attachment_id = part.get("body", {}).get("attachmentId")
        if not attachment_id:
            continue

        attachment = service.users().messages().attachments().get(
            userId=user_id, messageId=message_id, id=attachment_id
        ).execute()

        data = base64.urlsafe_b64decode(attachment["data"])
        attachments.append({"filename": filename, "data": data})

    return attachments
