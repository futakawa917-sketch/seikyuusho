"""OAuthリフレッシュトークンを取得するセットアップスクリプト。

初回のみローカルで実行し、取得したトークン情報をGitHub Secretsに設定する。

使い方:
  1. Google Cloud Console で OAuth 2.0 クライアントID（デスクトップアプリ）を作成
  2. client_secret_xxxxx.json をダウンロードしてこのスクリプトと同じディレクトリに配置
  3. python setup_oauth.py を実行
  4. ブラウザで認証を完了
  5. 表示されたJSONをGitHub SecretsのGOOGLE_OAUTH_TOKENに設定
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.file",
]


def main():
    # client_secret ファイルを探す
    secret_files = list(Path(".").glob("client_secret*.json"))
    if not secret_files:
        print("❌ client_secret_xxxxx.json が見つかりません。")
        print("   Google Cloud Console → 認証情報 → OAuth 2.0 クライアントID で作成し、")
        print("   JSONをダウンロードしてこのディレクトリに配置してください。")
        sys.exit(1)

    secret_file = secret_files[0]
    print(f"📄 認証ファイル: {secret_file}")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), scopes=SCOPES)
    creds = flow.run_local_server(port=0)

    # client_id と client_secret を取得
    with open(secret_file) as f:
        client_config = json.load(f)
    installed = client_config.get("installed", client_config.get("web", {}))

    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "client_id": installed["client_id"],
        "client_secret": installed["client_secret"],
    }

    token_json = json.dumps(token_data, ensure_ascii=False)

    print("\n✅ 認証成功！")
    print("\n以下のJSONをGitHub SecretsのGOOGLE_OAUTH_TOKENに設定してください：")
    print("=" * 60)
    print(token_json)
    print("=" * 60)


if __name__ == "__main__":
    main()
