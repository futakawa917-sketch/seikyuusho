"""Googleスプレッドシートに請求書データを記録・管理する。"""

import json
import os
from datetime import datetime, timezone, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
JST = timezone(timedelta(hours=9))

# スプレッドシートのヘッダー行
HEADERS = [
    "受信日", "請求元", "金額", "支払期限", "振込先口座",
    "内容", "メール件名", "送信者", "支払済み", "備考",
]


def get_sheets_service():
    """Google Sheets APIサービスを初期化して返す。"""
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
    return build("sheets", "v4", credentials=creds)


def ensure_spreadsheet(service):
    """請求書管理スプレッドシートのIDを取得する。

    環境変数 SPREADSHEET_ID が設定されていればそれを使用。

    Returns:
        str: スプレッドシートID
    """
    return os.environ.get("SPREADSHEET_ID", "")


def ensure_monthly_sheet(service, spreadsheet_id, year, month):
    """月別シートを確認し、なければ作成する。

    Args:
        service: Sheets APIサービス
        spreadsheet_id: スプレッドシートID
        year: 年
        month: 月

    Returns:
        str: シート名
    """
    sheet_name = "{}年{:02d}月".format(year, month)

    # 既存シート一覧を取得
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_sheets = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]

    if sheet_name not in existing_sheets:
        # シート追加
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [{
                    "addSheet": {
                        "properties": {"title": sheet_name}
                    }
                }]
            },
        ).execute()

        # ヘッダー行を書き込み
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="{}!A1:J1".format(sheet_name),
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()

    return sheet_name


def append_invoice(service, spreadsheet_id, sheet_name, invoice_data):
    """請求書データをスプレッドシートに追記する。

    Args:
        service: Sheets APIサービス
        spreadsheet_id: スプレッドシートID
        sheet_name: シート名
        invoice_data: 解析済み請求書データ
    """
    amount = invoice_data.get("amount")
    amount_str = str(int(amount)) if amount else ""

    row = [
        invoice_data.get("email_date", ""),
        invoice_data.get("issuer") or "不明",
        amount_str,
        invoice_data.get("due_date") or "",
        invoice_data.get("bank_info") or "",
        invoice_data.get("description") or "",
        invoice_data.get("email_subject") or "",
        invoice_data.get("email_sender") or "",
        "",  # 支払済み（空欄）
        invoice_data.get("manual_download") or "",
    ]

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="{}!A:J".format(sheet_name),
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


def get_upcoming_due_invoices(service, spreadsheet_id, days_ahead=3):
    """支払期限が近い未払い請求書を取得する。

    Args:
        service: Sheets APIサービス
        spreadsheet_id: スプレッドシートID
        days_ahead: 何日先までをチェックするか

    Returns:
        list[dict]: 期限が近い請求書リスト
    """
    now = datetime.now(JST)
    target_date = now + timedelta(days=days_ahead)

    # 当月と来月のシートをチェック
    sheets_to_check = [
        "{}年{:02d}月".format(now.year, now.month),
    ]
    # 月末近い場合は来月もチェック
    if now.day >= 25:
        next_month = now.month + 1
        next_year = now.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        sheets_to_check.append("{}年{:02d}月".format(next_year, next_month))

    upcoming = []

    for sheet_name in sheets_to_check:
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="{}!A:J".format(sheet_name),
            ).execute()
        except Exception:
            continue

        rows = result.get("values", [])
        if len(rows) <= 1:
            continue

        for row in rows[1:]:  # ヘッダーをスキップ
            if len(row) < 9:
                row.extend([""] * (9 - len(row)))

            due_date_str = row[3]  # 支払期限
            paid = row[8]  # 支払済み

            # 支払済みならスキップ
            if paid and paid.strip():
                continue

            if not due_date_str:
                continue

            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").replace(tzinfo=JST)
            except ValueError:
                continue

            # 期限が今日〜days_ahead日後の範囲内
            if now.date() <= due_date.date() <= target_date.date():
                days_left = (due_date.date() - now.date()).days
                upcoming.append({
                    "issuer": row[1],
                    "amount": row[2],
                    "due_date": due_date_str,
                    "bank_info": row[4],
                    "days_left": days_left,
                })

    # 期限が近い順にソート
    upcoming.sort(key=lambda x: x["due_date"])
    return upcoming
