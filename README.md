# Daily Report Builder

Confluence Cloud に日次レポートページを作成する小さなCLIです。

## Setup

```bash
export CONFLUENCE_BASE_URL="https://your-domain.atlassian.net"
export CONFLUENCE_EMAIL="you@example.com"
export CONFLUENCE_API_TOKEN="your-api-token"
export CONFLUENCE_SPACE_ID="123456789"
# 任意: 親ページ配下に作る場合
export CONFLUENCE_PARENT_ID="987654321"
```

## Usage

```bash
uv run python main.py --content "今日やったことをここに書く"
```

日付やタイトルを指定する場合:

```bash
uv run python main.py \
  --date 2026-06-28 \
  --title "Daily Report 2026-06-28" \
  --content "実装、レビュー、明日の予定"
```

Confluence API への通信は `app/confluence_client.py` の `ConfluenceClient` に集約しています。
Jira API への通信は `app/jira_client.py` の `JiraClient` に集約しています。

## Test

```bash
uv run python -m unittest discover -s test
```

アプリケーションコードは `app/`、テストコードは `test/` に配置しています。
