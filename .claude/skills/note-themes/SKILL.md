---
name: note-themes
description: 記事の方向性（knowledge/theme-direction.md の6条件）を満たすnote有料記事のテーマを、検索キーワード・場面・状況の分かれ方・無料/有料の中身・次に困ることまで表で一覧にする。「テーマを15個出して」「ネタ一覧を作って」で使う。
argument-hint: "[個数（既定15）] [ジャンル・読者の絞り込み（任意）]"
---

# テーマ一覧の作成

引数：$ARGUMENTS（1つ目が数字なら個数。それ以外はジャンル・読者の絞り込み）

1. `trend-researcher` を**テーマ一覧モード**で起動する。指示に含めること：
   - 個数（省略時は `config/pipeline.json` の `theme_list_count`）と絞り込み条件
   - `knowledge/theme-direction.md` の6条件をすべて満たすこと（C6は加点）
   - 単価を上げられるテーマより、繰り返し検索されるテーマを優先すること
   - 出力先：`articles/_themes/<YYYYMMDD>[-<絞り込み>].md`
2. 返ってきたファイルを読み、表をそのままユーザーに見せる。
3. 最後に次を一言添える：
   - 上位3テーマと、その理由（優先度の点数）
   - シリーズにできる組み合わせ（「次に困りそうなこと」がつながるもの）
   - 次の操作：`/note-article <テーマ名>` で1本作る、`scripts/batch.sh` で表の上位をまとめて作る
