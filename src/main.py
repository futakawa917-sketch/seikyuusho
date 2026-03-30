"""請求書自動管理ツール

3つのモードで動作:
- process: 新着メールを処理してLINEに即時通知 + スプレッドシート記録
- summary: 当月の請求書をまとめてLINEに月末サマリー送信
- reminder: 支払い期限が近い請求書をLINEでリマインド
"""

import calendar
import os
import sys
from datetime import datetime, timezone, timedelta

from src.gmail_client import get_gmail_service, fetch_invoice_emails, mark_as_processed, find_password_from_sender, _extract_email_address
from src.drive_client import (
    get_drive_service, ensure_monthly_folder, upload_file,
    save_invoice_data, load_monthly_invoice_data,
)
from src.invoice_parser import parse_pdf, parse_text
from src.line_notifier import send_notification, format_invoice_summary, format_monthly_summary
from src.downloader import find_and_download_pdfs, try_download_with_password

JST = timezone(timedelta(hours=9))


def _get_sheets_service_if_available():
    """スプレッドシートIDが設定されている場合のみSheets APIを初期化。"""
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        return None, None
    from src.spreadsheet_client import get_sheets_service, ensure_monthly_sheet
    return get_sheets_service(), spreadsheet_id


def process_invoices():
    """新着メール処理: メール取得 → Drive保存 → 解析 → スプレッドシート記録 → LINE即時通知"""
    print("📧 Gmailから請求書メールを取得中...")
    gmail = get_gmail_service()
    emails = fetch_invoice_emails(gmail)

    if not emails:
        print("新着の請求書メールはありません。")
        return

    print("📨 {}件の請求書メールを検出".format(len(emails)))

    drive = get_drive_service()
    sheets, spreadsheet_id = _get_sheets_service_if_available()
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

                if invoice_data is None:
                    print("    🔍 PDF解析中...")
                    invoice_data = parse_pdf(attachment["data"])

        # PDF添付がない場合、メール本文のリンクからPDFダウンロードを試みる
        failed_urls = []
        if not email["attachments"] and email["body"]:
            print("    🔗 ダウンロードリンクを探索中...")
            downloaded, failed_urls, needs_password = find_and_download_pdfs(email["body"])

            if needs_password:
                sender_addr = _extract_email_address(email["sender"])
                print("    🔑 パスワードを同じ送信元のメールから探索中...")
                password = find_password_from_sender(gmail, sender_addr)

                if password:
                    print("    🔑 パスワード発見、ダウンロード試行中...")
                    for page_info in needs_password:
                        result = try_download_with_password(page_info, password)
                        if result:
                            downloaded.append(result)
                            print("    📎 パスワード認証でPDF取得成功: {}".format(result["filename"]))
                        else:
                            failed_urls.append(page_info["url"])
                else:
                    print("    ⚠️ パスワードが見つかりませんでした")
                    for page_info in needs_password:
                        failed_urls.append(page_info["url"])

            for dl_file in downloaded:
                print("    📎 リンクからPDF保存: {}".format(dl_file["filename"]))
                upload_file(drive, folder_id, dl_file["filename"], dl_file["data"])

                if invoice_data is None:
                    print("    🔍 PDF解析中...")
                    invoice_data = parse_pdf(dl_file["data"])

        # それでも解析できない場合はメール本文で解析
        if invoice_data is None and email["body"]:
            print("    🔍 メール本文を解析中...")
            invoice_data = parse_text(email["body"], email["subject"], email["sender"])

        if invoice_data and failed_urls:
            invoice_data["manual_download"] = "手動DL必要: " + ", ".join(failed_urls[:2])

        if invoice_data:
            invoice_data["email_subject"] = email["subject"]
            invoice_data["email_sender"] = email["sender"]
            invoice_data["email_date"] = str(email["date"])
            parsed_invoices.append(invoice_data)

            # DriveにJSON保存
            save_invoice_data(drive, folder_id, invoice_data)

            # スプレッドシートに記録
            if sheets and spreadsheet_id:
                from src.spreadsheet_client import ensure_monthly_sheet, append_invoice
                sheet_name = ensure_monthly_sheet(sheets, spreadsheet_id, year, month)
                append_invoice(sheets, spreadsheet_id, sheet_name, invoice_data)
                print("    📊 スプレッドシートに記録")

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
    now = datetime.now(JST)
    year = now.year
    month = now.month

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


def send_reminder():
    """支払い期限リマインダー: 期限3日以内の未払い請求書をLINE通知"""
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        print("SPREADSHEET_IDが未設定のため、リマインダーをスキップします。")
        return

    from src.spreadsheet_client import get_sheets_service, get_upcoming_due_invoices

    print("⏰ 支払い期限チェック中...")
    sheets = get_sheets_service()
    upcoming = get_upcoming_due_invoices(sheets, spreadsheet_id, days_ahead=3)

    if not upcoming:
        print("期限が近い請求書はありません。")
        return

    print("📋 {}件の期限間近の請求書を検出".format(len(upcoming)))

    lines = ["⏰ 支払い期限リマインダー\n"]

    for inv in upcoming:
        if inv["days_left"] == 0:
            urgency = "🔴 今日が期限！"
        elif inv["days_left"] == 1:
            urgency = "🟠 明日が期限"
        elif inv["days_left"] == 2:
            urgency = "🟡 明後日が期限"
        else:
            urgency = "📅 {}日後が期限".format(inv["days_left"])

        amount_str = "¥{}".format(inv["amount"]) if inv["amount"] else "未記載"

        lines.append("{} {}".format(urgency, inv["issuer"]))
        lines.append("   金額: {}".format(amount_str))
        lines.append("   期限: {}".format(inv["due_date"]))
        if inv["bank_info"]:
            lines.append("   口座: {}".format(inv["bank_info"]))
        lines.append("")

    message = "\n".join(lines)
    send_notification(message)

    print("✅ リマインダーを送信しました。")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "process"

    try:
        if mode == "summary":
            send_monthly_summary()
        elif mode == "reminder":
            send_reminder()
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
