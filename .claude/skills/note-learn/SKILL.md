---
name: note-learn
description: 公開したnote記事の実績（閲覧数・販売数・スキ）を記録し、ペルソナ評価と実売のずれを分析して knowledge/learnings.md を更新する。「売上を記録して」「実績を反映して」で使う。
argument-hint: "[slug] [views_7d] [sales_7d] ... または自由記述"
---

# 実売データの学習

入力：$ARGUMENTS（不足があればユーザーに聞く。noteのダッシュボードの数字を貼ってもらってもよい）

## 手順
1. 対象記事の `articles/<slug>/state.json` と `final.md` から、タイトル・価格・総合点・平均購入意向・平均満足度を取る。
2. `knowledge/performance.csv` に1行追加（同じ slug があれば更新）。列は1行目のヘッダに従う。
3. 3本以上データがあれば分析する：
   - 購入率（sales / views）と、平均購入意向・総合点の順位相関（本数が少ないうちは傾向として扱う）
   - 評価が高いのに売れなかった記事、評価が低いのに売れた記事の共通点
   - ジャンル・価格帯・タイトルの型・有料ラインの位置ごとの傾向
4. `knowledge/learnings.md` を更新する。各知見に根拠（どの記事のどの数字か）を添える。古い知見と矛盾したら書き換える。
5. 評価と実売が大きくずれる場合は、`knowledge/evaluation-rubric.md` の重みや `config/pipeline.json` のしきい値の変更案を提示する
   （変更はユーザーの了承を得てから）。
6. 結果を短く報告する。
