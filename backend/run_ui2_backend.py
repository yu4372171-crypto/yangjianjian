"""YangJianJian desktop sidecar.

The WPF host communicates through newline-delimited JSON on private stdio
pipes. Standard output is reserved exclusively for protocol packets; logs go
to standard error.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
for stream in (sys.stdin, sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PROTOCOL_OUT = sys.stdout
sys.stdout = sys.stderr
WRITE_LOCK = threading.Lock()


def send(packet: dict) -> None:
    from app.ui2.common import json_value

    with WRITE_LOCK:
        PROTOCOL_OUT.write(json.dumps(json_value(packet), ensure_ascii=False) + "\n")
        PROTOCOL_OUT.flush()


def main() -> int:
    from app.config.settings import AppSettings
    from app.services.context import AppContext
    from app.services.registry import Services
    from app.ui2.api import BusinessAPI
    from app.ui2.common import BridgeError
    from app.utils.common import get_logger, setup_logging

    settings = AppSettings()
    setup_logging(settings.get("log_level", "INFO"))
    logger = get_logger("yangjianjian.protocol")
    ctx = AppContext(settings)
    api = BusinessAPI(
        ctx,
        Services(ctx),
        lambda name, data: send({"event": name, "data": data}),
    )
    stopped = threading.Event()
    request_lock = threading.Lock()

    def read_requests() -> None:
        previous_action = "?"
        for line in sys.stdin:
            request_id = None
            try:
                if len(line) > 8 * 1024 * 1024:
                    raise BridgeError("REQUEST_TOO_LARGE", "请求过大")
                request = json.loads(line)
                request_id = request["id"]
                action = request["action"]
                previous_action = action
                data = request.get("data") or {}
                if not isinstance(data, dict):
                    raise BridgeError("INVALID_REQUEST", "请求参数必须是对象")
                with request_lock:
                    result = api.invoke(action, data)
                send(
                    {
                        "id": request_id,
                        "success": True,
                        "data": result,
                        "error": None,
                    }
                )
                if action == "app.shutdown":
                    break
            except Exception as error:
                logger.exception("Bridge failure: action=%s", previous_action)
                send(
                    {
                        "id": request_id,
                        "success": False,
                        "data": None,
                        "error": {
                            "code": getattr(error, "code", "BUSINESS_ERROR"),
                            "message": str(error) or error.__class__.__name__,
                        },
                    }
                )
        api.tasks.close()
        stopped.set()

    worker = threading.Thread(
        target=read_requests,
        name="yangjianjian-requests",
        daemon=True,
    )
    worker.start()
    send(
        {
            "event": "backend.ready",
            "data": {"name": "羊剪剪", "version": api.version},
        }
    )
    stopped.wait()
    ctx.close_project()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as error:
        sys.stderr.write(f"YangJianJian backend failed: {error}\n")
        raise
