# 画像の生成・編集（OpenAI Images API）

> **現在の運用**：画像の生成はChatGPT側で手動で行います（貼る指示文：`knowledge/visual-trial-1-chatgpt.md`）。この文書のAPI経由の方法は、OpenAIのAPI残高を用意した場合の任意の手段です。

`scripts/image.py`（標準ライブラリのみ。`pip install` は不要）と、Claude Code から自然言語で頼む `/note-image` スキルで使います。

## 準備
1. **APIキーを環境変数に設定する**（キーをチャットやファイルに貼らない）
   - シェル：`export OPENAI_API_KEY=...`
   - または、`.env.example` を `.env` にコピーして `OPENAI_API_KEY=` を埋める（`.env` は git に入りません）
2. 設定を確認：`python3 scripts/image.py check`
3. **モデルIDを確認する**：`python3 scripts/image.py models`
   - 既定は `gpt-image-2.6-sunburst` ですが、OpenAIの公式資料で確認できていません（見つかったのは再販業者のページで、`gpt-image-2.5-sunburst` の情報が中心でした）。
   - 一覧にIDがなければ、`config/images.json` の `model` か環境変数 `OPENAI_IMAGE_MODEL` を直してください。
4. 接続先 `api.openai.com` が、実行環境のネットワークで許可されている必要があります（クラウド環境では許可リストに追加）。

### クラウド環境（Claude Code on the web）でのキー
環境変数にキーを平文で置かず、環境の「ネットワークシークレット」に保存します（セッションで `request_credential` のフォームから保存）。通信時にプロキシが認証ヘッダーを付けるので、スクリプトにはダミーの値を渡します。

```bash
OPENAI_API_KEY=proxy-injected python3 scripts/image.py models
```
キーの保存先は、このリポジトリ専用の環境（`affiliate-note`）にしてあります。

### 429「no credits remaining」と出たとき
OpenAI側のクレジット（残高）が足りません。platform.openai.com の Billing で残高を追加してください。エラーでは料金はかかりません。

## Claude Code から使う（自然言語）
`/note-image` を付けるか、ふだんの言葉で頼みます。

- 「noteの見出し画像を作って。落ち着いた青系で、鍵とスマホ」
- 「images/output の最新の画像の背景を白にして」
- 「このロゴを透明背景のPNGにして。保存先は images/logo」

スキルは、料金がかかることを踏まえて1依頼につき1回だけ呼び、保存後に画像を開いて確認します。

## コマンドで使う
```bash
python3 scripts/image.py generate -p "夕焼けの海辺のイラスト" --size 1536x1024 --out images/output --name sunset
python3 scripts/image.py edit --image images/output/a.png -p "背景を白無地にする" --name white-bg
python3 scripts/image.py edit --image a.png --mask mask.png -p "マスクの部分だけ青にする"
python3 scripts/image.py generate -p "…" --dry-run      # APIを呼ばず、送る内容だけ確認
```
主なオプション：`--size`、`--quality`、`--n`（上限は `max_n`）、`--format png|jpeg|webp`、`--background`、`--param KEY=VALUE`（そのままAPIに渡す）、`--out`、`--name`、`--no-meta`。

## 保存先
- 既定：`images/output/`（`config/images.json` の `output_dir`、または `OPENAI_IMAGE_OUTPUT_DIR`、または `--out`）。相対パスはプロジェクトのルートから。
- ファイル名：`日時-名前-連番.png`。既存のファイルは上書きしません。
- 同名の `.json` に、指示・モデル・設定・元画像のパスを記録します（APIキーは入りません）。
- `images/output/` と `.env` は git に入れない設定です。

## 設定の優先順位
`--オプション` ＞ 環境変数（`OPENAI_IMAGE_MODEL`、`OPENAI_IMAGE_OUTPUT_DIR`、`OPENAI_BASE_URL`）＞ `config/images.json` ＞ 組み込みの既定値

## 注意
- APIの利用料金がかかります。モデルごとの価格は公式で確認してください。
- 編集では、元の画像がOpenAIに送られます。個人情報が写った画像に注意してください。
- 画像内の日本語は崩れやすいので、文字はnoteのエディタで足す方が確実です。
- AI生成画像の表示や権利の扱いは、noteとOpenAIの最新の規約で確認してください。

## テスト
`python3 -m unittest discover -s tests -v`（模擬サーバーを使うので、キーもネットワークも不要）
