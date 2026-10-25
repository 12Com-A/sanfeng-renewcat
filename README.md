# 续命喵 · RenewCat

> 给免费云服务器续命的猫
>
> 自动扫描三丰云 → 生成评测文章发到知乎 → 回填三丰云延期表单 → 钉钉猫娘汇报。
> 部署到 Linux 上一键跑起来，7×24 无人值守。

<p>
<img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-blue">
<img alt="Playwright" src="https://img.shields.io/badge/playwright-1.40%2B-2EAD33">
<img alt="Platform" src="https://img.shields.io/badge/platform-Ubuntu%20%7C%20Debian%20%7C%20CentOS-lightgrey">
<img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

```bash
git clone https://github.com/12Com-A/sanfeng-renewcat.git
cd sanfeng-renewcat && bash install.sh --login
```

---

## 目录

- [它能干嘛？](#它能干嘛)
- [三丰云的投稿要求 & 文章怎么满足](#三丰云的投稿要求--文章怎么满足)
- [知乎登录过期了怎么办](#知乎登录过期了怎么办自动推二维码到钉钉)
- [一键部署（Linux 服务器）](#一键部署linux-服务器推荐)
- [配置文件详解](#配置文件详解configyaml)
- [常见问题 FAQ](#常见问题-faq)

---

> ⚠️ **写在最前——关于三丰云的审核机制**
>
> **审核只在工作时间进行，大约 3 小时内审完**。意思是——不上班不审核。
> 如果刚好你服务器过期赶上非工作时间，那不好意思，**自动删除你的实例，数据全没**。
>
> 该脚本能做到提交时间一到自动续期， 但如果你到期时间和审核时间恰好一起卡在周末或节假日——自求多福。

---

## 它能干嘛？

> 自动扫描 → 知乎发评测文章 → 三丰云填表单提交延期 → 钉钉通知，全程无人值守。

<table align="center">
  <tr>
    <td><img width="300" src="https://github.com/user-attachments/assets/61645ba2-3a83-4e2b-a4d7-28927ff9bf97" /></td>
    <td><img width="300" src="https://github.com/user-attachments/assets/163fc996-f55e-4e49-967d-ad7cee81ad16" /></td>
    <td><img width="300" src="https://github.com/user-attachments/assets/1c810e27-d673-48d7-aee1-9a0d71c584d5" /></td>
  </tr>
</table>


三丰云的免费云服务器（+5天/次）和免费虚拟主机（+30天/次）需要定期发评测文章提交延期。这个脚本帮你把整套流程全自动跑完：

| 步骤 | 做什么 | 怎么判断 |
|------|--------|---------|
| ① 扫描 | 访问三丰云控制面板，从 **DOM 页面文字** 提取到期时间 + 表单状态 | `form_status` 四态：`ready`（有发帖表单可提交）/ `in_review`（审核中，等结果）/ `not_yet`（未到时间，跳过）/ `not_activated`（未开通，跳过） |
| ② 发帖 | 知乎（zhihu.com）自动生成评测文章并发布 | **只有 `form_status=ready` 才发帖**；按三丰云投稿要求生成（见下表），并发完自动插一张三丰云官网截图 |
| ③ 提交 | 三丰云后台填入文章 URL + 上传文章截图，提交延期表单 | 单张 JPG/PNG 截图（full_page）；提交成功 → 冷却 4h 等审核；审核中 → 2h 后再扫 |
| ④ 通知 | 每个阶段都推一条钉钉 Markdown 消息 | 加签模式安全，消息带"下次脚本执行时间" |

**两个实例各自独立倒计时**，哪个先到时间就先触发哪个，互不干扰。

### 三丰云的投稿要求 & 文章怎么满足

| 三丰云的要求 | 脚本里的做法 |
|------|------|
| ① 不能出现"申请延期"字样 | 模板池里**一个"延期/续期"都没有**，`ArticleGenerator.FORBIDDEN_WORDS` 每次生成后自动扫描，命中就把问题写进日志 |
| ② 必须含"三丰云""免费云服务器""免费虚拟主机" + 50 字以上评测 | 三个词在正文里自然出现多次，结尾"关键词"行再兜一次底；`REQUIRED_KEYWORDS` 自检，正文字数通常 1500+ |
| ③ 含三丰云官网链接优先通过 | 每篇都带 `https://www.sanfengyun.com`（正文里 + 结尾各一处） |
| ④ 含官网截图 / 图文并茂优先通过 | 发文时自动另开标签页截一张三丰云官网图，插进正文末尾；插不进去只降级成纯文字，不影响发布 |
| （避坑）整篇像广告会被平台限流 | 文章写成"介绍 + 横向对比"：普遍带阿里云、腾讯云、华为云、京东云、UCloud、雨云做参照，并单独写"不足"段落，读起来是评测而不是软文 |

> 想核对生成质量：`ArticleGenerator.check(title, content)` 返回空列表就表示满足上面的硬性要求。

### 知乎登录过期了怎么办（自动推二维码到钉钉）

知乎 Cookie 会过期（一般几十天）。脚本检测到登录失效时不会干等着，而是：

1. 打开知乎登录页 → 切到「扫码登录」→ 截下**当前二维码**（自动放大到 552px，方便手机扫）
2. 在服务器上临时起一个**只读图片服务**（默认 80 端口，只对 `/<随机 token>.png` 返回这张图，其它路径 404）
3. 把图片地址用 Markdown 发到钉钉：`![知乎登录二维码](http://你的服务器/zhihu-qr-xxxx.png)`
4. 在钉钉里用**知乎 App 扫一扫**，手机上点「确认登录」
5. 扫到后立刻存 Cookie 写进 `zhihu_cookies.json`，关掉临时图片服务，接着干活

细节：

- 二维码 2 分钟过期，所以脚本每 150 秒**换一张重发**，一共 3 轮（约 7.5 分钟），你什么时候看到什么时候扫都行
- 临时服务只在登录过程开着，登录一结束（成功或超时）立即关闭，不长期占端口
- 80 端口被占用 / 钉钉抓不到图时，自动退回 **0x0.st 图床**；图床也不通就发文字提示 + 二维码在服务器上的路径
- 消息里除了图片还带一条纯文字链接，图片没渲染出来时点链接也能打开

> 相关配置：`settings.qr_public_base`（填你服务器的公网地址）、`settings.qr_port`（默认 80）。

### 钉钉机器人说话风格：猫娘

所有钉钉消息都是「小喵」的口吻：自称**人家**、称呼你**主人**、句尾带**喵～**，失败时会说"呜呜…耳朵耷拉下来"。技术信息（时间 / 状态 / 错误 / 链接）一个不少，只是换了层皮。想改回去，直接改 `dingtalk_notify.py` 里各个 `notify_*` 方法的文案即可。

---

## 目录结构

```
sanfeng-renewcat/
├── README.md                 📖 本文件（给人看）
├── AI_SPEC.yaml              🤖 机器可读规约（给 AI 看，YAML 结构化，含可复用组件标注）
├── renewcat.py     ⭐ 主入口（命令行 / 持续运行模式）
├── scanner.py                登录三丰云 + DOM 扫描到期时间 / 延期状态
├── publisher.py              登录知乎 + 自动发文 + 官网配图 + 页面截图
├── qr_service.py             知乎登录过期时，临时托管二维码并推送到钉钉
├── renewer.py                三丰云后台填写延期表单 + 提交
├── article_generator.py      文章生成器（介绍+横评模板池 + 投稿要求自检）
├── dingtalk_notify.py        钉钉机器人通知（猫娘语气，加签，Markdown + 图片）
├── config.yaml               🔧 配置文件（账号密码 / 产品列表 / 运行参数）
├── config.example.yaml       配置模板（一键部署时用它生成 config.yaml）
├── install.sh                🚀 一键部署脚本（依赖 / venv / Chromium / 配置 / systemd）
├── zhihu_login.py            知乎扫码登录 CLI（二维码推钉钉）
├── requirements.txt          Python 依赖
├── instance_timestamps.json  ⚡ 运行时生成：每个实例的下次触发时间戳
├── zhihu_cookies.json        ⚡ 运行时生成：知乎登录 Cookie（下次免验证码）
└── screenshots/              运行时生成：知乎文章截图、扫描截图（自动创建）
```

### 各文件一句话说明

| 文件 | 作用 | 要不要改 |
|------|------|---------|
| [renewcat.py](renewcat.py) | **主入口**，三种运行模式（`--test` / `--once` / 持续循环）。run_loop 里有独立倒计时持久化逻辑，**核心常量在文件顶部**（STATE_FILE / SLEEP_SLICE / TRIGGER_DELAY） | 一般不用改 |
| [scanner.py](scanner.py) | DOM 页面元素抓取。`ensure_login()` 做登录检测，`scan_product()` 返回 `can_renew / expire_time / renew_time / form_status`（ready/in_review/not_yet/not_activated） | 一般不用改 |
| [publisher.py](publisher.py) | 知乎自动发文。`login()` + `publish()`，Markdown 正文会转成富文本写进知乎编辑器，并自动插一张三丰云官网配图；发布后跳转**公开页** full_page 截图，Pillow 压缩到 500KB 内 JPG | 一般不用改 |
| [renewer.py](renewer.py) | 三丰云填表单。`fill_and_submit()` 里 `dry_run=True` 只填不提交 | 一般不用改 |
| [article_generator.py](article_generator.py) | 文章模板池 + 投稿要求自检。想换话题/风格就改 `TITLE_TEMPLATES` / `INTRO_TEMPLATES` 这些列表；硬性要求写在 `REQUIRED_KEYWORDS` / `FORBIDDEN_WORDS` 里，`check()` 负责把关 | **可以改，加自己的模板**（别加"延期"字样） |
| [dingtalk_notify.py](dingtalk_notify.py) | 钉钉通知格式。想改通知样式在这里调 Markdown | 一般不用改 |
| [config.yaml](config.yaml) | **所有账号、产品 URL、运行参数都在这里** | **必须改**（见下文配置详解） |
| [requirements.txt](requirements.txt) | Python 依赖列表 | 一般不用改 |
| `instance_timestamps.json` | **脚本自动生成**，保存每个实例下次触发的 Unix 时间戳。删了也没事，下次启动会自动重新扫 | 不用手动改 |
| `screenshots/` | **脚本自动生成**，存放所有截图：①扫描页面截图（排错用）②知乎文章公开页长截图（**提交给三丰云审核用，必须有**）③三丰云填表截图。目录不存在会自动 `mkdir`，不用手动建，也别提交到 git | 不用手动改 |

---

## 运行时自动生成的文件（不用手动建）

脚本第一次运行时会自动创建以下文件/目录，**不需要你手动建**，也**不要提交到 GitHub**：

| 文件/目录 | 什么时候生成 | 能不能删 | 删了会怎样 |
|----------|------------|---------|-----------|
| `screenshots/` | 脚本启动时 `mkdir(exist_ok=True)` | 可以删 | 下次运行自动重建；里面的截图会丢失（三丰云提交时需要重新生成） |
| `instance_timestamps.json` | 首次扫描完成后写入 | 可以删 | 下次启动会重新登录三丰云全量扫描重建（多花一次扫描时间） |
| `zhihu_cookies.json` | 知乎首次登录成功后写入 | 可以删 | 下次运行要重新登录知乎（可能还要再拖一次滑块 / 扫一次码） |
| `__pycache__/` | Python 导入模块时生成 | 可以删 | 自动重建 |
| `run.log`（如果你在 config.yaml 配了日志文件路径） | 脚本运行写日志时生成 | 可以删 | 删了重新生成，历史日志丢失 |

> 💡 **关于 screenshots 文件夹**：它是有用的，**别删**。脚本里 `publisher.py` 生成的文章公开页长截图会上传到三丰云作为延期凭证，`scanner.py` 和 `renewer.py` 的截图用于排错。目录不存在时脚本会自动创建。

---

## 前提版本

| 组件 | 最低版本 | 推荐版本 | 说明 |
|------|---------|---------|------|
| Python | **3.9** | 3.10 / 3.11 / 3.12 | 用到了类型注解和 strftime 的 `/` 替换 |
| Playwright | 1.40 | 最新 | 浏览器自动化引擎 |
| Pillow | 9.0 | 最新 | 截图压缩到 500KB 内（三丰云审核偏好小图） |
| 系统 | Ubuntu 20.04 / Debian 11 / CentOS 7+ | Ubuntu 22.04 | 需要有 root 或 sudo 权限安装 chromium 依赖 |
| 中文字体 | - | fonts-noto-cjk + fonts-wqy-zenhei | **Linux 服务器必须装！否则截图中文全是 □□□ 乱码** |
| 磁盘 | - | ≥ 1GB | Playwright chromium + 截图会占空间 |

---

## 快速上手（本地）

### 第 1 步：克隆 & 安装依赖

```bash
git clone https://github.com/12Com-A/sanfeng-renewcat.git
cd sanfeng-renewcat

# 装 Python 依赖
pip install -r requirements.txt

# 装 Playwright 浏览器（第一次会下载 chromium，几十 MB）
playwright install chromium
playwright install-deps chromium   # 服务器上跑必须执行这条！安装系统库
```

### 第 2 步：改配置

打开 `config.yaml`，改这几块：

```yaml
sanfengyun:
  phone: "你的三丰云手机号"     # ← 改
  password: "你的三丰云密码"     # ← 改

zhihu:
  email: "你的知乎手机号/邮箱"   # ← 改
  password: "你的知乎密码"       # ← 改
  username: ""                  # 可留空：登录后自动识别主页
  cookies_file: ""              # 可留空：默认 zhihu_cookies.json

dingtalk:
  enabled: true
  webhook: "https://oapi.dingtalk.com/robot/send?access_token=xxx"   # ← 改
  secret: "SECxxx"   # ← 改（机器人安全设置里复制）

products:
  - key: "vps"
    url: "https://www.sanfengyun.com/control/#/freeServer/你的实例ID"    # ← 改
  - key: "vhost"
    url: "https://www.sanfengyun.com/control/#/freeVhost/你的实例ID"     # ← 改
```

> 💡 不想用钉钉通知？把 `enabled: true` 改成 `false` 就行。

### 第 3 步：跑测试模式（只填表单，不真提交）

```bash
python3 renewcat.py --test
```

看到日志走完三个阶段（扫描 → 发文 → 填表），没有报错，**钉钉也收到了三条通知**，就说明环境 OK。

### 第 4 步：跑持续模式（自动倒计时，到点自动触发）

```bash
python3 renewcat.py
```

按 `Ctrl + C` 可以优雅退出。

---

## 首次运行会发生什么？

第一次跑 `--test` 或持续模式时，脚本会按顺序做这些事：

```
1. 读 config.yaml → 初始化日志、钉钉通知
2. 启动 chromium（headless=False + Xvfb 虚拟显示，绕过知乎的自动化检测）
3. 登录三丰云（清空旧 cookie → 填账号密码 → 修复 cookie domain → 验证）
4. 扫描所有产品（跳转到每个产品详情页 → 等 Vue 渲染 → 提取到期时间/表单状态）
   → 自动创建 instance_timestamps.json（记录每个产品下次触发时间）
   → 自动创建 screenshots/ 目录，保存扫描截图
5. 如果有产品 form_status=ready（可延期）：
   → 登录知乎（优先复用 zhihu_cookies.json；没有就账号密码 + 自动拖滑块，仍不成功会留 180 秒给你扫码）
   → 生成三丰云介绍 + 横评文章 → Markdown 转富文本写入知乎编辑器 → 插一张官网配图 → 发布 → 截文章公开页长图
   → 回到三丰云填 URL + 上传截图 → 提交（--test 模式只填不提交）
6. 每个阶段推一条钉钉通知
```

**常见现象（正常，不用慌）：**
- 扫描时页面会"卡住"5 秒 → 这是在等 Vue SPA 渲染到期时间，正常
- 知乎首次登录可能弹滑块验证 / 要求扫码 → 脚本用 smoothstep 贝塞尔曲线自动拖滑块（最多 3 次）；还不行就留 180 秒给你扫码。登录成功后 Cookie 存进 `zhihu_cookies.json`，下次直接免登录
- 持续模式等待时不开浏览器 → 只读 JSON 判断倒计时，到点才启动浏览器（节省资源）
- `--test` 模式最后三丰云表单只填不提交 → 这是设计如此，怕你误提交
- 第一次跑会慢一点（要全量扫描），之后读 json 跳过初始化扫描就快了

---

## 三种运行模式

| 命令 | 做什么 | 什么时候用 |
|------|--------|-----------|
| `python3 renewcat.py --test` | 扫描 → 发文 → **填表不提交**（dry_run=True） | 第一次跑、改了配置后验证 |
| `python3 renewcat.py --once` | 扫描 → **可以延期的都完整提交一次** | 临时手动触发一次 |
| `python3 renewcat.py` | 启动持续循环，每实例独立倒计时，到点自动执行 | 服务器上 7×24 挂着跑 |

---

## 配置文件详解（config.yaml）

### 🔧 必须改的字段

| 位置 | 字段 | 说明 |
|------|------|------|
| `sanfengyun.phone` | 手机号 | 你注册三丰云用的手机号 |
| `sanfengyun.password` | 密码 | 三丰云登录密码 |
| `zhihu.email` | 手机号/邮箱 | 知乎登录账号 |
| `zhihu.password` | 密码 | 知乎登录密码 |
| `zhihu.username` | 主页 token | 可留空（登录后自动识别）；也可填 `https://www.zhihu.com/people/xxx` 里的 `xxx` |
| `dingtalk.webhook` | Webhook | 钉钉群 → 设置 → 智能群助手 → 添加机器人（自定义） → 复制 URL |
| `dingtalk.secret` | 加签密钥 | 机器人安全设置 → 加签 → 复制 `SEC` 开头那串 |
| `products[*].url` | 实例 URL | 三丰云控制面板里点进实例详情页，复制浏览器地址栏 |

### ✏️ 可选调整的字段

| 位置 | 默认值 | 说明 |
|------|--------|------|
| `settings.dry_run` | `false` | `true`=只填表单不提交（测试用）；`false`=真的提交延期 |
| `settings.sanitize_keywords` | `[]` | 默认**不做任何替换**。三丰云审核要求文章里必须出现"三丰云"三个字，替换掉反而不合格；只有知乎把某个词判成敏感词、发文被拦时才填 `["原词", "替换词"]` |
| `settings.qr_public_base` | `"http://你的服务器IP"` | 知乎登录过期时，二维码图片要通过这个地址让钉钉抓取。**填服务器公网地址**，留空则退回 0x0.st 图床 |
| `settings.qr_port` | `80` | 临时图片服务端口。80 一般最容易被钉钉抓图，被占用会自动换图床 |
| `logging.file` | `""` | 留空只输出控制台；填路径（如 `run.log`）则同时写日志文件 |
| `products[*].enabled` | `true` | `false`=跳过这个产品（比如你只有 vps，把 vhost 设 false） |
| `settings.scan_scope` | `"all"` | 扫描范围：`all`=两个都扫；`vps`=只扫云服务器；`vhost`=只扫虚拟主机。钉钉通知也只包含被扫描的产品 |

### 🔒 不用改的字段

`login_url`、`ptype`、`level` 这些保持默认就行。

> ⚠️ `check_interval`、`early_submit_seconds` 是**遗留字段**，当前版本代码未使用（倒计时由 `instance_timestamps.json` 独立管理），保留仅为兼容旧配置，可忽略。

---

## 一键部署（Linux 服务器，推荐）

不想一步步手搓就用这个 —— 系统依赖、Python 环境、Chromium、配置、systemd 一次搞定：

```bash
# 在服务器上（root）
git clone https://github.com/12Com-A/sanfeng-renewcat.git && cd sanfeng-renewcat
bash install.sh                    # 交互式：会问你账号/钉钉/产品 URL
```

脚本做的事：

| 步骤 | 内容 |
|---|---|
| 1 | 识别系统（Ubuntu/Debian 用 apt，CentOS/Rocky/Alma/Fedora 用 dnf），装 python3、venv、Xvfb、中文字体、chromium 依赖 |
| 2 | 把代码拷到 `/root/sanfeng-renewcat`（**不会覆盖已有的 config.yaml**） |
| 3 | 建 `.venv` + 装依赖（**默认清华 PyPI 镜像**，失败自动回退官方；Chromium 走 npmmirror） |
| 4 | 没有配置就跑向导（三丰云账号 / 知乎账号 / 钉钉 / 产品 URL / 公网地址，自动探测公网 IP） |
| 5 | 注册 `renewcat.service` 并启动（配置没填完时只注册不启动，避免崩溃重启刷屏） |
| 6 | 自检：编译所有 .py、导入依赖、检查配置占位符是否还留着 |

常用玩法：

```bash
bash install.sh --login                 # 装完直接弹二维码，扫码登录知乎
bash install.sh --update                # 已部署过：更新代码 + 重启服务
bash install.sh --yes                   # 全自动（缺配置就留占位符，之后再改）
bash install.sh --no-service            # 只装不注册 systemd
bash install.sh --skip-deps             # 系统依赖已装过，跳过 apt/dnf
bash install.sh --pip-index https://pypi.org/simple   # 换源
bash install.sh --dir /opt/sfy          # 自定义安装目录
```

> 实测：Ubuntu 22.04 + 已缓存 chromium 的情况下，`bash install.sh --yes` 全程 **29 秒**。

---

## 手动部署到服务器（Ubuntu / Debian）

### 第 1 步：安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# Playwright 需要的系统库（必须，否则 chromium 启动报缺库）
sudo apt install -y libnss3 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 libx11-xcb1

# ⚠️ 中文字体（必须！否则截图里中文全是 □□□ 乱码）
sudo apt install -y fonts-noto-cjk fonts-wqy-zenhei fonts-wqy-microhei
fc-cache -fv

# ⚠️ Xvfb 虚拟显示（必须！知乎会检测 headless 模式）
sudo apt install -y xvfb
```

### 第 2 步：创建目录 + 上传代码

```bash
sudo mkdir -p /root/sanfeng-renewcat
sudo chown -R $USER:$USER /root/sanfeng-renewcat

# 方式 A：git clone
cd /root/sanfeng-renewcat
git clone https://github.com/12Com-A/sanfeng-renewcat.git .

# 方式 B：本机打包 scp 过去
# 在本机：tar czf sanfengyun.tar.gz sanfeng-renewcat/
# 在服务器：scp user@你的服务器IP:~/sanfengyun.tar.gz /root/
#          tar xzf /root/sanfeng-renewcat.tar.gz -C /root/sanfeng-renewcat --strip-components=1
```

### 第 3 步：安装 Python 依赖

```bash
cd /root/sanfeng-renewcat
pip3 install -r requirements.txt --break-system-packages   # Ubuntu 24.04+ 用这个
# 或用 venv（推荐）：
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 安装 chromium
playwright install chromium
playwright install-deps chromium
```

### 第 4 步：修改 config.yaml（服务器版本）

```bash
vi /root/sanfeng-renewcat/config.yaml
```

重点检查：

```yaml
settings:
  dry_run: false          # ← 部署后改成 false，真的提交延期

logging:
  file: "/root/sanfeng-renewcat/run.log"   # ← 服务器上建议写日志文件，方便排错
```

### 第 5 步：先跑一次测试

```bash
cd /root/sanfeng-renewcat
source .venv/bin/activate    # 如果用 venv

python3 renewcat.py --test
```

走完三个阶段、钉钉收到通知 → 环境 OK。

### 第 6 步：用 systemd 守护（7×24 自动重启）

创建服务文件：

```bash
sudo vi /etc/systemd/system/renewcat.service
```

内容：

```ini
[Unit]
Description=续命喵
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/root/sanfeng-renewcat
ExecStart=/root/sanfeng-renewcat/.venv/bin/python3 /root/sanfeng-renewcat/renewcat.py
Restart=on-failure
RestartSec=30
# 如果没用 venv，把上面两个路径换成系统的 python3 就行
# ExecStart=/usr/bin/python3 /root/sanfeng-renewcat/renewcat.py

[Install]
WantedBy=multi-user.target
```

启动 & 设置开机自启：

```bash
sudo systemctl daemon-reload
sudo systemctl start renewcat
sudo systemctl enable renewcat

# 查看实时日志
journalctl -u renewcat -f

# 查看进程状态
systemctl status renewcat
```

### 常用运维命令

```bash
systemctl restart renewcat     # 重启（改了 config.yaml 后必须重启才生效）
systemctl stop renewcat        # 停止
tail -f /root/sanfeng-renewcat/run.log # 直接看脚本日志文件
```

---

## 倒计时持久化机制

### 核心思路

两个实例 **各自独立保存** 下次允许提交的 Unix 时间戳到 `instance_timestamps.json`：

```json
{
  "freeServer_532542": {"next_allow_submit_ts": 1788717483},
  "freeVhost_6631220": {"next_allow_submit_ts": 1789634902}
}
```

### 触发条件

```
当前时间 >= next_allow_submit_ts + 60
                                  ↑
                          TRIGGER_DELAY = 60s
                          缓冲一下三丰云和本地的时间差
```

### 运行流程

```
脚本启动
  │
  └─ 读 instance_timestamps.json
     ├─ 有缺失实例？→ 登录三丰云 DOM 扫描补全，写回 json
     └─ json 完整 → 跳过初始化扫描（节省时间和请求）

主循环（每 60s 醒一次）
  │
  ├─ 遍历实例，计算 remain = next_ts + 60 - now
  │   ├─ remain <= 0      → 到点了，加入 need_trigger_keys
  │   ├─ remain <= 3600   → 钉钉推"即将触发"紧急提醒（每实例只推一次）
  │   └─ remain > 3600    → 打印进度日志：[等待中] 免费云服务器 → 09-06 07:59
  │
  ├─ 有实例到点 → 执行完整流程（_execute_single_product）
  │   │
  │   ├─ Phase A: DOM 扫描 → 得到 form_status
  │   │
  │   ├─ form_status = ready（有发帖表单）
  │   │   → 知乎发文 → 三丰云填表提交
  │   │   → next_ts = now + 4h（等审核结果）
  │   │
  │   ├─ form_status = in_review（审核中）
  │   │   → 不发帖、不提交
  │   │   → next_ts = now + 2h（2h 后再扫，看审核过了没）
  │   │   → 循环扫描：若仍审核中，继续 2h 后再扫；
  │   │     若变成 not_yet，取页面"请在XX后提交"时间；
  │   │     若变成 ready，执行发文+提交
  │   │
  │   └─ form_status = not_yet（未到时间）
  │       → 不发帖、不提交
  │       → next_ts = 页面上的"请在 XX 后提交"时间
  │
  └─ sleep 60s → 下一轮
```

### 钉钉通知机制

所有通知都是猫娘口吻（自称"人家"、称呼"主人"、句尾"喵～"）。脚本在以下时机发送钉钉通知：

| 时机 | 通知内容 |
|------|---------|
| 脚本启动 | 启动时间、监控产品数、持久化文件路径 |
| 到点前 30min | "即将触发"提醒（每实例每轮只推一次，触发后清除标记） |
| 触发执行 | "🚀 倒计时已触发"，开始扫描三丰云页面状态 |
| 扫描结果 | DOM 扫描后推送 form_status、到期时间、可提交时间 |
| ready → 提交成功 | 文章 URL、提交结果、下次扫描时间（4h 后） |
| ready → 提交失败 | 失败原因、下次重试时间（30min） |
| in_review | "审核中，脚本将在 XX 时间再次扫描"（2h 后） |
| not_yet | "未到可提交时间，下次扫描 XX" |
| not_activated | "产品未开通，24h 后再检查" |
| **知乎登录过期** | **推送二维码图片**（临时图片服务 + Markdown 内嵌），扫码后自动恢复并回一条"登录恢复" |
| 脚本异常 | 异常错误信息 |

**通知时序示例**：
1. 倒计时 ≤ 30 分钟 → 推送"即将触发"提醒（仅 1 次）
2. 到点 → 推送"已触发"通知 → 扫描 DOM
3. 扫描完 → 推送"扫描结果"（form_status 详情）
4. 根据状态 → 推送"审核中"/"提交成功"/"未到时间"等结果

**为什么每次扫描后都通知下次启动时间？**
每次触发执行后，脚本会根据 `form_status` 计算下次扫描时间并写入 `instance_timestamps.json`，同时通过 `notify_waiting` 通知用户。这样用户能清楚知道脚本何时会再次运行，无需手动查看日志。审核中状态每 2h 扫描一次，未到时间状态则等到页面指定的时间点。

### 持续模式主循环优化

主循环每 60 秒检查一次，但**只在需要触发或初始化时才启动浏览器**：

1. 先读 `instance_timestamps.json`（不启动浏览器）
2. 判断是否有实例到达触发时间，或 JSON 缺失实例
3. 如果都不需要 → 只打一行日志 `[等待中]`，sleep 60s 继续
4. 如果有触发或需要初始化 → 启动浏览器，执行扫描/触发流程

这样避免了每 60 秒启动一次浏览器的资源浪费。

### 登录与反检测机制

知乎登录页有滑块验证 + 风控，headless 模式容易被判定为机器人。脚本采用以下策略：

| 策略 | 作用 |
|------|------|
| **Xvfb 虚拟显示** | 在无显示器的服务器上提供虚拟 X11 显示，让 `headless=False` 模式可以运行 |
| **headless=False** | 非无头模式不容易被知乎风控判定为自动化工具 |
| **隐藏 webdriver 特征** | `add_init_script` 覆盖 `navigator.webdriver`、`window.chrome`、`plugins`、`languages` |
| **playwright-stealth** | 注入 stealth 脚本，进一步隐藏自动化痕迹 |
| **smoothstep 贝塞尔曲线** | 拖滑块时按 `t² × (3-2t)` 缓动函数分 22-38 步移动鼠标，模拟人类轨迹 |
| **随机停顿** | 按下与松开滑块之间随机停顿，松开后等 3.5s 看验证结果 |
| **3 次重试** | 滑块验证失败自动重试；仍失败则留 180 秒给你扫码登录 |
| **Cookie 复用** | 登录成功把 Cookie 存进 `zhihu_cookies.json`，下次启动先试 Cookie，命中就完全跳过验证码 |

三丰云登录不涉及验证码，使用简单的表单登录 + cookie domain 修复。

### 关键设计：先查入口再发帖

> **绝对不会先发帖再去检查能不能提交**。每次触发都先 DOM 扫描 `form_status`，只有 `ready` 才去知乎发文。如果三丰云页面显示"审核中"或"未到时间"，直接跳过，避免生成无效文章被知乎判定灌水 / 营销。

### 为什么要持久化？

| 情况 | 没持久化 | 有持久化 |
|------|---------|---------|
| 脚本进程崩了重启 | 立刻重新全量扫描（浪费 API） | 读 json，直接恢复倒计时 |
| 服务器重启 | 同上 | 同上 |
| 两个实例一个到点一个没到 | 全量扫描 + 统一 sleep | 各自独立，只跑那个到点的 |

### 关键原则（方案2 原文）

> **本地 json 只是倒计时记录，一切业务判断以三丰云 DOM 页面为准**。即使 json 存的时间戳乱了，每次触发都会重新访问页面，不会乱发帖乱提交。

---

## 常见问题 FAQ

### Q1：脚本跑起来但钉钉没收到通知？

检查：
1. `config.yaml` 里 `dingtalk.enabled` 是否为 `true`
2. 机器人 Webhook 里的 `access_token` 和 `secret` 是否复制完整
3. 钉钉群 → 机器人安全设置 → 加签密钥（`SEC` 开头）有没有对上
4. 服务器能不能访问 `oapi.dingtalk.com`（`curl -I https://oapi.dingtalk.com/robot/send`）

### Q2：知乎发布后提示"内容涉嫌营销 / 广告"被限制？

先别急着换词。默认配置 `sanitize_keywords: []` **不做替换**，因为三丰云要求文章里必须出现"三丰云"——把它换成"三丰"三丰云那边就判不合格了。

判断方向：
1. 文章本身已经带了同行对比（阿里云 / 腾讯云 / 华为云 / 京东云 / UCloud / 雨云）和优缺点，如果仍被限，多半是账号权重问题，换时间段再发一次即可；
2. 确实被某个词卡住时，才填替换词：

```yaml
sanitize_keywords:
  - "三丰云"
  - "SFY"     # 换成你想替换成什么（注意：替换后就不再满足三丰云的必需关键词要求）
```

### Q3：服务器上跑 Chromium 报 "error while loading shared libraries: libnss3.so"？

Playwright 没装系统依赖。执行：

```bash
playwright install-deps chromium
```

### Q3.5：三丰云收到的截图里中文全是 □□□ 方块？

**服务器没装中文字体**，Chromium 渲染中文时全部变成豆腐块。执行：

```bash
sudo apt install -y fonts-noto-cjk fonts-wqy-zenhei fonts-wqy-microhei
fc-cache -fv
# 装完重启脚本即可，不用重装 chromium
```

本地 macOS / Windows 一般自带中文字体，不会有这个问题。

### Q4：脚本进程崩了会自动重启吗？

如果按 systemd 方式部署的（推荐），会。`Restart=on-failure` 配置会让它异常退出后 30s 自动拉起。

### Q5：我只有一个产品（比如只有 vps 没有 vhost）？

```yaml
products:
  - key: "vps"
    name: "免费云服务器"
    enabled: true
    url: "https://www.sanfengyun.com/control/#/freeServer/你的实例ID"
  # 把 vhost 那段整个删掉，或者留着 enabled: false
```

### Q6：我想换一个发布平台（CSDN、掘金、简书）？

改 `publisher.py`，换成你要的平台的登录 + 发文逻辑。接口都在 `publisher.py` 的 `login()` / `publish()` 里，主入口不动；`config.yaml` 里对应的账号段同步改名即可。

### Q7：想自己改文章模板？

打开 `article_generator.py`，顶部有 `TITLE_TEMPLATES` / `INTRO_TEMPLATES` / `ABOUT_PARAGRAPHS` / `COMPARE_PARAGRAPHS` 等列表。你想换风格就往里面加自己的文案。

加模板时注意三条硬规则（文件顶部 `REQUIRED_KEYWORDS` / `FORBIDDEN_WORDS` 就是干这个的）：
1. **不能出现"延期""续期""申请延期"**——三丰云明确禁止，加了会导致投稿不合格；
2. 正文要能自然带上"三丰云""免费云服务器""免费虚拟主机"三个词；
3. 保留至少一句对其他云厂商（阿里云/腾讯云/华为云/京东云/UCloud/雨云）的对比，纯夸产品容易被平台判成广告。

带时间占位符的模板用 `{NOW_FULL}`（`2026年09月05日22:20`）或 `{NOW_DATE}`（`2026年09月05日`），运行时自动替换。

### Q8：`--test` 和 `--once` 有啥区别？

- `--test`：所有 **执行** 步骤都走，但三丰云表单只填不提交（`dry_run=True` 硬编码）
- `--once`：真的提交。`config.yaml` 里的 `dry_run` 决定要不要真提交。

### Q9：instance_timestamps.json 能手动改吗？

可以，但没必要。脚本启动时会用 DOM 扫描结果覆盖它。删了也没事，下次启动会自动重建。

---

## 安全提示

**`config.yaml` 和 `zhihu_cookies.json` 里是你的账号密码和登录态，都已经写进 `.gitignore`，不会进仓库。**

- 仓库里只有 `config.example.yaml`（全是占位符）
- 万一不小心提交了真实配置，立刻改密码 + 删历史：`git filter-repo --path config.yaml --invert-paths`
- 知乎 Cookie 过期后会自动推二维码到钉钉，不用手动维护

## 它是怎么工作的

```
                ┌──────────────────────────────────────────┐
                │           renewcat.py (主循环)            │
                └───────────────┬──────────────────────────┘
                                │ 每 60s 看一眼倒计时（不启动浏览器）
                                ▼
        ┌───────────────┬───────────────┬──────────────────┐
        │  scanner.py   │  publisher.py │   renewer.py     │
        │ 扫三丰云状态   │  知乎发文      │  三丰云填表提交   │
        └───────┬───────┴───────┬───────┴────────┬─────────┘
                │               │                │
                ▼               ▼                ▼
        form_status 四态    文章 + 官网配图    表单 + 截图
        ready / in_review   zhihu_cookies   dry_run 开关
        not_yet / not_activated
                │
                └──► dingtalk_notify.py（猫娘汇报）
                          └─ 登录过期 → qr_service.py 推二维码
```

## 许可

[MIT](LICENSE) © 2026 Commkom

部分代码来源：https://github.com/dyshk/sanfengyun-auto-renewal/ 此项目

> 仅供学习交流。用自动化脚本操作第三方平台前，请自行确认是否符合该平台的服务条款；账号风险自负。
