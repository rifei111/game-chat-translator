"""手机端静态页面服务（PWA）：只监听局域网，自动顺延端口。"""
from __future__ import annotations

import functools
import logging
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from .paths import phone_path

log = logging.getLogger("phone")


class PhoneServer:
    def __init__(self, port: int):
        handler = functools.partial(SimpleHTTPRequestHandler, directory=phone_path())
        handler.log_message = lambda *a, **k: None

        class Server(ThreadingHTTPServer):
            allow_reuse_address = True

        self.server = Server(("0.0.0.0", port), handler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever,
                                        daemon=True, name="phone-server")

    def start(self):
        self._thread.start()
        log.info("手机端服务已启动：%s", self.port)

    def stop(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
