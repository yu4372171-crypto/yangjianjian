from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicLoginCopyTests(unittest.TestCase):
    def test_first_run_login_explains_account_creation(self):
        html = (ROOT / "webui/index.html").read_text("utf8")
        self.assertIn("index-CVDv6sjN.js", html)
        javascript = (ROOT / "webui/assets/index-CVDv6sjN.js").read_text("utf8")
        self.assertIn("t.license?.firstRun", javascript)
        self.assertIn("首次使用：填写自定账号和至少8位密码", javascript)
        self.assertIn("创建并登录", javascript)


if __name__ == "__main__":
    unittest.main()
