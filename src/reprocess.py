"""特定の送信元のメールの処理済みラベルを外して再処理可能にする。"""

import sys
from src.gmail_client import get_gmail_service, get_processed_label_id


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""
    if not keyword:
        print("使い方: python -m src.reprocess <検索キーワード>")
        sys.exit(1)

    service = get_gmail_service()
    label_id = get_processed_label_id(service)

    query = "label:請求書処理済み {}".format(keyword)
    results = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
    messages = results.get("messages", [])

    if not messages:
        print("該当するメールが見つかりませんでした。")
        return

    for msg_meta in messages:
        msg = service.users().messages().get(userId="me", id=msg_meta["id"], format="metadata").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        print("  ラベル解除: {} ({})".format(subject, sender))

        service.users().messages().modify(
            userId="me",
            id=msg_meta["id"],
            body={"removeLabelIds": [label_id]},
        ).execute()

    print("✅ {}件のラベルを解除しました。".format(len(messages)))


if __name__ == "__main__":
    main()
