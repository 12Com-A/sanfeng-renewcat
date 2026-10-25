#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块2: publisher - 知乎自动发文
功能:
  1. 登录知乎（账号密码 + 滑块验证码，失败可用 Cookie 或扫码兜底）
  2. 把 Markdown 正文转成富文本，写进知乎「写文章」编辑器并发布
  3. 返回文章URL和截图路径（给三丰云延期用）
"""

import re
import os
import json
import time
import random
import logging
from pathlib import Path

logger = logging.getLogger("sanfengyun.publisher")

# URL 正则：避免把中文标点一起吞进链接里
URL_PATTERN = r"""https?://[^\s<>"'）)，。；：！？]+"""


class ZhihuPublisher:
    """知乎发帖器（替代原来的博客园自动发文）"""

    HOME_URL = "https://www.zhihu.com/"
    LOGIN_URL = "https://www.zhihu.com/signin?next=%2F"
    WRITE_URL = "https://zhuanlan.zhihu.com/write"

    # 标题输入框
    TITLE_SELECTORS = (
        'textarea[placeholder*="标题"]',
        'input[placeholder*="标题"]',
        "textarea.WriteIndex-titleInput",
        ".WriteIndex-titleInput textarea",
    )

    # 正文编辑器（知乎用 Draft.js，body 是 contenteditable）
    EDITOR_SELECTORS = (
        "div.public-DraftEditor-content",
        "div[contenteditable='true']",
        ".WriteIndex-editor [contenteditable='true']",
        "div[data-contents='true']",
    )

    # 滑块验证码的手柄（网易易盾 / 极验 / 阿里云 / 知乎自带）
    SLIDER_SELECTORS = (
        ".yidun_slider",
        ".yidun_slider__icon",
        ".geetest_slider_button",
        ".geetest_radar_btn",
        "#aliyunCaptcha-checkbox-left",
        ".aliyunCaptcha-checkbox-left",
        ".slide-verify-slider-mask-item",
        "[class*='slider'] [class*='button']",
    )

    def __init__(self, email: str, password: str, username: str = "",
                 cookies_file: str = ""):
        self.email = email            # 知乎登录手机号 / 邮箱
        self.password = password
        self.username = username      # 知乎昵称或主页 token（用于兜底取文章链接）
        self.cookies_file = cookies_file or str(
            Path(__file__).parent / "zhihu_cookies.json"
        )

    # --------------------------------------------------------------
    # 小工具
    # --------------------------------------------------------------
    @staticmethod
    def _sd() -> Path:
        """截图目录"""
        d = Path(__file__).parent / "screenshots"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _first(page, selectors):
        """返回第一个可见的 locator，找不到返回 None"""
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    @staticmethod
    def _text(page) -> str:
        try:
            return page.inner_text("body") or ""
        except Exception:
            return ""

    # --------------------------------------------------------------
    # 登录
    # --------------------------------------------------------------
    def login(self, page, on_qr=None) -> bool:
        """登录知乎：先试 Cookie，再试账号密码，最后扫码（可推送二维码到钉钉）"""
        logger.info("[知乎] 检查登录状态...")
        try:
            page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
        except Exception as e:
            logger.error(f"[知乎] 打开首页失败: {e}")

        if self._is_logged_in(page):
            self._remember_token(page)
            logger.info("[知乎] 已登录")
            return True

        # 1) 复用本地 Cookie（省去验证码）
        if self._load_cookies(page):
            try:
                page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)
            except Exception:
                pass
            if self._is_logged_in(page):
                self._remember_token(page)
                logger.info("[知乎] ✅ Cookie 登录成功")
                return True
            logger.warning("[知乎] Cookie 已失效，改用账号密码登录")

        # 2) 账号密码
        if self._password_login(page):
            self._remember_token(page)
            self._save_cookies(page)
            return True

        # 3) 二维码：把码推给主人（钉钉），然后等扫码
        return self.login_by_qr(page, on_qr=on_qr)

    # --------------------------------------------------------------
    # 二维码登录（可把二维码推给钉钉）
    # --------------------------------------------------------------
    def login_by_qr(self, page, on_qr=None, rounds: int = 3, wait: int = 150) -> bool:
        """
        二维码登录。
        on_qr: 拿到二维码图片路径后的回调（一般是上传并推送到钉钉），
               每一轮都会调用一次，方便主人扫到最新那张。
        """
        logger.info("[知乎] 改用二维码登录喵...")
        for i in range(rounds):
            path = self._open_qr(page)
            if not path:
                logger.warning("[知乎] 没截到二维码")
            else:
                logger.info(f"[知乎] 二维码已备好（第 {i + 1}/{rounds} 张）: {path}")
                if on_qr is not None:
                    try:
                        on_qr(path)
                    except Exception as e:
                        logger.warning(f"[知乎] 二维码推送失败: {e}")

            if self._wait_for_login(page, timeout=wait):
                self._remember_token(page)
                self._save_cookies(page)
                logger.info("[知乎] ✅ 扫码登录成功")
                return True
            logger.info(f"[知乎] 第 {i + 1} 轮二维码没扫，换一张重发")

        logger.error("[知乎] 扫码登录超时")
        try:
            page.screenshot(path=str(self._sd() / "zhihu_login_fail.png"))
        except Exception:
            pass
        return False

    def _open_qr(self, page) -> str:
        """打开登录页 → 切到扫码登录 → 截下二维码（顺手放大，方便手机扫）"""
        try:
            page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3500)
        except Exception as e:
            logger.warning(f"[知乎] 打开登录页失败: {e}")

        for text in ("扫码登录", "二维码登录"):
            try:
                tab = page.get_by_text(text, exact=True).first
                if tab.count() and tab.is_visible():
                    tab.click()
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                continue

        path = self._sd() / "zhihu_qr_login.png"
        for sel in (".SignFlow-qrcode", ".Qrcode", ".SignFlow-qrcode img",
                    "img[alt*='二维码']", "canvas"):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.screenshot(path=str(path))
                    self._upscale(path)
                    return str(path)
            except Exception:
                continue

        try:
            page.screenshot(path=str(path))
            return str(path)
        except Exception:
            return ""

    @staticmethod
    def _upscale(img_path, target: int = 560):
        """二维码截图通常只有 140px，放大到 target 宽才好扫"""
        try:
            from PIL import Image
        except ImportError:
            return
        try:
            img = Image.open(img_path)
            if img.width >= target * 0.8:
                return
            k = max(2, round(target / img.width))
            img.resize((img.width * k, img.height * k), Image.NEAREST).save(img_path)
        except Exception:
            pass

    def _password_login(self, page, timeout: int = 45) -> bool:
        """账号密码登录（含滑块验证码处理）"""
        logger.info("[知乎] 账号密码登录...")
        try:
            page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            logger.error(f"[知乎] 打开登录页失败: {e}")
            return False

        # 切到「密码登录」页签
        for text in ("密码登录", "账号密码登录"):
            try:
                tab = page.get_by_text(text, exact=True).first
                if tab.count() and tab.is_visible():
                    tab.click()
                    page.wait_for_timeout(1200)
                    logger.info(f"[知乎] 已切换到「{text}」")
                    break
            except Exception:
                continue

        # 填账号密码
        try:
            user = self._first(page, (
                'input[name="username"]',
                'input[placeholder*="手机号"]',
                'input[placeholder*="邮箱"]',
                'input[autocomplete="username"]',
            ))
            if not user:
                logger.error("[知乎] 找不到账号输入框")
                return False
            user.click()
            page.keyboard.type(self.email, delay=60)

            pwd = self._first(page, (
                'input[name="password"]',
                'input[type="password"]',
                'input[placeholder*="密码"]',
            ))
            if not pwd:
                logger.error("[知乎] 找不到密码输入框")
                return False
            pwd.click()
            page.keyboard.type(self.password, delay=60)
            page.wait_for_timeout(300)

            # 勾选「我已阅读并同意」协议（新版登录框有）
            try:
                box = page.locator(
                    '.SignFlow-agreementButton, .SignFlow-agreement input[type="checkbox"], '
                    'label:has-text("同意") input[type="checkbox"]'
                ).first
                if box.count() and box.is_visible() and not box.is_checked():
                    box.check()
                    page.wait_for_timeout(300)
            except Exception:
                pass

            submit = self._first(page, (
                "button.SignFlow-submitButton",
                'button[type="submit"]',
                'button:has-text("登录")',
            ))
            if submit:
                submit.click()
            else:
                page.keyboard.press("Enter")
            logger.info("[知乎] 已提交登录表单")
        except Exception as e:
            logger.error(f"[知乎] 填表单失败: {e}")
            return False

        page.wait_for_timeout(3000)

        # 轮询结果，中途遇到滑块就拖
        deadline = time.time() + timeout
        slider_tries = 0
        while time.time() < deadline:
            if self._is_logged_in(page):
                logger.info("[知乎] ✅ 登录成功")
                return True
            body = self._text(page)
            if any(k in body for k in ("滑动", "拖动", "拼图", "验证")):
                if slider_tries < 3:
                    slider_tries += 1
                    logger.info("[知乎] 处理滑块验证...")
                    self._solve_slider(page)
                    continue
            page.wait_for_timeout(2000)

        return self._is_logged_in(page)

    def _solve_slider(self, page, max_retry: int = 3) -> bool:
        """拖动滑块完成验证码（模拟人类鼠标轨迹）"""
        for _ in range(max_retry):
            if "验证成功" in self._text(page):
                return True

            handle = self._first(page, self.SLIDER_SELECTORS)
            if not handle:
                page.wait_for_timeout(1500)
                continue

            try:
                box = handle.bounding_box()
            except Exception:
                box = None
            if not box:
                page.wait_for_timeout(1500)
                continue

            track_w = self._track_width(handle) or 300
            distance = max(track_w - box["width"] - random.randint(3, 10), 40)
            self._drag(page, box, distance)
            page.wait_for_timeout(3500)

            if "验证成功" in self._text(page):
                logger.info("[知乎] ✅ 滑块验证通过")
                return True

            page.wait_for_timeout(1500)
        logger.warning("[知乎] 滑块验证未通过")
        return False

    @staticmethod
    def _track_width(handle) -> float:
        """取滑块轨道的宽度（手柄父容器的宽度）"""
        try:
            return handle.evaluate(
                """el => {
                    const p = el.closest("[class*='slider'], [class*='Slider'], [class*='captcha'], [class*='Captcha']") || el.parentElement;
                    return p ? (p.getBoundingClientRect().width || 0) : 0;
                }"""
            ) or 0
        except Exception:
            return 0

    @staticmethod
    def _drag(page, box, distance: float) -> None:
        """从手柄位置人性化拖到右侧"""
        sx = box["x"] + box["width"] / 2 + random.uniform(-2, 2)
        sy = box["y"] + box["height"] / 2 + random.uniform(-2, 2)
        page.mouse.move(sx - random.randint(40, 90), sy + random.randint(-20, 20))
        page.wait_for_timeout(random.randint(200, 400))
        page.mouse.move(sx, sy)
        page.wait_for_timeout(random.randint(100, 250))
        page.mouse.down()
        page.wait_for_timeout(random.randint(120, 220))

        steps = random.randint(22, 38)
        for i in range(1, steps + 1):
            t = i / steps
            ease = t * t * (3 - 2 * t)          # smoothstep，先慢后快再慢
            x = sx + distance * ease + random.uniform(-1.5, 1.5)
            y = sy + random.uniform(-1.2, 1.2)
            page.mouse.move(x, y)
            page.wait_for_timeout(random.randint(8, 26))
        page.wait_for_timeout(random.randint(150, 350))
        page.mouse.up()
        page.wait_for_timeout(random.randint(600, 1200))

    def _wait_for_login(self, page, timeout: int = 180) -> bool:
        """等待用户扫码 / 手动登录"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._is_logged_in(page):
                return True
            page.wait_for_timeout(3000)
        return False

    @staticmethod
    def _is_logged_in(page) -> bool:
        """是否已登录：优先看 z_c0 这个登录态 Cookie"""
        try:
            for c in page.context.cookies("https://www.zhihu.com"):
                if c.get("name") == "z_c0" and c.get("value"):
                    return True
        except Exception:
            pass
        try:
            return bool(page.evaluate(
                """() => !!document.querySelector(
                    '.AppHeader-profile, .AppHeader-userInfo, .AppHeader-avatar, .AppHeaderV2-profile'
                )"""
            ))
        except Exception:
            return False

    def _remember_token(self, page) -> None:
        """记下主页 token，发布后万一拿不到链接可以兜底查"""
        if self.username:
            return
        token = self._detect_token(page)
        if token:
            self.username = token
            logger.info(f"[知乎] 当前账号: {token}")

    @staticmethod
    def _detect_token(page) -> str:
        """从页面头部头像链接推断主页 token"""
        try:
            return page.evaluate(
                r"""() => {
                    const a = document.querySelector(
                        '.AppHeader-profile a[href*="/people/"], a[href*="zhihu.com/people/"]'
                    );
                    if (!a) return '';
                    const m = (a.getAttribute('href') || '').match(/people\/([^/?#]+)/);
                    return m ? decodeURIComponent(m[1]) : '';
                }"""
            ) or ""
        except Exception:
            return ""

    # --------------------------------------------------------------
    # Cookie 持久化
    # --------------------------------------------------------------
    def _load_cookies(self, page) -> bool:
        p = Path(self.cookies_file)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[知乎] Cookie 文件解析失败: {e}")
            return False

        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not isinstance(cookies, list) or not cookies:
            return False

        now = time.time()
        clean = []
        for c in cookies:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            expires = c.get("expires")
            if isinstance(expires, (int, float)) and 0 < expires < now:
                continue
            item = {
                k: c[k]
                for k in ("name", "value", "domain", "path", "httpOnly", "secure", "sameSite")
                if k in c
            }
            item.setdefault("domain", ".zhihu.com")
            item.setdefault("path", "/")
            if isinstance(expires, (int, float)) and expires > 0:
                item["expires"] = expires
            clean.append(item)

        if not clean:
            logger.warning("[知乎] Cookie 全部过期")
            return False

        try:
            page.context.add_cookies(clean)
            logger.info(f"[知乎] 已载入 {len(clean)} 条 Cookie")
            return True
        except Exception as e:
            logger.warning(f"[知乎] Cookie 载入失败: {e}")
            return False

    def _save_cookies(self, page) -> None:
        try:
            cookies = page.context.cookies()
            Path(self.cookies_file).write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info(f"[知乎] 登录 Cookie 已保存: {self.cookies_file}")
        except Exception as e:
            logger.debug(f"[知乎] Cookie 保存失败: {e}")

    # --------------------------------------------------------------
    # 发文
    # --------------------------------------------------------------
    def publish(self, page, title: str, content: str,
                sanitize_from: str = "", sanitize_to: str = "",
                image_path: str = "") -> tuple:
        """
        在知乎发布文章
        返回: (success: bool, article_url: str, screenshot_path: str)
        """
        shot_dir = self._sd()
        screenshot_path = str(shot_dir / "zhihu_article.png")

        # 替换敏感词
        if sanitize_from and sanitize_from != sanitize_to:
            title = title.replace(sanitize_from, sanitize_to)
            content = content.replace(sanitize_from, sanitize_to)

        # 知乎标题上限 100 字
        title = (title or "").strip()[:100]

        try:
            logger.info("[知乎] 进入写文章页...")
            page.goto(self.WRITE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(6000)

            if "signin" in page.url or "zhuanlan.zhihu.com" not in page.url:
                logger.error(f"[知乎] ❌ 打不开写文章页（可能未登录）: {page.url}")
                try:
                    page.screenshot(path=str(shot_dir / "zhihu_publish_fail.png"))
                except Exception:
                    pass
                return False, "", screenshot_path

            # ---- 填标题 ----
            title_box = self._first(page, self.TITLE_SELECTORS)
            if not title_box:
                logger.error("[知乎] 找不到标题输入框")
                try:
                    page.screenshot(path=str(shot_dir / "zhihu_publish_fail.png"))
                except Exception:
                    pass
                return False, "", screenshot_path
            title_box.click()
            # 清掉可能的草稿标题，避免和旧内容拼在一起
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.wait_for_timeout(200)
            page.keyboard.type(title, delay=25)
            logger.info(f"[知乎] 标题: {title}")
            page.wait_for_timeout(800)

            # ---- 填正文（Markdown → 富文本）----
            html = self._md_to_html(content)
            plain = self._md_to_plain(content)
            if not self._insert_content(page, html, plain):
                logger.error("[知乎] 正文写入失败")
                try:
                    page.screenshot(path=str(shot_dir / "zhihu_publish_fail.png"))
                except Exception:
                    pass
                return False, "", screenshot_path
            logger.info(f"[知乎] 正文已写入，长度约 {len(plain)} 字")

            # ---- 配图：插一张三丰云官网截图，做到图文并茂 ----
            # 三丰云审核规则第 4 条：含官网截图 / 图文并茂的评测优先通过
            # 全程 best-effort，插不进去也照常发布，绝不影响主流程
            try:
                img = image_path or self._reference_screenshot(page)
                if img and os.path.exists(img):
                    if self._insert_image(page, img):
                        logger.info(f"[知乎] ✅ 已插入配图: {img}")
                    else:
                        logger.warning("[知乎] 配图插入失败，按纯文字发布")
                else:
                    logger.warning("[知乎] 没有可用的配图，按纯文字发布")
            except Exception as e:
                logger.warning(f"[知乎] 配图处理异常（忽略，继续发布）: {e}")

            page.wait_for_timeout(1200)

            # ---- 发布 ----
            if not self._click_publish(page):
                logger.error("[知乎] 发布按钮点击失败")
                try:
                    page.screenshot(path=str(shot_dir / "zhihu_publish_fail.png"))
                except Exception:
                    pass
                return False, "", screenshot_path

            success, article_url = self._wait_published(page, timeout=60)

            if not success:
                logger.error(f"[知乎] ❌ 发布失败: {self._collect_errors(page)}")
                try:
                    page.screenshot(path=str(shot_dir / "zhihu_publish_fail.png"))
                except Exception:
                    pass
                # 即使没拿到链接，只要成功页出现了也截一张后台图
                try:
                    page.screenshot(path=screenshot_path, full_page=True)
                except Exception:
                    pass
                return False, "", screenshot_path

            logger.info(f"[知乎] ✅ 发布成功: {article_url}")

        except Exception as e:
            logger.error(f"[知乎] ❌ 发布异常: {e}")
            try:
                page.screenshot(path=str(shot_dir / "zhihu_publish_fail.png"))
            except Exception:
                pass
            return False, "", screenshot_path

        # 保存文章页面截图（给三丰云延期用）
        # 🔒 关键：必须跳到文章**公开页**截图，不能在后台编辑页截
        try:
            logger.info(f"[知乎] 跳转到文章公开页截图: {article_url}")
            page.goto(article_url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(2500)
            self._dismiss_modal(page)        # 关掉「发布成功」弹窗，别挡住文章
            self._load_all_images(page)      # 滚动触发懒加载，等配图都渲染出来
            page.screenshot(path=screenshot_path, full_page=True)
            # 压缩到 JPG + 限制 500KB 内（三丰云审核偏好清晰+小）
            try:
                self._compress_screenshot(screenshot_path, max_kb=500)
            except Exception as e:
                logger.warning(f"[知乎] 截图压缩失败（继续用原图）: {e}")
            logger.info(f"[知乎] ✅ 公开页长截图: {screenshot_path}")
        except Exception as e:
            logger.warning(f"[知乎] 公开页截图失败（改用当前页）: {e}")
            try:
                page.screenshot(path=screenshot_path, full_page=True)
            except Exception:
                pass

        return True, article_url, screenshot_path

    def _insert_content(self, page, html: str, plain: str) -> bool:
        """把富文本写进 Draft.js 编辑器，按 剪贴板 → 粘贴事件 → 纯文本 依次降级"""
        editor = self._first(page, self.EDITOR_SELECTORS)
        if not editor:
            logger.error("[知乎] 找不到正文编辑器")
            return False

        expect = len(re.sub(r"\s+", "", plain))

        # 方案 1：写系统剪贴板 + Ctrl+V（真实粘贴，Draft.js 能正确解析 HTML）
        if self._paste_by_clipboard(page, html, plain):
            got = self._content_len(page)
            if got >= expect * 0.5:
                logger.info(f"[知乎] 富文本粘贴成功（{got} 字）")
                return True
            logger.warning(f"[知乎] 剪贴板粘贴内容偏少（{got}/{expect}），换方案")

        # 方案 2：直接派发 paste 事件
        if self._paste_by_event(page, html, plain):
            got = self._content_len(page)
            if got >= expect * 0.5:
                logger.info(f"[知乎] 粘贴事件写入成功（{got} 字）")
                return True
            logger.warning(f"[知乎] 粘贴事件内容偏少（{got}/{expect}），换方案")

        # 方案 3：兜底，逐字输入纯文本
        logger.warning("[知乎] 富文本写入失败，改用纯文本输入")
        try:
            self._clear_editor(page)
            page.keyboard.type(plain, delay=3)
            page.wait_for_timeout(1500)
            return self._content_len(page) > 0
        except Exception as e:
            logger.error(f"[知乎] 纯文本输入失败: {e}")
            return False

    def _clear_editor(self, page) -> None:
        try:
            editor = self._first(page, self.EDITOR_SELECTORS)
            if editor:
                editor.click()
        except Exception:
            pass
        try:
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.wait_for_timeout(300)
        except Exception:
            pass

    def _paste_by_clipboard(self, page, html: str, plain: str) -> bool:
        """把 HTML 写进剪贴板，再按 Ctrl+V 粘贴"""
        try:
            page.context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://zhuanlan.zhihu.com",
            )
        except Exception:
            pass

        try:
            ok = page.evaluate(
                """async ({html, plain}) => {
                    try {
                        const items = {
                            'text/html': new Blob([html], {type: 'text/html'}),
                            'text/plain': new Blob([plain], {type: 'text/plain'}),
                        };
                        await navigator.clipboard.write([new ClipboardItem(items)]);
                        return true;
                    } catch (e) {
                        return false;
                    }
                }""",
                {"html": html, "plain": plain},
            )
        except Exception:
            ok = False
        if not ok:
            return False

        try:
            editor = self._first(page, self.EDITOR_SELECTORS)
            if not editor:
                return False
            self._clear_editor(page)
            page.keyboard.press("Control+V")
            page.wait_for_timeout(3000)
            return True
        except Exception as e:
            logger.debug(f"[知乎] 剪贴板粘贴失败: {e}")
            return False

    def _paste_by_event(self, page, html: str, plain: str) -> bool:
        """构造 paste 事件直接派发到编辑器"""
        try:
            self._clear_editor(page)
            res = page.evaluate(
                """({html, plain}) => {
                    const el = document.querySelector('div.public-DraftEditor-content')
                            || document.querySelector('div[contenteditable="true"]');
                    if (!el) return 'no-editor';
                    el.focus();
                    const dt = new DataTransfer();
                    dt.setData('text/html', html);
                    dt.setData('text/plain', plain);
                    const ev = new ClipboardEvent('paste', {
                        clipboardData: dt, bubbles: true, cancelable: true,
                    });
                    el.dispatchEvent(ev);
                    return 'ok';
                }""",
                {"html": html, "plain": plain},
            )
            page.wait_for_timeout(2500)
            return res == "ok"
        except Exception as e:
            logger.debug(f"[知乎] 粘贴事件失败: {e}")
            return False

    @staticmethod
    def _content_len(page) -> int:
        """编辑器里实际有多少字（去掉空白）"""
        try:
            text = page.evaluate(
                """() => {
                    const el = document.querySelector('div.public-DraftEditor-content')
                            || document.querySelector('div[contenteditable="true"]');
                    return el ? (el.innerText || '') : '';
                }"""
            )
            return len(re.sub(r"\s+", "", text or ""))
        except Exception:
            return 0

    # --------------------------------------------------------------
    # 配图
    # --------------------------------------------------------------
    def _reference_screenshot(self, page, url: str = "https://www.sanfengyun.com") -> str:
        """用同 context 另开一个标签页截三丰云官网，作为文章配图"""
        path = self._sd() / "sf_home.png"
        tmp_page = None
        try:
            tmp_page = page.context.new_page()
            tmp_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                tmp_page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            tmp_page.wait_for_timeout(2500)
            tmp_page.screenshot(path=str(path), full_page=False)
            logger.info(f"[知乎] 已截取三丰云官网配图: {path}")
            return str(path)
        except Exception as e:
            logger.warning(f"[知乎] 三丰云官网截图失败: {e}")
            return ""
        finally:
            if tmp_page is not None:
                try:
                    tmp_page.close()
                except Exception:
                    pass

    def _insert_image(self, page, img_path: str) -> bool:
        """把图片插到正文末尾：优先塞 file input，再退回「图片」按钮走文件选择器"""
        # 光标移到正文末尾
        try:
            editor = self._first(page, self.EDITOR_SELECTORS)
            if editor:
                editor.click()
                page.keyboard.press("Control+End")
                page.wait_for_timeout(500)
        except Exception:
            pass

        # 方案 1：直接给隐藏的 file input 塞文件
        for sel in ('input[type="file"][accept*="image"]', 'input[type="file"]'):
            try:
                loc = page.locator(sel).first
                if loc.count():
                    loc.set_input_files(img_path)
                    page.wait_for_timeout(8000)
                    if self._image_count(page) > 0:
                        return True
            except Exception:
                continue

        # 方案 2：点工具栏「图片」按钮 → 文件选择器
        try:
            with page.expect_file_chooser(timeout=8000) as chooser_info:
                clicked = False
                for sel in ('button[aria-label*="图片"]',
                            '[class*="Toolbar"] button:has-text("图片")',
                            'button:has-text("图片")',
                            "button:has-text('上传图片')"):
                    loc = self._first(page, (sel,))
                    if loc:
                        loc.click()
                        clicked = True
                        break
                if not clicked:
                    raise RuntimeError("找不到图片按钮")
            chooser_info.value.set_files(img_path)
            page.wait_for_timeout(10000)
            return self._image_count(page) > 0
        except Exception as e:
            logger.warning(f"[知乎] 图片上传失败: {e}")
            return False

    @staticmethod
    def _image_count(page) -> int:
        """正文里现在有几张图"""
        try:
            return int(page.evaluate(
                """() => document.querySelectorAll(
                    'div.public-DraftEditor-content img, div[contenteditable="true"] img'
                ).length"""
            ))
        except Exception:
            return 0

    def _click_publish(self, page) -> bool:
        """点「发布」，必要时在发布设置面板里选专栏再确认"""
        clicked = False
        for sel in ("button:has-text('发布')", ".WriteIndex-publishButton",
                    "button[class*='Publish']", ".PublishPanel-button"):
            loc = self._first(page, (sel,))
            if not loc:
                continue
            try:
                loc.click()
                clicked = True
                logger.info("[知乎] 点击发布...")
                break
            except Exception:
                continue

        if not clicked:
            return False

        page.wait_for_timeout(2500)

        # 发布设置面板：选第一个专栏（不选会发布不了）
        try:
            panel = self._first(page, (
                'div[role="dialog"]',
                "[class*='PublishPanel']",
                "[class*='Modal']",
            ))
            if panel:
                col = self._first(page, (
                    "[class*='PublishPanel'] [class*='Radio']",
                    "[class*='PublishPanel'] [class*='column'] label",
                    'div[role="dialog"] label',
                ))
                if col:
                    col.click()
                    page.wait_for_timeout(800)
                    logger.info("[知乎] 已选择发布专栏")
        except Exception:
            pass

        # 面板里再点一次「发布」确认
        # 优先用知乎发布面板已知的按钮 class，再退回按文案找
        for sel in (".PublishPanel-stepTwoButton", "button[class*='stepTwo']"):
            loc = self._first(page, (sel,))
            if loc:
                try:
                    loc.click()
                    page.wait_for_timeout(2500)
                    return True
                except Exception:
                    continue

        # 退路：发布面板内所有按钮里，挑文案含「发布」的那个（从后往前找）
        try:
            panel_btns = page.locator("[class*='PublishPanel'] button")
            total = panel_btns.count()
        except Exception:
            total = 0

        for i in range(total - 1, -1, -1):
            btn = panel_btns.nth(i)
            try:
                text = (btn.inner_text() or "").strip()
                if btn.is_visible() and "发布" in text and "设置" not in text:
                    btn.click()
                    page.wait_for_timeout(2500)
                    return True
            except Exception:
                continue

        # 最后退回按 role 精确定位
        try:
            btns = page.get_by_role("button", name="发布", exact=True)
            count = btns.count()
        except Exception:
            count = 0

        for i in range(count - 1, -1, -1):
            btn = btns.nth(i)
            try:
                if btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(2500)
                    return True
            except Exception:
                continue

        return True

    def _wait_published(self, page, timeout: int = 60) -> tuple:
        """等发布完成，返回 (success, article_url)"""
        deadline = time.time() + timeout
        toast = False

        while time.time() < deadline:
            m = re.search(r"zhuanlan\.zhihu\.com/p/(\d+)", page.url or "")
            if m:
                return True, f"https://zhuanlan.zhihu.com/p/{m.group(1)}"

            body = self._text(page)
            if "发布成功" in body or "已发布" in body:
                toast = True
                break
            page.wait_for_timeout(1500)

        if toast:
            page.wait_for_timeout(2000)
            url = self._url_from_page(page) or self._url_from_posts(page)
            if url:
                return True, url
        return False, ""

    @staticmethod
    def _url_from_page(page) -> str:
        """从当前页面的链接里找刚发的文章地址"""
        try:
            href = page.evaluate(
                r"""() => {
                    for (const a of document.querySelectorAll('a[href*="/p/"]')) {
                        const m = (a.getAttribute('href') || '').match(/zhuanlan\.zhihu\.com\/p\/(\d+)/);
                        if (m) return 'https://zhuanlan.zhihu.com/p/' + m[1];
                    }
                    return '';
                }"""
            )
            return href or ""
        except Exception:
            return ""

    def _url_from_posts(self, page) -> str:
        """兜底：去我的主页文章列表取最新一篇"""
        if not self.username:
            return ""
        try:
            import urllib.parse
            token = urllib.parse.quote(self.username)
            page.goto(f"https://www.zhihu.com/people/{token}/posts",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            return self._url_from_page(page)
        except Exception:
            return ""

    @staticmethod
    def _dismiss_modal(page) -> None:
        """关掉知乎的「发布成功 / 分享」弹窗，避免挡住文章截图"""
        for sel in ('button[aria-label="关闭"]', '[aria-label="Close"]',
                    ".Modal-closeButton", ".Modal-close",
                    '[class*="Modal"] [class*="close"]'):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click()
                    page.wait_for_timeout(700)
                    return
            except Exception:
                continue
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            pass

    @staticmethod
    def _load_all_images(page, timeout_ms: int = 8000) -> None:
        """知乎图片是懒加载的：滚到底触发加载，等所有 img 完成后再截长图"""
        try:
            page.evaluate(
                """() => new Promise(resolve => {
                    let y = 0;
                    const step = () => {
                        window.scrollBy(0, Math.round(window.innerHeight * 0.8));
                        y += Math.round(window.innerHeight * 0.8);
                        if (y < document.body.scrollHeight) {
                            setTimeout(step, 120);
                        } else {
                            resolve();
                        }
                    };
                    step();
                })""")
            page.wait_for_timeout(1200)
            page.evaluate(
                """(timeout) => Promise.all(Array.from(document.images)
                    .filter(i => !i.complete)
                    .map(i => new Promise(r => {
                        i.onload = i.onerror = r;
                        setTimeout(r, timeout);
                    })))""",
                timeout_ms,
            )
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(800)
        except Exception:
            pass

    def _collect_errors(self, page) -> list:
        """捞页面上可能出现的错误提示"""
        try:
            return page.evaluate(
                """() => {
                    const out = [];
                    document.querySelectorAll(
                        '[class*="error"], [class*="Error"], [class*="warning"], '
                        + '[class*="Message"], [class*="toast"]'
                    ).forEach(el => {
                        const t = (el.innerText || '').trim();
                        if (t && t.length < 200 && !t.includes('成功')) out.push(t);
                    });
                    return out.slice(0, 6);
                }"""
            )
        except Exception:
            return []

    # --------------------------------------------------------------
    # Markdown 转换
    # --------------------------------------------------------------
    @classmethod
    def _md_to_html(cls, md: str) -> str:
        """极简 Markdown → HTML（只覆盖本程序生成的文章用到的语法）"""
        out = []
        para = []
        list_type = None

        def flush_para():
            if para:
                out.append("<p>" + "<br>".join(cls._inline(x) for x in para) + "</p>")
                para.clear()

        def close_list():
            nonlocal list_type
            if list_type:
                out.append(f"</{list_type}>")
                list_type = None

        for raw in (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw.strip()
            if not line:
                flush_para()
                close_list()
                continue

            if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", line):
                flush_para()
                close_list()
                out.append("<hr>")
                continue

            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                flush_para()
                close_list()
                level = min(len(m.group(1)), 6)
                out.append(f"<h{level}>{cls._inline(m.group(2))}</h{level}>")
                continue

            m = re.match(r"^[-*+]\s+(.*)$", line)
            if m:
                flush_para()
                if list_type != "ul":
                    close_list()
                    out.append("<ul>")
                    list_type = "ul"
                out.append(f"<li>{cls._inline(m.group(1))}</li>")
                continue

            m = re.match(r"^\d+[.)]\s+(.*)$", line)
            if m:
                flush_para()
                if list_type != "ol":
                    close_list()
                    out.append("<ol>")
                    list_type = "ol"
                out.append(f"<li>{cls._inline(m.group(1))}</li>")
                continue

            para.append(line)

        flush_para()
        close_list()
        return "\n".join(out)

    @staticmethod
    def _inline(text: str) -> str:
        """行内语法：链接 / 加粗 / 斜体 / 裸链接"""
        s = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(
            rf'(?<![\"\'=>(])({URL_PATTERN})',
            r'<a href="\1">\1</a>',
            s,
        )
        return s

    @classmethod
    def _md_to_plain(cls, md: str) -> str:
        """Markdown 去标记后的纯文本（用于字数校验和兜底输入）"""
        s = (md or "").replace("\r\n", "\n").replace("\r", "\n")
        s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.M)
        s = re.sub(r"^\s*[-*+]\s+", "· ", s, flags=re.M)
        s = re.sub(r"^\s*(\d+)[.)]\s+", r"\1. ", s, flags=re.M)
        s = re.sub(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", "", s, flags=re.M)
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r"\1（\2）", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip()

    # --------------------------------------------------------------
    # 截图处理
    # --------------------------------------------------------------
    @staticmethod
    def _compress_screenshot(img_path: str, max_kb: int = 500):
        """PNG → JPG 压缩，文件超 max_kb 时降低质量直到达标"""
        import os
        try:
            from PIL import Image
        except ImportError:
            # 没装 Pillow 就跳过压缩
            return
        img_size = os.path.getsize(img_path)
        if img_size <= max_kb * 1024:
            return  # 已经够小
        img = Image.open(img_path).convert("RGB")  # JPG 不支持 alpha
        out_path = img_path.replace(".png", ".jpg")
        for quality in (85, 75, 65, 55):
            img.save(out_path, "JPEG", quality=quality, optimize=True)
            if os.path.getsize(out_path) <= max_kb * 1024:
                break
        else:
            # 还是超，缩宽到 1024
            w, h = img.size
            img = img.resize((1024, int(h * 1024 / w)), Image.LANCZOS)
            img.save(out_path, "JPEG", quality=60, optimize=True)
        # 替换原文件引用
        os.replace(out_path, img_path)
        logger.info(f"[知乎] 截图已压缩: {img_size//1024}KB → {os.path.getsize(img_path)//1024}KB")


# --------------------------------------------------------------
# 向后兼容：旧代码里的 CnblogsPublisher 现在指向知乎实现
# 行为已经完全切换成知乎发布，建议把调用处改成 ZhihuPublisher
# --------------------------------------------------------------
CnblogsPublisher = ZhihuPublisher
