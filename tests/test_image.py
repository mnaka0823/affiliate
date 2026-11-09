"""scripts/image.py のテスト。OpenAI の代わりに手元の模擬サーバーを使う（APIキー・ネットワーク不要）。

実行: python3 -m unittest discover -s tests -v
"""
import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "image.py"
# 1x1 の PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

spec = importlib.util.spec_from_file_location("image_cli", SCRIPT)
image_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_cli)


class Mock(BaseHTTPRequestHandler):
    last = {}
    fail = None  # (status, body)

    def log_message(self, *a):
        pass

    def _send(self, status, obj):
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        Mock.last = {"method": "GET", "path": self.path, "auth": self.headers.get("Authorization")}
        self._send(200, {"data": [{"id": "gpt-image-2.6-sunburst"}, {"id": "gpt-4o"}, {"id": "gpt-image-1"}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        Mock.last = {"method": "POST", "path": self.path, "auth": self.headers.get("Authorization"),
                     "ctype": self.headers.get("Content-Type"), "body": body}
        if Mock.fail:
            status, obj = Mock.fail
            return self._send(status, obj)
        n = 1
        if "json" in (self.headers.get("Content-Type") or ""):
            n = json.loads(body).get("n", 1)
        else:
            marker = b'name="n"\r\n\r\n'
            if marker in body:
                n = int(body.split(marker)[1].split(b"\r\n")[0])
        self._send(200, {"data": [{"b64_json": base64.b64encode(PNG).decode()} for _ in range(n)],
                         "usage": {"total_tokens": 7}})


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Mock)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Mock.fail = None
        Mock.last = {}
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, key="sk-test-SECRET", extra_env=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("OPENAI_")}
        env["OPENAI_BASE_URL"] = f"http://127.0.0.1:{self.port}/v1"
        if key is not None:
            env["OPENAI_API_KEY"] = key
        env.update(extra_env or {})
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)

    # ---- 生成
    def test_generate_saves_files_and_metadata(self):
        r = self.run_cli("generate", "-p", "青い海", "--n", "2", "--out", str(self.out), "--name", "sea")
        self.assertEqual(r.returncode, 0, r.stderr)
        pngs = sorted(self.out.glob("*.png"))
        self.assertEqual(len(pngs), 2)
        self.assertTrue(all(p.read_bytes() == PNG for p in pngs))
        self.assertIn("-sea-1", pngs[0].name)
        meta = json.loads(pngs[0].with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(meta["prompt"], "青い海")
        self.assertEqual(meta["mode"], "generate")
        self.assertNotIn("SECRET", json.dumps(meta))

    def test_generate_request_shape(self):
        self.run_cli("generate", "-p", "x", "--size", "1536x1024", "--quality", "high",
                     "--background", "transparent", "--param", "moderation=low", "--out", str(self.out))
        self.assertEqual(Mock.last["path"], "/v1/images/generations")
        self.assertEqual(Mock.last["auth"], "Bearer sk-test-SECRET")
        sent = json.loads(Mock.last["body"])
        self.assertEqual(sent["model"], "gpt-image-2.6-sunburst")
        self.assertEqual((sent["size"], sent["quality"], sent["background"], sent["moderation"]),
                         ("1536x1024", "high", "transparent", "low"))

    def test_model_override_by_env(self):
        self.run_cli("generate", "-p", "x", "--out", str(self.out), extra_env={"OPENAI_IMAGE_MODEL": "my-model"})
        self.assertEqual(json.loads(Mock.last["body"])["model"], "my-model")

    def test_output_dir_from_env(self):
        r = self.run_cli("generate", "-p", "x", extra_env={"OPENAI_IMAGE_OUTPUT_DIR": str(self.out)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(list(self.out.glob("*.png"))), 1)

    def test_no_meta(self):
        self.run_cli("generate", "-p", "x", "--out", str(self.out), "--no-meta")
        self.assertEqual(list(self.out.glob("*.json")), [])

    # ---- 編集
    def test_edit_sends_multipart_with_images_and_mask(self):
        src = Path(self.tmp.name) / "元画像 1.png"
        src.write_bytes(PNG)
        mask = Path(self.tmp.name) / "mask.png"
        mask.write_bytes(PNG)
        r = self.run_cli("edit", "--image", str(src), "--mask", str(mask), "-p", "背景を白に",
                         "--out", str(self.out), "--name", "white")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Mock.last["path"], "/v1/images/edits")
        self.assertIn("multipart/form-data; boundary=", Mock.last["ctype"])
        body = Mock.last["body"]
        self.assertIn(b'name="image[]"; filename="____1.png"', body)  # 日本語・空白は安全な名前に
        self.assertIn(b'name="mask"; filename="mask.png"', body)
        self.assertIn('背景を白に'.encode(), body)
        self.assertIn(b'name="model"\r\n\r\ngpt-image-2.6-sunburst', body)
        self.assertEqual(len(list(self.out.glob("*-white-1.png"))), 1)

    def test_edit_rejects_missing_and_unsupported_files(self):
        r = self.run_cli("edit", "--image", "/no/such.png", "-p", "x", "--out", str(self.out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("見つかりません", r.stderr)
        gif = Path(self.tmp.name) / "a.gif"
        gif.write_bytes(b"GIF89a")
        r = self.run_cli("edit", "--image", str(gif), "-p", "x", "--out", str(self.out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("対応していない形式", r.stderr)

    # ---- 安全・エラー
    def test_missing_key_exits_2_without_network(self):
        r = self.run_cli("generate", "-p", "x", "--out", str(self.out), key=None)
        self.assertEqual(r.returncode, 2)
        self.assertIn("OPENAI_API_KEY", r.stderr)
        self.assertEqual(Mock.last, {})

    def test_dry_run_needs_no_key_and_sends_nothing(self):
        r = self.run_cli("generate", "-p", "x", "--dry-run", "--out", str(self.out), key=None)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("/images/generations", r.stdout)
        self.assertEqual(Mock.last, {})
        self.assertFalse(self.out.exists())

    def test_n_limit_and_empty_prompt(self):
        r = self.run_cli("generate", "-p", "x", "--n", "9", "--out", str(self.out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("max_n", r.stderr)
        r = self.run_cli("generate", "-p", "  ", "--out", str(self.out))
        self.assertEqual(r.returncode, 1)

    def test_api_error_shows_hint_and_never_leaks_key(self):
        Mock.fail = (404, {"error": {"message": "The model `gpt-image-2.6-sunburst` does not exist sk-test-SECRET"}})
        r = self.run_cli("generate", "-p", "x", "--out", str(self.out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("モデルID", r.stderr)
        self.assertNotIn("SECRET", r.stderr + r.stdout)

    def test_429_no_credits_gets_billing_hint(self):
        Mock.fail = (429, {"error": {"message": "You have no credits remaining. Add credits to continue."}})
        r = self.run_cli("generate", "-p", "x", "--out", str(self.out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("残高", r.stderr)
        self.assertEqual(list(self.out.glob("*.png")) if self.out.exists() else [], [])

    def test_check_and_models(self):
        r = self.run_cli("check")
        self.assertEqual(r.returncode, 0)
        self.assertIn("設定あり", r.stdout)
        self.assertNotIn("SECRET", r.stdout)
        r = self.run_cli("check", key=None)
        self.assertEqual(r.returncode, 2)
        r = self.run_cli("models")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gpt-image-2.6-sunburst", r.stdout)
        self.assertNotIn("gpt-4o", r.stdout)
        self.assertIn("一覧にあります", r.stdout)

    # ---- 部品
    def test_load_dotenv_does_not_override_and_ignores_other_keys(self):
        env_file = Path(self.tmp.name) / ".env"
        env_file.write_text('# c\nexport OPENAI_API_KEY="from-file"\nOPENAI_IMAGE_MODEL=m1\nOTHER=1\n', encoding="utf-8")
        old = dict(os.environ)
        try:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ["OPENAI_IMAGE_MODEL"] = "keep"
            loaded = image_cli.load_dotenv(env_file)
            self.assertEqual(os.environ["OPENAI_API_KEY"], "from-file")
            self.assertEqual(os.environ["OPENAI_IMAGE_MODEL"], "keep")
            self.assertNotIn("OTHER", os.environ)
            self.assertEqual(loaded, ["OPENAI_API_KEY"])
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_unique_path_never_overwrites(self):
        d = Path(self.tmp.name)
        a = image_cli.unique_path(d, "x", "png")
        a.write_bytes(b"1")
        b = image_cli.unique_path(d, "x", "png")
        self.assertNotEqual(a, b)

    def test_slugify(self):
        self.assertEqual(image_cli.slugify("日本語", "image"), "image")
        self.assertEqual(image_cli.slugify("hero banner!", "image"), "hero-banner")


if __name__ == "__main__":
    unittest.main()
