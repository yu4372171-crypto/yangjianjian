"""Create a password hash for YJJ_ADMIN_PASSWORD_HASH.

The password is read from stdin so it does not appear in the process command
line or shell history.
"""

from __future__ import annotations

import base64
import hashlib
import sys


def main() -> int:
    password = sys.stdin.readline().rstrip("\r\n")
    if len(password) < 12:
        sys.stderr.write("Password must contain at least 12 characters.\n")
        return 2
    iterations = 600_000
    salt = hashlib.sha256(
        (password + ":yangjianjian-local-account").encode("utf-8")
    ).digest()[:16]
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    sys.stdout.write(f"pbkdf2_sha256${iterations}${encoded_salt}${encoded_digest}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
