#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二维码推送服务

知乎登录态过期时，需要把人弄去扫码。但钉钉机器人的 markdown 图片必须是
公网 http(s) 地址，所以这里做两件事：

  QrServer  —— 在本机临时起一个极端克制的 HTTP 服务（默认 80 端口），
               只对 `/<随机token>.png` 返回二维码图片，其它路径一律 404。
               登录成功后立即关掉，不长期占端口。
  QrPusher  —— 把二维码依次尝试「本机服务 → 0x0.st 图床」，拿到公网 URL
               后交给 notifier 推送到钉钉。
"""

import logging
import secrets
import threading
import http.server
from pathlib import Path

logger = logging.getLogger("sanfengyun.qr")


class _QrHandler(http.server.BaseHTTPRequestHandler):
    """只认 server.qr_path 这一个路径，其余 404"""

    server_version = "QrSrv/1.0"

    def do_GET(self):
        payload = getattr(self.server, "qr_payload", b"")
        if payload and self.path == getattr(self.server, "qr_path", ""):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except Exception:
                pass
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, fmt, *args):     # 别把访问日志刷进 run.log
        pass


class QrServer:
    """临时托管一张二维码图片"""

    def __init__(self, port: int = 80, host: str = "0.0.0.0"):
        self.port = int(port)
        self.host = host
        self._httpd = None
        self._thread = None
        self.url_path = ""

    def publish(self, img_path: str) -> str:
        """把图片换成当前要暴露的二维码，返回 URL 路径"""
        data = Path(img_path).read_bytes()
        if self._httpd is None:
            self._httpd = http.server.ThreadingHTTPServer((self.host, self.port), _QrHandler)
            self._httpd.daemon_threads = True
            self._httpd.qr_payload = b""
            self._httpd.qr_path = ""
            self._thread = threading.Thread(
                target=self._httpd.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True
            )
            self._thread.start()
            logger.info(f"[二维码] 临时图片服务已启动 {self.host}:{self.port}")
        self.url_path = f"/zhihu-qr-{secrets.token_hex(6)}.png"
        self._httpd.qr_path = self.url_path
        self._httpd.qr_payload = data
        return self.url_path

    def close(self):
        if self._httpd is None:
            return
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        try:
            self._httpd.server_close()
        except Exception:
            pass
        self._httpd = None
        logger.info("[二维码] 临时图片服务已关闭")


class QrPusher:
    """二维码 → 钉钉：本机 HTTP 服务优先，端口被占就退 0x0.st 图床"""

    def __init__(self, notifier, base_url: str = "", port: int = 80):
        self.notifier = notifier
        self.base_url = (base_url or "").strip().rstrip("/")
        self.port = int(port or 80)
        # base_url 没写端口时自动补上，避免 qr_port 非 80 时拼出打不开的地址
        if self.base_url and self.port != 80:
            from urllib.parse import urlparse
            u = urlparse(self.base_url)
            if u.port is None:
                self.base_url = f"{u.scheme}://{u.hostname}:{self.port}"
        self.server = None
        self.pushed = 0

    def push(self, img_path: str) -> bool:
        """推送一张二维码到钉钉，返回是否成功"""
        url = self._public_url(img_path)
        if not url:
            logger.warning("[二维码] 拿不到公网地址，改发文字提示")
            self._safe(lambda: self.notifier.notify_login_qr_failed(str(img_path)))
            return False
        logger.info(f"[二维码] 公网地址: {url}")
        ok = self._safe(lambda: self.notifier.notify_login_qr(url))
        self.pushed += 1
        return ok

    def _public_url(self, img_path: str) -> str:
        if self.base_url:
            try:
                if self.server is None:
                    self.server = QrServer(self.port)
                return self.base_url + self.server.publish(img_path)
            except Exception as e:
                logger.warning(f"[二维码] 本机图片服务不可用: {e}")
        return self._upload_0x0(img_path)

    @staticmethod
    def _upload_0x0(img_path: str) -> str:
        try:
            import requests
            with open(img_path, "rb") as f:
                r = requests.post(
                    "https://0x0.st",
                    files={"file": f},
                    data={"expires": "1"},
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) qr-push/1.0"},
                    timeout=25,
                )
            txt = (r.text or "").strip()
            if r.status_code == 200 and txt.startswith("http"):
                return txt
            logger.warning(f"[二维码] 0x0.st 返回 {r.status_code}: {txt[:100]}")
        except Exception as e:
            logger.warning(f"[二维码] 0x0.st 上传失败: {e}")
        return ""

    @staticmethod
    def _safe(fn) -> bool:
        try:
            fn()
            return True
        except Exception as e:
            logger.warning(f"[二维码] 钉钉推送失败: {e}")
            return False

    def close(self):
        if self.server is not None:
            self.server.close()
            self.server = None
