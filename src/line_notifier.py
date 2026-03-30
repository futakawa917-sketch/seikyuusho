import os

import requests


LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"


def send_notification(message: str):
    """LINE Notifyでメッセージを送信する。

    Args:
        message: 送信するメッセージ（最大1000文字）
    """
    token = os.environ["LINE_NOTIFY_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}

    # LINE Notifyの文字数制限（1000文字）に対応
    if len(message) > 1000:
        chunks = _split_message(message, 1000)
        for chunk in chunks:
            requests.post(LINE_NOTIFY_URL, headers=headers, data={"message": chunk})
    else:
        requests.post(LINE_NOTIFY_URL, headers=headers, data={"message": message})


def format_invoice_summary(invoices: list[dict]) -> str:
    """請求書情報リストをLINE通知用のメッセージにフォーマットする。

    Args:
        invoices: 請求書情報のリスト。各dictは以下のキーを持つ:
            - issuer: 請求元
            - amount: 金額
            - due_date: 支払期限
            - bank_info: 振込先
            - description: 概要

    Returns:
        str: フォーマット済みメッセージ
    """
    if not invoices:
        return "\n請求書の新着はありませんでした。"

    lines = [f"\n📋 請求書サマリー（{len(invoices)}件）\n"]

    for i, inv in enumerate(invoices, 1):
        issuer = inv.get("issuer") or "不明"
        amount = inv.get("amount")
        due_date = inv.get("due_date") or "未記載"
        bank_info = inv.get("bank_info") or "未記載"
        description = inv.get("description") or ""

        amount_str = f"¥{amount:,.0f}" if amount else "未記載"

        lines.append(f"{i}. {issuer}")
        lines.append(f"   金額: {amount_str}")
        lines.append(f"   期限: {due_date}")
        lines.append(f"   口座: {bank_info}")
        if description:
            lines.append(f"   内容: {description}")
        lines.append("")

    return "\n".join(lines)


def _split_message(message: str, max_length: int) -> list[str]:
    """メッセージを指定文字数で分割する。"""
    chunks = []
    while message:
        if len(message) <= max_length:
            chunks.append(message)
            break
        split_pos = message.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        chunks.append(message[:split_pos])
        message = message[split_pos:].lstrip("\n")
    return chunks
