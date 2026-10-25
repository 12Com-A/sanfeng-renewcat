#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三丰云免费产品自动延期 - 钉钉通知模块（猫娘版）

所有消息都以「小喵」的口吻说：自称人家、称用户主人，句尾带喵～
技术信息（时间 / 状态 / 链接 / 报错）一个字不少，只是换了层皮喵。
支持加签验证，发送文本 / Markdown 消息，以及知乎二维码图片推送。
"""

import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DingTalkNotifier:
    """钉钉机器人通知（猫娘人格）"""

    def __init__(self, webhook: str, secret: str, at_all: bool = False, at_mobiles: list = None):
        self.webhook = webhook
        self.secret = secret
        self.at_all = at_all
        self.at_mobiles = at_mobiles or []
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _sign(self) -> dict:
        """生成钉钉加签参数"""
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return {"timestamp": timestamp, "sign": sign}

    def _get_url(self) -> str:
        """获取带签名的完整URL"""
        params = self._sign()
        return f"{self.webhook}&timestamp={params['timestamp']}&sign={params['sign']}"

    def send_text(self, content: str) -> bool:
        """发送文本消息"""
        data = {
            "msgtype": "text",
            "text": {"content": content},
            "at": {
                "atMobiles": self.at_mobiles,
                "isAtAll": self.at_all
            }
        }
        return self._send(data)

    def send_markdown(self, title: str, text: str) -> bool:
        """发送Markdown消息"""
        data = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
            "at": {
                "atMobiles": self.at_mobiles,
                "isAtAll": self.at_all
            }
        }
        return self._send(data)

    def _send(self, data: dict) -> bool:
        """发送请求到钉钉"""
        try:
            url = self._get_url()
            resp = self.session.post(url, json=data, timeout=10)
            result = resp.json()
            if result.get("errcode") == 0:
                logger.info("钉钉通知发送成功")
                return True
            else:
                logger.error(f"钉钉通知发送失败: {result}")
                return False
        except Exception as e:
            logger.error(f"钉钉通知异常: {e}")
            return False

    # ==================================================================
    # 扫描结果通知（扫描阶段一次性推送）
    # ==================================================================
    def notify_scan(self, products: list):
        """通知：扫描延期状态
        form_status 决定颜色：
          not_yet       → 🟢 未到时间（正常等待）
          ready         → 🔴 可延期（需要执行）
          in_review     → 🔴 审核中（需要等结果）
          not_activated → ⚫ 未开通
        """
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"### 📋 三丰云扫描结果  [{now_str}]\n",
                 "> 主人～人家把服务器的状态都看了一遍喵！\n"]
        icon_map = {
            "not_yet": "🟢",
            "ready": "🔴",
            "in_review": "🔴",
            "not_activated": "⚫",
        }
        status_map = {
            "not_yet": "🟢 还没到时间，人家安安静静等喵～",
            "ready": "🔴 可以延期啦！人家马上动手喵！",
            "in_review": "🔴 还在审核呢，人家乖乖等着喵…",
            "not_activated": "⚫ 还没开通喵，人家记下来了",
        }
        for p in products:
            fs = p.get("form_status", "not_yet")
            icon = icon_map.get(fs, "🔴")
            lines.append(f"\n{icon} **{p['name']}**")
            lines.append(f"> 到期：`{p.get('expire_time', '?')}`")
            if p.get("renew_time"):
                lines.append(f"> 可提交：`{p['renew_time']}`")
            if p.get("next_trigger"):
                lines.append(f"> 下次启动：`{p['next_trigger']}`")
            lines.append(f"> 状态：{status_map.get(fs, '?')}")
        self.send_markdown("📋 三丰云扫描结果", "\n".join(lines))

    # ==================================================================
    # 倒计时即将到期提醒（到点前 30min）
    # ==================================================================
    def notify_countdown_urgent(self, product_name: str, next_time: str, remain_str: str):
        """通知：距离触发 <=30 分钟，紧急提醒"""
        text = (
            f"### ⏰ 马上就要出发啦喵！\n\n"
            f"> **{product_name}**\n"
            f"> 下次启动：**`{next_time}`**\n"
            f"> 还剩：`{remain_str}`\n"
            f"\n主人～人家已经戴好小铃铛啦，时间一到就冲喵！(=^･ω･^=)"
        )
        self.send_markdown("⏰ 马上出发喵", text)

    # ==================================================================
    # 倒计时到点触发通知
    # ==================================================================
    def notify_trigger_fired(self, product_name: str, next_time: str):
        """通知：倒计时触发，开始执行"""
        text = (
            f"### 🚀 倒计时到啦，人家出发喵！\n\n"
            f"> **{product_name}**\n"
            f"> 计划启动：`{next_time}`\n"
            f"> 现在人家去扒三丰云的页面状态啦～"
        )
        self.send_markdown("🚀 出发喵", text)

    # ==================================================================
    # 文章已发布
    # ==================================================================
    def notify_article_posted(self, product_name: str, article_url: str, title: str):
        """通知：评测文章已发布到知乎"""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"### 📝 文章写好啦喵！\n\n"
            f"> **{product_name}**\n"
            f"> 标题：`{title}`\n"
            f"> 时间：{now_str}\n"
            f"\n👉 [主人点这里看人家写的文章喵～]({article_url})"
        )
        self.send_markdown("📝 文章发好啦喵", text)

    # ==================================================================
    # 延期提交成功
    # ==================================================================
    def notify_submit_success(self, product_name: str, article_url: str,
                              response: str = "", next_time: str = "",
                              next_run_ts: int = 0):
        """通知：延期表单提交成功"""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"### ✅ 延期成功啦喵！\n\n"
            f"> **{product_name}**\n"
            f"> 时间：{now_str}\n"
            f"> 文章：[{article_url}]({article_url})"
        )
        if next_time:
            text += f"\n> **下次启动：`{next_time}`**"
        if next_run_ts:
            text += f"\n> 🕐 **下次脚本执行：`{datetime.fromtimestamp(next_run_ts).strftime('%m-%d %H:%M')}`**"
        text += "\n\n主人快夸夸人家嘛喵～（尾巴摇摇）等三丰云审核，大概 3 小时的样子喵。"
        self.send_markdown("✅ 延期成功喵", text)

    # ==================================================================
    # 延期提交失败
    # ==================================================================
    def notify_submit_failed(self, product_name: str, error: str,
                             next_run_ts: int = 0):
        """通知：延期提交失败"""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"### ❌ 呜呜…失败啦喵\n\n"
            f"> **{product_name}**\n"
            f"> 时间：{now_str}\n"
            f"> 错误：`{error}`"
        )
        if next_run_ts:
            text += f"\n> 🕐 **下次重试：`{datetime.fromtimestamp(next_run_ts).strftime('%m-%d %H:%M')}`**"
        text += "\n\n主人帮人家看看嘛…（耳朵耷拉下来）"
        self.send_markdown("❌ 失败啦喵", text)

    # ==================================================================
    # 等待中（审核中 / 未到时间）—— 带下次执行时间
    # ==================================================================
    def notify_waiting(self, product_name: str, reason: str, next_run_ts: int):
        """通知：本次跳过，下次什么时候再来"""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"### ⏸ 这次先跳过喵～\n\n"
            f"> **{product_name}**\n"
            f"> 时间：{now_str}\n"
            f"> 原因：`{reason}`\n"
            f"> 🕐 **下次人家再来：`{datetime.fromtimestamp(next_run_ts).strftime('%m-%d %H:%M')}`**\n"
            f"\n人家先去眯一会儿喵～（蜷成一团）"
        )
        self.send_markdown("⏸ 跳过喵", text)

    # ==================================================================
    # 脚本异常
    # ==================================================================
    def notify_error(self, error: str):
        """通知：脚本异常"""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"### ⚠️ 呜哇！人家出错了喵\n\n"
            f"> 时间：{now_str}\n"
            f"> 错误：`{error}`\n"
            f"\n主人快来看看嘛…人家有点慌（抖抖耳朵）"
        )
        self.send_markdown("⚠️ 出错了喵", text)

    # ==================================================================
    # 知乎登录过期 → 推送二维码
    # ==================================================================
    def notify_login_qr(self, image_url: str):
        """通知：知乎登录态失效，把二维码图片推给主人扫"""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"### 🔑 知乎的登录饼干过期啦喵！\n\n"
            f"> 时间：{now_str}\n"
            f"> 主人～人家被知乎挡在门外了喵…\n\n"
            f"**快用知乎 App 扫一下下面这个二维码喵！**\n\n"
            f"![知乎登录二维码]({image_url})\n\n"
            f"> 扫完记得在手机上点「确认登录」哦～\n"
            f"> 二维码大概 2 分钟就过期，过期了人家会自己换一张再发给你喵（=^･ω･^=）\n"
            f"> 万一图片没显示，点这里也能打开喵：[二维码链接]({image_url})"
        )
        # 二维码标题带上口令，方便在通知列表里认出来
        self.send_markdown("🔑 主人快扫码喵！", text)

    def notify_login_qr_failed(self, local_path: str):
        """通知：二维码图片发不出去，只能给路径"""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"### 🔑 知乎登录过期了喵…（图没发出去）\n\n"
            f"> 时间：{now_str}\n"
            f"> 呜…人家没能把二维码图挂到公网上。\n"
            f"> 二维码存在服务器这里，主人 ssh 上去看一下喵：\n"
            f"> `{local_path}`\n\n"
            f"> 也可以直接跑：`cat {local_path} | base64` 再存成图片喵～"
        )
        self.send_markdown("🔑 二维码喵", text)

    # ==================================================================
    # 知乎登录结果
    # ==================================================================
    def notify_login_success(self):
        """通知：扫码成功，登录恢复"""
        text = (
            "### 🎉 主人扫好啦，人家又能进去了喵！\n\n"
            "> 知乎登录态已经存好，接下来人家安心干活喵～（蹭蹭）"
        )
        self.send_markdown("🎉 登录恢复喵", text)
