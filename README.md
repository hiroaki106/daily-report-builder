# Daily Report Builder

Confluence Cloud に日次レポートページを作成する小さなCLIです。

## Setup

`app/config.py` にJiraとConfluenceの接続先、対象IDを設定します。
認証情報を `None` にするとChromeのCookieを使用します。

## Usage

```bash
uv run python main.py
```

引数を省略すると、開始日時と終了日時を対話形式で入力します。

集計期間を指定する場合（`yyyy/MM/dd HH:mm`形式）:

```bash
uv run python main.py \
  --start-date "2026/07/01 09:00" \
  --end-date "2026/07/01 18:00"
```

Confluence API への通信は `app/confluence_client.py` の `ConfluenceClient` に集約しています。
Jira API への通信は `app/jira_client.py` の `JiraClient` に集約しています。

## Test

```bash
uv run python -m unittest discover -s test
```

アプリケーションコードは `app/`、テストコードは `test/` に配置しています。
