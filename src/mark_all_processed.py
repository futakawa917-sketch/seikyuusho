"""既存メール全てに処理済みラベルを付与する一回限りのスクリプト。"""

from src.gmail_client import get_gmail_service, get_processed_label_id


def main():
    service = get_gmail_service()
    label_id = get_processed_label_id(service)

    query = "-label:請求書処理済み"
    processed = 0

    while True:
        results = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
        messages = results.get("messages", [])

        if not messages:
            break

        for msg in messages:
            service.users().messages().modify(
                userId="me",
                id=msg["id"],
                body={"addLabelIds": [label_id]},
            ).execute()
            processed += 1

        print("{}件処理済み...".format(processed))

    print("完了: 合計{}件に処理済みラベルを付与しました。".format(processed))


if __name__ == "__main__":
    main()
