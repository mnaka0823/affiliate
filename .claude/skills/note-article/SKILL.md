---
name: note-article
description: note有料記事を1本作るオーケストレーター。リサーチ→ペルソナ→構成→本文→タイトル→ペルソナ評価＋品質監査→改善判定を、合格するか上限に達するまでループし、note貼り付け用の最終稿を出す。「note記事を作って」「有料記事を1本書いて」で使う。
argument-hint: "[テーマ（省略するとネタ探しから）]"
---

# note有料記事オーケストレーター

あなたはパイプライン全体の進行役です。**自分では記事を書かず、評価もしません。** 各工程はサブエージェントに任せ、
ファイルの受け渡しと、ループの進行、状態の記録だけを行います。サブエージェントへの指示には、
必ず「読むファイルのパス」と「書き出すファイルのパス」を明記してください。

テーマ：$ARGUMENTS

## 0. 準備
1. `config/pipeline.json` と `knowledge/theme-direction.md`（記事の方向性）を読む。
   各サブエージェントへの指示に「記事の方向性は knowledge/theme-direction.md に従う」と添える。
2. `knowledge/author-profile.md` がテンプレートのまま（実績欄が空）なら、ユーザーに一言警告する
   （対話モードなら記入を促す。非対話なら続行し、最終報告で警告する）。
3. 作業フォルダは、リサーチ後に決まる slug で `articles/<YYYYMMDD>-<slug>/` とする。
   リサーチ前は `articles/_tmp-<YYYYMMDDHHMM>/` で始め、slug が決まったら `mv` で改名する。
4. `state.json` を作る：
```json
{"slug": "", "theme": "", "status": "running", "current_version": 0, "best_version": null,
 "history": [], "started_at": "<ISO8601>"}
```

## 1. リサーチ（1回だけ）
`trend-researcher` を起動。出力先 `01_research.md`。テーマが空ならネタ探しモード。
返ってきた slug でフォルダを改名し、state.json の slug・theme を更新。

## 2. ペルソナ（1回だけ）
`persona-builder` を起動。入力 `01_research.md`、出力 `02_personas.md`。
返ってきたペルソナID一覧を控える。

## 3. 改善ループ（n = 1 から）
各版のファイルは `v{n}/` に置く。`restart_from` は初回 `outline`。

1. **構成**（`restart_from` が outline のとき）：`structure-architect` → `v{n}/outline.md`
   - それ以外は前版の `outline.md` を `v{n}/` にコピー。
2. **本文**（outline または draft のとき）：`article-writer` → `v{n}/draft.md`
   - title だけのときは前版の `draft.md` をコピー。
3. **タイトル**（常に実行）：`title-optimizer` → `v{n}/titles.md`
4. **評価（並列）**：**1つのメッセージで同時に**次を起動する。
   - ペルソナごとに `persona-evaluator`（プロンプトでペルソナIDを指定、出力 `v{n}/eval_<ID>.md`。n≥2 なら前版との一対比較も指示）
   - `quality-auditor`（出力 `v{n}/eval_audit.md`）
   評価エージェントには、構成の意図や改訂メモを伝えない。読むファイルを `persona-evaluator` の定義どおりに限定する。
5. **判定**：`improvement-director` → `v{n}/director.md`。返ってきたJSONを `state.json` の `history` に追加し、
   `best_version` と `current_version` を更新する。
6. `decision` が `continue` なら、`restart_from` と `director.md` のパスを次の版の各エージェントに渡し、n+1 で 3-1 に戻る。
   それ以外ならループを抜ける。

途中で各版の要点（総合点・判定・次の開始工程）を1行ずつユーザーに報告する。

## 4. 仕上げ
最良版 `v{best}` から、作業フォルダ直下に `final.md` を作る（これは自分で整形してよい）。
```
# <採用タイトル>
価格：◯◯円 ／ 予備タイトル：... ／ 見出し画像の文言：...
ハッシュタグ案：#... （5個程度）

（無料部分）

──────── ここから有料（noteエディタで有料エリアを設定） ────────

（有料部分）
```
続けて、最良版の `outline.md` にある「次に困りそうなこと」を `next-themes.md` に書き出す（次の記事・シリーズの候補）。

さらに `publish-checklist.md` を作る：
- [ ] `【要記入】` をすべて自分の実体験で埋めた（残り件数：◯）
- [ ] quality-auditor の major 指摘を確認した
- [ ] 数字・出典を自分の目で確認した
- [ ] 状況パターンA/B/Cそれぞれの手順を、自分の経験と照らして確認した
- [ ] 変わりうる情報（制度・料金・画面）に時点を書いた
- [ ] アフィリエイトリンクがある場合、広告である旨を明示した
- [ ] note の最新の利用規約・ガイドラインに反していない
- [ ] 価格と有料ラインをnoteエディタで設定した
- [ ] 公開後、`/note-learn` で実績を記録する予定を入れた

`state.json` の status を `done`（合格）または `done_unpassed`（未合格で終了）にする。

## 5. 最終報告
次をユーザーに返す：採用タイトル、価格、次に困りそうなこと（次の記事の候補）、版ごとの点数推移、合格したか、要記入の件数、`final.md` のパス、
未合格ならその主な理由。**公開は人が確認してから行うこと**を添える。
