#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知乎扫码登录 CLI

用法（在项目目录下）：
  python3 zhihu_login.py              # 先试已有 cookie，失效才出二维码
  python3 zhihu_login.py --force      # 强制重新扫码（换账号 / 搬家）
  python3 zhihu_login.py --rounds 5   # 最多换 5 张二维码
  python3 zhihu_login.py --local      # 不推钉钉，只把二维码存到本地

二维码默认推到钉钉（配置里 dingtalk.enabled + settings.qr_public_base），
手机上直接用知乎 App 扫就行，扫完自动写入 zhihu_cookies.json。
"""

import sys
import argparse
import logging
from pathlib import Path

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

import yaml
from playwright.sync_api import sync_playwright
from publisher import ZhihuPublisher
from qr_service import QrPusher
from dingtalk_notify import DingTalkNotifier
from renewcat import launch_browser, new_context, new_page


class LocalSink:
    """--local：不碰钉钉，只提示二维码文件在哪"""

    def notify_login_qr(self, path):
        print("\n" + "=" * 62)
        print("  知乎登录二维码已保存：")
        print(f"  {path}")
        print("  在服务器上取回本地看：")
        print(f"  base64 -w0 {path}   # 再把输出解码成 png")
        print("=" * 62 + "\n")

    def notify_login_qr_failed(self, path):
        print(f"\n二维码在本地：{path}\n")

    def notify_login_success(self):
        print("\n登录成功喵～\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="知乎扫码登录（二维码推钉钉）")
    ap.add_argument("--force", action="store_true", help="跳过已有 cookie，强制重新扫码")
    ap.add_argument("--local", action="store_true", help="不推钉钉，只存二维码到本地")
    ap.add_argument("--rounds", type=int, default=3, help="最多换几张二维码（默认 3）")
    ap.add_argument("--wait", type=int, default=150, help="每张二维码等多少秒（默认 150）")
    args = ap.parse_args()

    cfg_path = BASE / "config.yaml"
    if not cfg_path.exists():
        print(f"找不到配置文件：{cfg_path}", file=sys.stderr)
        return 2

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    zh = cfg.get("zhihu") or {}
    settings = cfg.get("settings") or {}
    dt = cfg.get("dingtalk") or {}

    publisher = ZhihuPublisher(
        zh.get("email", ""), zh.get("password", ""),
        zh.get("username", ""), zh.get("cookies_file", ""),
    )

    # 决定「二维码往哪送」
    sink = None
    if args.local or not dt.get("enabled") or not dt.get("webhook"):
        sink = LocalSink()
    else:
        notifier = DingTalkNotifier(
            dt["webhook"], dt.get("secret", ""),
            dt.get("at_all", False), dt.get("at_mobiles", []),
        )
        sink = QrPusher(
            notifier,
            base_url=settings.get("qr_public_base", ""),
            port=int(settings.get("qr_port", 80) or 80),
        )

    print(f"知乎账号: {zh.get('email', '(未配置)')}")
    print(f"二维码推送: {'钉钉' if isinstance(sink, QrPusher) else '本地文件'}")

    # QrPusher 用 push()，LocalSink 用 notify_login_qr()，这里统一成一个回调
    on_qr = sink.push if isinstance(sink, QrPusher) else sink.notify_login_qr

    ok = False
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=False)
        ctx = new_context(browser)
        page = new_page(ctx)
        try:
            if args.force:
                ok = publisher.login_by_qr(
                    page, on_qr=on_qr,
                    rounds=args.rounds, wait=args.wait,
                )
            else:
                ok = publisher.login(page, on_qr=on_qr)
        except Exception as e:
            print(f"登录过程出错: {e}", file=sys.stderr)
        finally:
            if isinstance(sink, QrPusher):
                sink.close()
            try:
                browser.close()
            except Exception:
                pass

    if ok:
        if isinstance(sink, QrPusher):
            try:
                sink.notifier.notify_login_success()
            except Exception:
                pass
        else:
            sink.notify_login_success()
        print(f"cookie 已保存: {publisher.cookies_file}")
        return 0

    print("登录未完成（二维码过期或没扫到）。重跑一次即可，或加 --force。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
