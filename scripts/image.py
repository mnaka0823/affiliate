#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAI Images API で画像を生成・編集して、指定フォルダに保存する小さなCLI。

標準ライブラリだけで動く（pip install は不要）。
APIキーは環境変数 OPENAI_API_KEY から読む（プロジェクト直下の .env も可。.env は git に入れない）。
キーはファイルにもログにも書き出さない。

使い方の例:
  python3 scripts/image.py check
  python3 scripts/image.py models
  python3 scripts/image.py generate -p "夕焼けの海辺のイラスト" --out images/output
  python3 scripts/image.py edit --image images/output/a.png -p "背景を白にして" --name white-bg
  python3 scripts/image.py generate -p "..." --dry-run      # APIを呼ばずにリクエストだけ確認
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "images.json"

DEFAULTS = {
    "model": "gpt-image-2.6-sunburst",  # 公式資料で未確認。`models` コマンドで確かめて差し替える
    "base_url": "https://api.openai.com/v1",
    "size": "1024x1024",
    "quality": "medium",
    "output_format": "png",
    "n": 1,
    "output_dir": "images/output",
    "max_n": 4,
    "timeout_sec": 300,
    "max_image_mb": 25,  # 手元の安全弁。APIの上限ではない
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
FORMAT_EXT = {"png": "png", "jpeg": "jpg", "webp": "webp"}


class CliError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- 設定
def load_dotenv(path: Path) -> list[str]:
    """`.env` の OPENAI_* だけを読む。すでに環境変数にあるものは上書きしない。"""
    loaded: list[str] = []
    if not path.is_file():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.startswith("OPENAI_") and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def load_config(path: Path = CONFIG_PATH, env=None) -> dict:
    env = os.environ if env is None else env
    cfg = dict(DEFAULTS)
    if path.is_file():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    if env.get("OPENAI_IMAGE_MODEL"):
        cfg["model"] = env["OPENAI_IMAGE_MODEL"]
    if env.get("OPENAI_IMAGE_OUTPUT_DIR"):
        cfg["output_dir"] = env["OPENAI_IMAGE_OUTPUT_DIR"]
    if env.get("OPENAI_BASE_URL"):
        cfg["base_url"] = env["OPENAI_BASE_URL"]
    cfg["base_url"] = str(cfg["base_url"]).rstrip("/")
    return cfg


def resolve_dir(value: str) -> Path:
    """相対パスはプロジェクトのルートからの相対とする（作業フォルダに依存しない）。"""
    p = Path(value).expanduser()
    return p if p.is_absolute() else ROOT / p


def get_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise CliError(
            "OPENAI_API_KEY が設定されていません。\n"
            "  シェルで:  export OPENAI_API_KEY=...（キーはチャットに貼らないでください）\n"
            "  または、プロジェクト直下の .env に OPENAI_API_KEY=... と書く（.env は git に入りません）",
            code=2,
        )
    return key


# ---------------------------------------------------------------- リクエスト作成
def parse_extra(pairs: list[str] | None) -> dict:
    extra: dict = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise CliError(f"--param は KEY=VALUE の形で指定してください: {pair}")
        k, v = pair.split("=", 1)
        try:
            extra[k.strip()] = json.loads(v)
        except json.JSONDecodeError:
            extra[k.strip()] = v
    return extra


def build_params(args, cfg: dict) -> dict:
    prompt = (args.prompt or "").strip()
    if not prompt:
        raise CliError("--prompt（-p）に画像の指示を書いてください。")
    n = args.n if args.n is not None else int(cfg["n"])
    if not 1 <= n <= int(cfg["max_n"]):
        raise CliError(f"--n は 1〜{cfg['max_n']} の範囲で指定してください（config/images.json の max_n）。")
    fmt = args.format or cfg["output_format"]
    if fmt not in FORMAT_EXT:
        raise CliError(f"--format は {', '.join(FORMAT_EXT)} のどれかにしてください。")
    params: dict = {
        "model": args.model or cfg["model"],
        "prompt": prompt,
        "n": n,
        "size": args.size or cfg["size"],
        "quality": args.quality or cfg["quality"],
        "output_format": fmt,
    }
    if args.background:
        params["background"] = args.background
    if args.compression is not None:
        params["output_compression"] = args.compression
    params.update(parse_extra(args.param))
    return params


def encode_multipart(fields: list[tuple[str, str]], files: list[tuple[str, Path]]):
    boundary = uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    for name, path in files:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", path.name) or "image"
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{safe}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def check_input_images(paths: list[str], cfg: dict) -> list[Path]:
    result: list[Path] = []
    limit = int(cfg["max_image_mb"]) * 1024 * 1024
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.is_absolute() and not p.exists():
            p = ROOT / p
        if not p.is_file():
            raise CliError(f"画像ファイルが見つかりません: {raw}")
        if p.suffix.lower() not in IMAGE_EXTS:
            raise CliError(f"対応していない形式です（png / jpg / webp のみ）: {raw}")
        if p.stat().st_size > limit:
            raise CliError(f"画像が大きすぎます（{cfg['max_image_mb']}MB まで）: {raw}")
        result.append(p)
    return result


# ---------------------------------------------------------------- API呼び出し
def redact(text: str, key: str | None) -> str:
    return text.replace(key, "***") if key else text


def api_request(method: str, url: str, key: str, body: bytes | None, content_type: str | None, timeout: int) -> dict:
    headers = {"Authorization": f"Bearer {key}", "User-Agent": "note-affiliate-image-cli/1.0"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(raw).get("error", {}).get("message") or raw
        except json.JSONDecodeError:
            message = raw
        hint = ""
        if e.code in (400, 404) and "model" in message.lower():
            hint = "\n  モデルIDが違う可能性があります。`python3 scripts/image.py models` で使えるIDを確認し、OPENAI_IMAGE_MODEL か config/images.json の model を直してください。"
        elif e.code == 401:
            hint = "\n  APIキーが無効です。OPENAI_API_KEY を確認してください。"
        elif e.code == 429:
            if "credit" in message.lower() or "billing" in message.lower() or "quota" in message.lower():
                hint = "\n  OpenAIのクレジット（残高）が足りません。platform.openai.com の Billing で残高を追加してください。"
            else:
                hint = "\n  レート制限です。時間をおいて再実行してください。"
        raise CliError(redact(f"HTTP {e.code}: {message}{hint}", key))
    except urllib.error.URLError as e:
        raise CliError(redact(f"APIに接続できません: {e.reason}（ネットワークの許可設定や OPENAI_BASE_URL を確認）", key))
    except TimeoutError:
        raise CliError(f"{timeout}秒でタイムアウトしました。config/images.json の timeout_sec を延ばしてください。")


def download(url: str, timeout: int) -> bytes:
    if not url.startswith("https://"):
        raise CliError("https 以外のURLからは画像を取得しません。")
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


# ---------------------------------------------------------------- 保存
def slugify(text: str | None, fallback: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", text or "").strip("-")[:40]
    return s or fallback


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    p = directory / f"{stem}.{ext}"
    i = 2
    while p.exists():
        p = directory / f"{stem}-{i}.{ext}"
        i += 1
    return p


def save_images(result: dict, out_dir: Path, slug: str, fmt: str, timeout: int, meta: dict | None) -> list[Path]:
    items = result.get("data") or []
    if not items:
        raise CliError("画像が返されませんでした: " + json.dumps(result, ensure_ascii=False)[:300])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    saved: list[Path] = []
    for i, item in enumerate(items, start=1):
        if item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            raw = download(item["url"], timeout)
        else:
            continue
        if not raw:
            continue
        path = unique_path(out_dir, f"{stamp}-{slug}-{i}", FORMAT_EXT[fmt])
        path.write_bytes(raw)
        saved.append(path)
        if meta is not None:
            side = dict(meta, file=path.name, revised_prompt=item.get("revised_prompt"), usage=result.get("usage"))
            path.with_suffix(".json").write_text(json.dumps(side, ensure_ascii=False, indent=2), encoding="utf-8")
    if not saved:
        raise CliError("保存できる画像データがありませんでした。")
    return saved


# ---------------------------------------------------------------- コマンド
def cmd_check(args, cfg) -> int:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    out_dir = resolve_dir(args.out or cfg["output_dir"])
    print(f"OPENAI_API_KEY : {'設定あり' if key else '未設定'}")
    print(f"モデル         : {cfg['model']}（公式資料で未確認なら `models` で確かめる）")
    print(f"API            : {cfg['base_url']}")
    print(f"保存先         : {out_dir}（{'あり' if out_dir.exists() else 'まだ無い。生成時に作る'}）")
    print(f"設定ファイル   : {CONFIG_PATH}（{'あり' if CONFIG_PATH.is_file() else 'なし。既定値を使う'}）")
    return 0 if key else 2


def cmd_models(args, cfg) -> int:
    key = get_api_key()
    data = api_request("GET", f"{cfg['base_url']}/models", key, None, None, int(cfg["timeout_sec"]))
    ids = sorted(m.get("id", "") for m in data.get("data", []))
    if not args.all:
        ids = [i for i in ids if "image" in i.lower()]
    if not ids:
        print("該当するモデルが見つかりませんでした（--all で全件）。")
        return 1
    print("\n".join(ids))
    print(f"\n現在の設定: {cfg['model']}  {'（一覧にあります）' if cfg['model'] in ids else '（一覧にありません。IDを確認してください）'}")
    return 0


def run_images(mode: str, args, cfg) -> int:
    params = build_params(args, cfg)
    out_dir = resolve_dir(args.out or cfg["output_dir"])
    timeout = int(cfg["timeout_sec"])
    files: list[tuple[str, Path]] = []
    if mode == "edit":
        for p in check_input_images(args.image, cfg):
            files.append(("image[]", p))
        if args.mask:
            files.append(("mask", check_input_images([args.mask], cfg)[0]))
        endpoint = f"{cfg['base_url']}/images/edits"
    else:
        endpoint = f"{cfg['base_url']}/images/generations"

    if args.dry_run:
        print(json.dumps({"endpoint": endpoint, "params": params,
                          "files": [{"field": n, "path": str(p)} for n, p in files],
                          "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
        return 0

    key = get_api_key()
    if mode == "edit":
        fields = [(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v)) for k, v in params.items()]
        body, ctype = encode_multipart(fields, files)
    else:
        body, ctype = json.dumps(params).encode("utf-8"), "application/json"

    result = api_request("POST", endpoint, key, body, ctype, timeout)
    meta = None if args.no_meta else {
        "mode": mode, "model": params["model"], "prompt": params["prompt"],
        "params": {k: v for k, v in params.items() if k not in ("prompt", "model")},
        "inputs": [str(p) for _, p in files], "created_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    saved = save_images(result, out_dir, slugify(args.name, "edit" if mode == "edit" else "image"),
                        params["output_format"], timeout, meta)
    for p in saved:
        print(f"保存: {p}")
    print(f"{len(saved)}枚保存しました。モデル: {params['model']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="OpenAI Images API で画像を生成・編集する")
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p, with_prompt=True):
        if with_prompt:
            p.add_argument("-p", "--prompt", help="画像の指示（必須）")
        p.add_argument("--model", help="モデルID（既定は config/images.json か OPENAI_IMAGE_MODEL）")
        p.add_argument("--size", help="例: 1024x1024 / 1536x1024 / 1024x1536 / auto")
        p.add_argument("--quality", help="例: low / medium / high / auto")
        p.add_argument("--n", type=int, help="枚数（上限は config の max_n）")
        p.add_argument("--format", choices=list(FORMAT_EXT), help="保存形式")
        p.add_argument("--background", help="例: transparent / opaque / auto")
        p.add_argument("--compression", type=int, help="jpeg/webp の圧縮率 0〜100")
        p.add_argument("--param", action="append", metavar="KEY=VALUE", help="そのままAPIに渡す追加パラメータ（繰り返し可）")
        p.add_argument("--out", help="保存先フォルダ（相対パスはプロジェクトのルートから）")
        p.add_argument("--name", help="ファイル名に入れる英数字の名前")
        p.add_argument("--no-meta", action="store_true", help="指示や設定を書いた .json を保存しない")
        p.add_argument("--dry-run", action="store_true", help="APIを呼ばずに、送る内容だけ表示する")

    g = sub.add_parser("generate", help="テキストから画像を生成する")
    common(g)
    e = sub.add_parser("edit", help="既存の画像を編集する")
    e.add_argument("--image", action="append", required=True, help="編集する画像（複数指定可）")
    e.add_argument("--mask", help="編集する範囲を示すマスク画像（任意）")
    common(e)
    c = sub.add_parser("check", help="設定を確認する（APIは呼ばない）")
    c.add_argument("--out")
    m = sub.add_parser("models", help="使える画像モデルのIDを一覧する（APIを呼ぶ）")
    m.add_argument("--all", action="store_true", help="画像以外も含めて全件表示")
    return ap


def main(argv=None) -> int:
    load_dotenv(ROOT / ".env")
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config()
        if args.command == "check":
            return cmd_check(args, cfg)
        if args.command == "models":
            return cmd_models(args, cfg)
        return run_images(args.command, args, cfg)
    except CliError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
