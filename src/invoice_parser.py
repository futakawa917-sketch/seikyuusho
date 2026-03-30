import base64
import json
import os

import anthropic


def get_client():
    """Anthropicクライアントを返す。"""
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


EXTRACTION_PROMPT = """\
以下の請求書の内容から、次の情報をJSON形式で抽出してください。
情報が見つからない場合は null としてください。

抽出項目:
- issuer: 請求元（会社名・個人名）
- amount: 請求金額（数値、税込）
- bank_info: 振込先口座情報（銀行名・支店名・口座種別・口座番号・口座名義を含む文字列）
- due_date: 支払期限（YYYY-MM-DD形式）
- description: 請求内容の概要（1行）

JSON のみを返してください。マークダウンのコードブロックは不要です。
"""


def parse_pdf(pdf_data: bytes) -> dict:
    """PDFの請求書をClaude Vision APIで解析する。

    Args:
        pdf_data: PDFファイルのバイナリデータ

    Returns:
        dict: 抽出された請求書情報
    """
    client = get_client()
    pdf_b64 = base64.standard_b64encode(pdf_data).decode("utf-8")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    return _parse_response(response)


def parse_text(email_body: str, subject: str = "", sender: str = "") -> dict:
    """メール本文の請求書をClaude APIで解析する。

    Args:
        email_body: メール本文テキスト
        subject: メール件名
        sender: 送信者

    Returns:
        dict: 抽出された請求書情報
    """
    client = get_client()

    context = f"件名: {subject}\n送信者: {sender}\n\n本文:\n{email_body}"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"{EXTRACTION_PROMPT}\n\n---\n\n{context}",
            }
        ],
    )

    return _parse_response(response)


def _parse_response(response) -> dict:
    """Claude APIレスポンスからJSONを抽出する。"""
    text = response.content[0].text.strip()

    # コードブロックで囲まれている場合を処理
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result[0] if result else {}
        return result
    except json.JSONDecodeError:
        return {
            "issuer": None,
            "amount": None,
            "bank_info": None,
            "due_date": None,
            "description": None,
            "raw_response": text,
        }
