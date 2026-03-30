import os

import requests


LINE_MESSAGING_API_URL = "https://api.line.me/v2/bot/message/broadcast"


def send_notification(message: str):
    """LINE Messaging APIでメッセージをブロードキャスト送信する。

    友だち追加している全ユーザーに送信される。

    Args:
        message: 送信するメッセージ（最大5000文字）
    """
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Messaging APIの1メッセージ最大5000文字に対応
    if len(message) > 5000:
        chunks = _split_message(message, 5000)
    else:
        chunks = [message]

    for chunk in chunks:
        payload = {
            "messages": [
                {
                    "type": "text",
                    "text": chunk,
                }
            ]
        }
        requests.post(LINE_MESSAGING_API_URL, headers=headers, json=payload)


def format_invoice_summary(invoices):
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
        return "請求書の新着はありませんでした。"

    lines = ["📋 請求書サマリー（{}件）\n".format(len(invoices))]

    for i, inv in enumerate(invoices, 1):
        issuer = inv.get("issuer") or "不明"
        amount = inv.get("amount")
        due_date = inv.get("due_date") or "未記載"
        bank_info = inv.get("bank_info") or "未記載"
        description = inv.get("description") or ""

        amount_str = "¥{:,.0f}".format(amount) if amount else "未記載"

        lines.append("{}. {}".format(i, issuer))
        lines.append("   金額: {}".format(amount_str))
        lines.append("   期限: {}".format(due_date))
        lines.append("   口座: {}".format(bank_info))
        if description:
            lines.append("   内容: {}".format(description))
        lines.append("")

    return "\n".join(lines)


def _split_message(message, max_length):
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
