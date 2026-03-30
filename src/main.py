"""請求書自動管理ツール

2つのモードで動作:
- process: 新着メールを処理してLINEに即時通知
- summary: 当月の請求書をまとめてLINEに月末サマリー送信
"""

import calendar
import sys
from datetime import datetime, timezone

from src.gmail_client import get_gmail_service, fetch_invoice_emails, mark_as_processed
from src.drive_client import (
    get_drive_service, ensure_monthly_folder, upload_file, upload_text_as_file,
    save_invoice_data, load_monthly_invoice_data,
)
from src.invoice_parser import parse_pdf, parse_text
from src.line_notifier import send_notification, format_invoice_summary, format_monthly_summary


def process_invoices():
    """新着メール処理: メール取得 → Drive保存 → 解析 → JSON保存 → LINE即時通知"""
    print("📧 Gmailから請求書メールを取得中...")
    gmail = get_gmail_service()
    emails = fetch_invoice_emails(gmail)

    if not emails:
        print("新着の請求書メールはありません。")
        return

    print("📨 {}件の請求書メールを検出".format(len(emails)))

    drive = get_drive_service()
    parsed_invoices = []

    for email in emails:
        print("  処理中: {} ({})".format(email["subject"], email["sender"]))

        year = email["date"].year
        month = email["date"].month
        folder_id = ensure_monthly_folder(drive, year, month)

        invoice_data = None

        # PDF添付ファイルがある場合
        if email["attachments"]:
            for attachment in email["attachments"]:
                print("    📎 PDF保存: {}".format(attachment["filename"]))
                upload_file(drive, folder_id, attachment["filename"], attachment["data"])

                # 最初のPDFで解析
                if invoice_data is None:
                    print("    🔍 PDF解析中...")
                    invoice_data = parse_pdf(attachment["data"])

        # PDF添付がない場合はメール本文で解析
        if invoice_data is None and email["body"]:
            print("    🔍 メール本文を解析中...")
            invoice_data = parse_text(email["body"], email["subject"], email["sender"])

            # 本文をテキストファイルとしても保存
            safe_subject = email["subject"].replace("/", "_").replace("\\", "_")
            filename = "{}.txt".format(safe_subject)
            content = "件名: {}\n送信者: {}\n日付: {}\n\n{}".format(
                email["subject"], email["sender"], email["date"], email["body"]
            )
            upload_text_as_file(drive, folder_id, filename, content)

        if invoice_data:
            invoice_data["email_subject"] = email["subject"]
            invoice_data["email_sender"] = email["sender"]
            invoice_data["email_date"] = str(email["date"])
            parsed_invoices.append(invoice_data)

            # 解析結果をJSONとしてDriveに保存（月末サマリー用）
            save_invoice_data(drive, folder_id, invoice_data)

        # 処理済みラベルを付与
        mark_as_processed(gmail, email["message_id"])
        print("    ✅ 処理完了")

    # LINE即時通知
    if parsed_invoices:
        print("\n📱 LINE通知を送信中...")
        message = format_invoice_summary(parsed_invoices)
        send_notification(message)

    print("✅ 全処理が完了しました。")


def send_monthly_summary():
    """月末サマリー: DriveからJSON読み込み → まとめてLINE送信"""
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month

    # 月末日かチェック（月末以外でも手動実行は許可）
    last_day = calendar.monthrange(year, month)[1]
    if now.day != last_day:
        print("今日は{}月{}日です（月末は{}日）。手動実行として続行します。".format(month, now.day, last_day))

    print("📊 {}年{}月の請求書サマリーを作成中...".format(year, month))

    drive = get_drive_service()
    invoices = load_monthly_invoice_data(drive, year, month)

    print("📋 {}件の請求書データを読み込みました".format(len(invoices)))

    message = format_monthly_summary(invoices, year, month)
    send_notification(message)

    print("✅ 月末サマリーを送信しました。")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "process"

    try:
        if mode == "summary":
            send_monthly_summary()
        else:
            process_invoices()
    except Exception as e:
        print("❌ エラーが発生しました: {}".format(e), file=sys.stderr)
        import traceback
        traceback.print_exc()
        try:
            send_notification("⚠️ 請求書処理でエラーが発生しました:\n{}".format(e))
        except Exception:
            pass
        sys.exit(1)
