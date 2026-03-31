"""Driveの最新請求書JSONをスプレッドシートに1件記録する一回限りのスクリプト。"""

import os
import sys
from datetime import datetime, timezone, timedelta

from src.drive_client import get_drive_service, load_monthly_invoice_data
from src.spreadsheet_client import get_sheets_service, ensure_monthly_sheet, append_invoice

JST = timezone(timedelta(hours=9))


def main():
    now = datetime.now(JST)
    year = now.year
    month = now.month

    print("📂 {}年{}月のDriveデータを読み込み中...".format(year, month))
    drive = get_drive_service()
    invoices = load_monthly_invoice_data(drive, year, month)

    if not invoices:
        # 先月も試す
        if month == 1:
            year -= 1
            month = 12
        else:
            month -= 1
        print("当月データなし。{}年{}月を確認中...".format(year, month))
        invoices = load_monthly_invoice_data(drive, year, month)

    if not invoices:
        print("請求書データが見つかりませんでした。")
        return

    # 最新1件を取得
    latest = invoices[-1]
    print("📋 最新の請求書: {} - ¥{}".format(
        latest.get("issuer", "不明"),
        latest.get("amount", "不明"),
    ))

    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not spreadsheet_id:
        print("SPREADSHEET_IDが未設定です。")
        sys.exit(1)

    sheets = get_sheets_service()
    email_date = latest.get("email_date", "")
    # 日付からyear/monthを判定
    sheet_name = ensure_monthly_sheet(sheets, spreadsheet_id, year, month)
    append_invoice(sheets, spreadsheet_id, sheet_name, latest)

    print("✅ スプレッドシートに記録しました。")


if __name__ == "__main__":
    main()
