import io
import json
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    """Google Drive APIサービスを初期化して返す（OAuth リフレッシュトークン方式）。"""
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
    return build("drive", "v3", credentials=creds)


def get_or_create_folder(service, name, parent_id=None):
    """指定名のフォルダを取得。なければ作成する。

    Args:
        service: Drive APIサービス
        name: フォルダ名
        parent_id: 親フォルダID（Noneならルート）

    Returns:
        str: フォルダID
    """
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def ensure_monthly_folder(service, year, month):
    """「請求書/YYYY年/MM月」フォルダ構成を作成してフォルダIDを返す。

    Args:
        service: Drive APIサービス
        year: 年（int）
        month: 月（int）

    Returns:
        str: 月フォルダのID
    """
    root_id = os.environ.get("DRIVE_ROOT_FOLDER_ID")

    invoice_folder_id = get_or_create_folder(service, "請求書", root_id)
    year_folder_id = get_or_create_folder(service, f"{year}年", invoice_folder_id)
    month_folder_id = get_or_create_folder(service, f"{month:02d}月", year_folder_id)

    return month_folder_id


def upload_file(service, folder_id, filename, data, mime_type="application/pdf"):
    """ファイルをDriveにアップロードする。

    Args:
        service: Drive APIサービス
        folder_id: アップロード先フォルダID
        filename: ファイル名
        data: ファイルデータ（bytes）
        mime_type: MIMEタイプ

    Returns:
        str: アップロードされたファイルのID
    """
    metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)
    uploaded = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return uploaded["id"]


def upload_text_as_file(service, folder_id, filename, text):
    """テキストをファイルとしてDriveにアップロードする。

    Args:
        service: Drive APIサービス
        folder_id: アップロード先フォルダID
        filename: ファイル名
        text: テキスト内容

    Returns:
        str: アップロードされたファイルのID
    """
    return upload_file(service, folder_id, filename, text.encode("utf-8"), mime_type="text/plain")
