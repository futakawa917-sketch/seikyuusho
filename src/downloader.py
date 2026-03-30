"""メール本文からダウンロードリンクを抽出してPDFを取得する。"""

import re
from urllib.parse import urlparse

import requests


# ダウンロードリンクのパターン
URL_PATTERN = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)

# PDFの可能性が高い拡張子・パス
PDF_HINTS = [".pdf", "download", "invoice", "receipt", "請求", "seikyu"]

# ログイン必須と判定するパターン
LOGIN_INDICATORS = ["login", "signin", "sign-in", "auth", "password", "ログイン"]


def extract_download_urls(text):
    """メール本文からダウンロード可能なURLを抽出する。

    Args:
        text: メール本文

    Returns:
        list[str]: URL のリスト
    """
    urls = URL_PATTERN.findall(text)

    # 末尾の記号を除去
    cleaned = []
    for url in urls:
        url = url.rstrip(".,;:)>]}")
        cleaned.append(url)

    return cleaned


def try_download_pdf(url):
    """URLからPDFのダウンロードを試みる。

    Args:
        url: ダウンロードURL

    Returns:
        dict or None: 成功時は {"filename": str, "data": bytes}、失敗時はNone
    """
    try:
        response = requests.get(url, timeout=30, allow_redirects=True, stream=True)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()

        # レスポンスがPDFかチェック
        if "application/pdf" in content_type:
            data = response.content
            filename = _extract_filename(response, url)
            return {"filename": filename, "data": data}

        # HTMLが返ってきた場合はログインが必要な可能性
        if "text/html" in content_type:
            body = response.text[:2000].lower()
            if any(indicator in body for indicator in LOGIN_INDICATORS):
                return None
            return None

        # application/octet-stream でPDFの可能性
        if "application/octet-stream" in content_type:
            data = response.content
            if data[:5] == b"%PDF-":
                filename = _extract_filename(response, url)
                return {"filename": filename, "data": data}

        return None

    except Exception:
        return None


def find_and_download_pdfs(email_body):
    """メール本文からURLを抽出し、PDFダウンロードを試みる。

    Args:
        email_body: メール本文テキスト

    Returns:
        tuple: (downloaded_files, failed_urls)
            - downloaded_files: [{"filename": str, "data": bytes}, ...]
            - failed_urls: [str, ...] ダウンロードできなかったURL
    """
    urls = extract_download_urls(email_body)
    if not urls:
        return [], []

    # PDFの可能性が高いURLを優先
    pdf_likely = []
    other = []
    for url in urls:
        url_lower = url.lower()
        if any(hint in url_lower for hint in PDF_HINTS):
            pdf_likely.append(url)
        else:
            other.append(url)

    # 画像・CSS・JS・SNS等の明らかに関係ないURLを除外
    skip_patterns = [
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js",
        "twitter.com", "facebook.com", "instagram.com", "youtube.com",
        "google.com/maps", "unsubscribe", "mailto:",
        "googleapis.com", "gstatic.com",
    ]

    candidates = pdf_likely + other
    candidates = [
        url for url in candidates
        if not any(skip in url.lower() for skip in skip_patterns)
    ]

    downloaded = []
    failed = []

    for url in candidates:
        result = try_download_pdf(url)
        if result:
            downloaded.append(result)
        else:
            # PDFの可能性が高いURLでダウンロードできなかった場合のみ報告
            url_lower = url.lower()
            if any(hint in url_lower for hint in PDF_HINTS):
                failed.append(url)

    return downloaded, failed


def _extract_filename(response, url):
    """レスポンスヘッダーまたはURLからファイル名を取得する。"""
    # Content-Dispositionからファイル名を取得
    cd = response.headers.get("Content-Disposition", "")
    if "filename" in cd:
        parts = cd.split("filename=")
        if len(parts) > 1:
            name = parts[1].strip().strip('"').strip("'")
            if name:
                return name

    # URLパスからファイル名を取得
    path = urlparse(url).path
    name = path.split("/")[-1]
    if name and "." in name:
        return name

    return "downloaded_invoice.pdf"
