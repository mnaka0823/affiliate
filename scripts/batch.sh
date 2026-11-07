#!/usr/bin/env bash
# note有料記事をテーマごとに別セッションで量産する（ヘッドレス実行）。
#   使い方: scripts/batch.sh themes.txt
#   themes.txt は1行1テーマ。空行と # で始まる行は無視する。
#   テーマを空のまま1本作るときは: scripts/batch.sh -
set -euo pipefail

cd "$(dirname "$0")/.."
input="${1:?テーマを1行ずつ書いたファイルを指定してください（'-' でネタ探しから1本）}"
log_dir="articles/_logs"
mkdir -p "$log_dir"

run_one() {
  local theme="$1"
  local stamp; stamp="$(date +%Y%m%d-%H%M%S)"
  echo "==> ${theme:-（ネタ探しから）}"
  # 権限は .claude/settings.json の allow リストに従う（docs/settings.example.json を参照）。
  claude -p "/note-article ${theme}" \
    --permission-mode acceptEdits \
    --output-format text \
    > "${log_dir}/${stamp}.log" 2>&1 \
    && echo "    完了: ${log_dir}/${stamp}.log" \
    || echo "    失敗: ${log_dir}/${stamp}.log"
}

if [[ "$input" == "-" ]]; then
  run_one ""
else
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "${line// }" || "$line" == \#* ]] && continue
    run_one "$line"
  done < "$input"
fi
