"""Expose first-run account creation in the recovered optimized Web UI."""
from pathlib import Path
import sys

replacements = {
    'a()?"账号状态":"账号登录"':
        'a()?"账号状态":t.license?.firstRun?"创建本地账号":"账号登录"',
    'b("p",{class:"field-help",style:{margin:"0"}},"登录后进入工作台")':
        'b("p",{class:"field-help",style:{margin:"0"}},'
        't.license?.firstRun?"首次使用：填写自定账号和至少8位密码，点击登录即创建本机账号，以后使用同一账号登录":"登录后进入工作台")',
    's.value?"登录中…":"登录"':
        's.value?"登录中…":t.license?.firstRun?"创建并登录":"登录"',
}


def patch(path: Path) -> None:
    text = path.read_text("utf8")
    for old, new in replacements.items():
        if old not in text:
            if new in text:
                continue
            raise ValueError(f"Expected login copy was not found in {path}")
        text = text.replace(old, new, 1)
    path.write_text(text, "utf8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch-public-login-copy.py <path-to-index-*.js>")
    patch(Path(sys.argv[1]))
