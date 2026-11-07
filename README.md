# note有料記事 量産マルチエージェント（Claude Code）

Claude Code のサブエージェントとスキルで、noteの有料記事を
「調査 → ペルソナ → 構成 → 本文 → タイトル → ペルソナ評価＋品質監査 → 改善」のループで作ります。

## はじめに
1. `knowledge/author-profile.md` を自分の情報に書き換える（**最重要**。実績がないと独自性のない記事になります）
2. 必要なら `config/pipeline.json` でペルソナ数・ループ上限・合格ラインを調整
3. 確認なしで動かしたい場合は `docs/settings.example.json` を `.claude/settings.json` にコピー
4. Claude Code で実行：
   ```
   /note-article ChatGPTで業務マニュアルを半自動で作る方法
   /note-article            # ネタ探しから
   /note-batch 5 AI活用      # 5本まとめて
   ```
   大量に作るときは記事ごとに別セッションで動かす：`scripts/batch.sh themes.txt`
5. `articles/<日付>-<slug>/final.md` と `publish-checklist.md` を確認し、`【要記入】` を埋めて手動で公開
6. 公開から7日・30日後に `/note-learn <slug> 閲覧数 販売数 ...` で実績を記録（次回以降の精度が上がります）

## エージェント構成
| 工程 | エージェント | 役割 |
|---|---|---|
| 0 | `/note-article`（スキル） | 全体の進行、ループ制御、状態記録 |
| 1 | `trend-researcher` | 需要・競合・価格・実売データからネタを選ぶ |
| 2 | `persona-builder` | 買う人3〜5人（懐疑派を含む） |
| 3 | `structure-architect` | 構成・有料ライン・価格 |
| 4 | `article-writer` | 本文 |
| 5 | `title-optimizer` | 20案 → 足切り → 一対比較で1つに |
| 6 | `persona-evaluator` ×人数 ＋ `quality-auditor` | 2段階のペルソナ評価（並列）と、事実・規約の監査 |
| 7 | `improvement-director` | 集計・判定・どこから直すかの指示 |
| — | `/note-learn`（スキル） | 実売データで評価を補正 |

当初の7エージェント案から何をなぜ変えたかは `docs/architecture.md` にまとめています。
