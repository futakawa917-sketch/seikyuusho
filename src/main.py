"""請求書自動管理ツール

Gmailから請求書メールを取得し、Google Driveに月別保存、
Claude APIで内容を解析し、LINE Notifyで支払いサマリーを通知する。
"""

import sys

from src.gmail_client import get_gmail_service, fetch_invoice_emails, mark_as_processed
from src.drive_client import get_drive_service, ensure_monthly_folder, upload_file, upload_text_as_file
from src.invoice_parser import parse_pdf, parse_text
from src.line_notifier import send_notification, format_invoice_summary


def process_invoices():
    """メイン処理: メール取得 → Drive保存 → 解析 → LINE通知"""
    print("📧 Gmailから請求書メールを取得中...")
    gmail = get_gmail_service()
    emails = fetch_invoice_emails(gmail)

    if not emails:
        print("新着の請求書メールはありません。")
        send_notification("\n請求書の新着はありませんでした。")
        return

    print(f"📨 {len(emails)}件の請求書メールを検出")

    drive = get_drive_service()
    parsed_invoices = []

    for email in emails:
        print(f"  処理中: {email['subject']} ({email['sender']})")

        year = email["date"].year
        month = email["date"].month
        folder_id = ensure_monthly_folder(drive, year, month)

        invoice_data = None

        # PDF添付ファイルがある場合
        if email["attachments"]:
            for attachment in email["attachments"]:
                print(f"    📎 PDF保存: {attachment['filename']}")
                upload_file(drive, folder_id, attachment["filename"], attachment["data"])

                # 最初のPDFで解析
                if invoice_data is None:
                    print(f"    🔍 PDF解析中...")
                    invoice_data = parse_pdf(attachment["data"])

        # PDF添付がない場合はメール本文で解析
        if invoice_data is None and email["body"]:
            print(f"    🔍 メール本文を解析中...")
            invoice_data = parse_text(email["body"], email["subject"], email["sender"])

            # 本文をテキストファイルとしても保存
            safe_subject = email["subject"].replace("/", "_").replace("\\", "_")
            filename = f"{safe_subject}.txt"
            content = f"件名: {email['subject']}\n送信者: {email['sender']}\n日付: {email['date']}\n\n{email['body']}"
            upload_text_as_file(drive, folder_id, filename, content)

        if invoice_data:
            invoice_data["email_subject"] = email["subject"]
            invoice_data["email_sender"] = email["sender"]
            invoice_data["email_date"] = str(email["date"])
            parsed_invoices.append(invoice_data)

        # 処理済みラベルを付与
        mark_as_processed(gmail, email["message_id"])
        print(f"    ✅ 処理完了")

    # LINE通知
    print(f"\n📱 LINE通知を送信中...")
    message = format_invoice_summary(parsed_invoices)
    send_notification(message)
    print("✅ 全処理が完了しました。")

    # 解析結果を表示
    for inv in parsed_invoices:
        issuer = inv.get("issuer") or "不明"
        amount = inv.get("amount")
        amount_str = f"¥{amount:,.0f}" if amount else "未記載"
        print(f"  - {issuer}: {amount_str}")


if __name__ == "__main__":
    try:
        process_invoices()
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}", file=sys.stderr)
        send_notification(f"\n⚠️ 請求書処理でエラーが発生しました:\n{e}")
        sys.exit(1)
