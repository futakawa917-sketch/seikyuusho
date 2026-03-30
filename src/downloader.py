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

        # HTMLが返ってきた場合はパスワードページかチェック
        if "text/html" in content_type:
            html = response.text
            if _is_password_page(html):
                return {"needs_password": True, "url": url, "html": html}
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
    needs_password = []

    for url in candidates:
        result = try_download_pdf(url)
        if result is None:
            url_lower = url.lower()
            if any(hint in url_lower for hint in PDF_HINTS):
                failed.append(url)
        elif isinstance(result, dict) and result.get("needs_password"):
            needs_password.append(result)
        elif isinstance(result, dict) and result.get("data"):
            downloaded.append(result)

    return downloaded, failed, needs_password


def try_download_with_password(page_info, password):
    """パスワード付きページからPDFダウンロードを試みる。

    Args:
        page_info: {"url": str, "html": str} パスワードページ情報
        password: パスワード文字列

    Returns:
        dict or None: 成功時は {"filename": str, "data": bytes}
    """
    import re as _re

    url = page_info["url"]
    html = page_info["html"]

    # formのaction URLとpasswordフィールド名を抽出
    form_action = _find_form_action(html, url)
    password_field = _find_password_field(html)

    if not form_action or not password_field:
        return None

    try:
        # セッション維持してPOST
        session = requests.Session()
        session.get(url, timeout=15)

        # hidden フィールドも含めて送信
        form_data = _extract_hidden_fields(html)
        form_data[password_field] = password

        response = session.post(form_action, data=form_data, timeout=30, allow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()

        if "application/pdf" in content_type:
            return {"filename": _extract_filename(response, form_action), "data": response.content}

        if "application/octet-stream" in content_type:
            data = response.content
            if data[:5] == b"%PDF-":
                return {"filename": _extract_filename(response, form_action), "data": data}

        # リダイレクト先にダウンロードリンクがある場合
        if "text/html" in content_type:
            new_urls = URL_PATTERN.findall(response.text)
            for new_url in new_urls:
                new_url = new_url.rstrip(".,;:)>]}")
                if any(hint in new_url.lower() for hint in PDF_HINTS):
                    result = try_download_pdf(new_url)
                    if isinstance(result, dict) and result.get("data"):
                        return result

        return None

    except Exception:
        return None


def _is_password_page(html):
    """HTMLがパスワード入力ページかどうかを判定する。"""
    html_lower = html.lower()
    has_password_input = 'type="password"' in html_lower or "type='password'" in html_lower
    has_password_text = any(w in html_lower for w in ["パスワード", "password", "暗証", "認証"])
    return has_password_input and has_password_text


def _find_form_action(html, base_url):
    """HTMLからformのaction URLを抽出する。"""
    import re as _re
    from urllib.parse import urljoin

    match = _re.search(r'<form[^>]*action=["\']([^"\']*)["\']', html, _re.IGNORECASE)
    if match:
        action = match.group(1)
        if action and not action.startswith("http"):
            action = urljoin(base_url, action)
        return action or base_url

    return base_url


def _find_password_field(html):
    """HTMLからパスワードinputフィールドのname属性を取得する。"""
    import re as _re

    match = _re.search(r'<input[^>]*type=["\']password["\'][^>]*name=["\']([^"\']+)["\']', html, _re.IGNORECASE)
    if match:
        return match.group(1)

    match = _re.search(r'<input[^>]*name=["\']([^"\']+)["\'][^>]*type=["\']password["\']', html, _re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def _extract_hidden_fields(html):
    """HTMLからhidden inputフィールドを全て抽出する。"""
    import re as _re
    fields = {}
    for match in _re.finditer(r'<input[^>]*type=["\']hidden["\'][^>]*>', html, _re.IGNORECASE):
        tag = match.group(0)
        name_match = _re.search(r'name=["\']([^"\']+)["\']', tag)
        value_match = _re.search(r'value=["\']([^"\']*)["\']', tag)
        if name_match:
            fields[name_match.group(1)] = value_match.group(1) if value_match else ""
    return fields


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
