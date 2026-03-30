/**
 * 請求書メール検知 → GitHub Actions トリガー
 *
 * セットアップ手順:
 * 1. https://script.google.com/ で新規プロジェクト作成
 * 2. このコードを貼り付け
 * 3. プロジェクトの設定 → スクリプトプロパティに以下を追加:
 *    - GITHUB_TOKEN: GitHubのPersonal Access Token（repoスコープ）
 *    - GITHUB_REPO: futakawa917-sketch/seikyuusho
 * 4. トリガーを設定:
 *    - 関数: checkNewInvoices
 *    - イベントソース: 時間主導型
 *    - 時間ベースのトリガー: 分ベースのタイマー
 *    - 間隔: 5分おき
 */

function checkNewInvoices() {
  // 未読メールを検索（請求書専用アドレスなので全メールが対象）
  var threads = GmailApp.search("is:unread", 0, 10);

  if (threads.length === 0) {
    return; // 新着なし
  }

  // GitHub Actions をトリガー
  triggerGitHubAction();

  // メールを既読にする（重複トリガー防止）
  for (var i = 0; i < threads.length; i++) {
    threads[i].markRead();
  }

  Logger.log(threads.length + "件の新着メールを検知し、GitHub Actionsをトリガーしました。");
}


function triggerGitHubAction() {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty("GITHUB_TOKEN");
  var repo = props.getProperty("GITHUB_REPO");

  var url = "https://api.github.com/repos/" + repo + "/dispatches";

  var options = {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/vnd.github.v3+json",
    },
    payload: JSON.stringify({
      event_type: "new-invoice",
    }),
    muteHttpExceptions: true,
  };

  var response = UrlFetchApp.fetch(url, options);
  Logger.log("GitHub Actions トリガー結果: " + response.getResponseCode());
}
