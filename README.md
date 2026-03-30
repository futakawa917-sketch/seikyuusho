# 請求書自動管理ツール

Gmailに届く請求書を自動で処理するツール。

## 機能

1. **Gmail取得** - 請求書専用アドレスのメールを自動取得
2. **Drive保存** - `請求書/YYYY年/MM月/` フォルダに自動整理
3. **内容解析** - Claude APIで請求元・金額・口座・期限を抽出
4. **LINE通知** - 支払いサマリーをLINE Notifyで通知

## セットアップ

### 1. Google Cloud 設定

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクト作成
2. Gmail API と Google Drive API を有効化
3. サービスアカウントを作成し、JSONキーをダウンロード
4. Google Workspace管理コンソールで、サービスアカウントにドメイン全体の委任を設定
   - スコープ: `https://www.googleapis.com/auth/gmail.readonly`, `https://www.googleapis.com/auth/gmail.modify`, `https://www.googleapis.com/auth/drive.file`

### 2. LINE Notify 設定

1. [LINE Notify](https://notify-bot.line.me/) にログイン
2. トークンを発行（通知先グループまたは1:1を選択）

### 3. GitHub Secrets 設定

リポジトリの Settings > Secrets and variables > Actions に以下を追加:

| Secret名 | 内容 |
|-----------|------|
| `GOOGLE_CREDENTIALS` | サービスアカウントのJSON（1行に整形） |
| `GMAIL_USER_EMAIL` | 請求書専用Gmailアドレス |
| `ANTHROPIC_API_KEY` | Claude APIキー |
| `LINE_NOTIFY_TOKEN` | LINE Notifyトークン |
| `DRIVE_ROOT_FOLDER_ID` | Drive保存先フォルダID（省略可） |

### 4. 実行

- **自動実行**: 毎日朝9時（JST）にGitHub Actionsで自動実行
- **手動実行**: Actions タブから "Run workflow" で手動実行

### ローカル実行

```bash
pip install -r requirements.txt
cp .env.example .env
# .env に認証情報を記入
python -m src.main
```
