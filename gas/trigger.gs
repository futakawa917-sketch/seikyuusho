/**
 * 請求書メール検知 → GitHub Actions トリガー
 *
 * セットアップ手順:
 * 1. https://script.google.com/ で新規プロジェクトを作成し、このコードを貼り付ける
 * 2. プロジェクトの設定 → スクリプト プロパティに以下を追加する
 *    - GITHUB_TOKEN: 対象リポジトリだけに Contents: Read and write を許可した
 *      Fine-grained Personal Access Token
 *    - GITHUB_REPO: futakawa917-sketch/seikyuusho
 * 3. setupTrigger を1回だけ手動実行する
 *
 * Gmailにはメール受信イベントのトリガーがないため、最短の1分間隔で確認する。
 * setupTrigger 実行時点のメールは検知済みとして記録し、過去メールでは起動しない。
 */

var SEARCH_QUERY = "newer_than:2d {subject:請求 subject:invoice} -label:請求書処理済み";
var SEEN_MESSAGE_IDS_KEY = "SEEN_MESSAGE_IDS";
var MAX_SEEN_MESSAGE_IDS = 500;


function setupTrigger() {
  validateSettings();

  // 再設定してもトリガーが重複しないよう、同じ関数の既存トリガーを削除する。
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (trigger.getHandlerFunction() === "checkNewInvoices") {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  // セットアップ以前のメールでGitHub Actionsを起動しないよう初期化する。
  saveSeenMessageIds(findInvoiceMessageIds());

  ScriptApp.newTrigger("checkNewInvoices")
    .timeBased()
    .everyMinutes(1)
    .create();

  Logger.log("1分ごとの請求書メール監視を設定しました。");
}


function checkNewInvoices() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) {
    return;
  }

  try {
    validateSettings();

    var currentIds = findInvoiceMessageIds();
    var seenIds = loadSeenMessageIds();
    var seenLookup = {};
    seenIds.forEach(function (id) {
      seenLookup[id] = true;
    });

    var newIds = currentIds.filter(function (id) {
      return !seenLookup[id];
    });

    if (newIds.length === 0) {
      return;
    }

    var statusCode = triggerGitHubAction();
    if (statusCode !== 204) {
      throw new Error("GitHub Actionsの起動に失敗しました。HTTP " + statusCode);
    }

    // GitHubが受け付けた後だけ記録する。メールの既読・未読状態は変更しない。
    saveSeenMessageIds(currentIds.concat(seenIds));
    Logger.log(newIds.length + "件の新着請求書メールを検知しました。");
  } finally {
    lock.releaseLock();
  }
}


function findInvoiceMessageIds() {
  var cutoff = Date.now() - (2 * 24 * 60 * 60 * 1000);
  var ids = [];

  GmailApp.search(SEARCH_QUERY, 0, 50).forEach(function (thread) {
    thread.getMessages().forEach(function (message) {
      if (message.getDate().getTime() >= cutoff && /請求|invoice/i.test(message.getSubject())) {
        ids.push(message.getId());
      }
    });
  });

  return ids;
}


function triggerGitHubAction() {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty("GITHUB_TOKEN");
  var repo = props.getProperty("GITHUB_REPO");
  var url = "https://api.github.com/repos/" + repo + "/dispatches";

  var response = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    payload: JSON.stringify({ event_type: "new-invoice" }),
    muteHttpExceptions: true,
  });

  Logger.log("GitHub Actions トリガー結果: " + response.getResponseCode());
  return response.getResponseCode();
}


function validateSettings() {
  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty("GITHUB_TOKEN") || !props.getProperty("GITHUB_REPO")) {
    throw new Error("GITHUB_TOKEN と GITHUB_REPO をスクリプト プロパティに設定してください。");
  }
}


function loadSeenMessageIds() {
  var value = PropertiesService.getScriptProperties().getProperty(SEEN_MESSAGE_IDS_KEY);
  return value ? JSON.parse(value) : [];
}


function saveSeenMessageIds(ids) {
  var uniqueIds = [];
  var lookup = {};

  ids.forEach(function (id) {
    if (!lookup[id]) {
      lookup[id] = true;
      uniqueIds.push(id);
    }
  });

  PropertiesService.getScriptProperties().setProperty(
    SEEN_MESSAGE_IDS_KEY,
    JSON.stringify(uniqueIds.slice(0, MAX_SEEN_MESSAGE_IDS))
  );
}
