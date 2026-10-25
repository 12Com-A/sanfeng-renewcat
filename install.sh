#!/usr/bin/env bash
# =============================================================================
# 三丰云免费产品自动延期（知乎发文版）—— Linux 一键部署脚本
#
#   用法（在服务器上以 root 执行）：
#     bash install.sh                      # 交互式安装，装完并启动 systemd 服务
#     bash install.sh --login              # 装完顺便扫码登录知乎（二维码推钉钉）
#     bash install.sh --repo <git地址>     # 本机没有源码时从 git 拉
#     bash install.sh --update             # 已部署过 = 更新代码并重启
#
#   常用参数：
#     --dir PATH        安装目录（默认 /root/sanfeng-renewcat）
#     --src PATH        源码目录（默认 = 本脚本所在目录）
#     --config FILE     直接用现成的 config.yaml（跳过配置向导）
#     --yes             全自动：不提问，缺配置就留占位符
#     --no-service      只装不注册 systemd
#     --skip-deps       跳过系统依赖（apt/dnf），已有环境时更快
#     --pip-index URL   换 PyPI 源（默认清华镜像，失败自动回退官方）
#     -h, --help        看帮助
# =============================================================================
set -uo pipefail

APP_NAME="sanfeng-renewcat"
INSTALL_DIR="/root/sanfeng-renewcat/${APP_NAME}"
SRC_DIR=""
REPO_URL=""
CONFIG_SRC=""
ASSUME_YES=0
WITH_SERVICE=1
DO_LOGIN=0
SKIP_DEPS=0
# 国内服务器直连 PyPI 经常慢到超时，默认走清华镜像；可用 --pip-index 覆盖
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
# Playwright 浏览器二进制国内镜像
PW_MIRROR="${PLAYWRIGHT_DOWNLOAD_HOST:-https://cdn.npmmirror.com/binaries/playwright}"

C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'
C_INFO=$'\033[1;36m'; C_DIM=$'\033[2m'; C_END=$'\033[0m'

log()  { printf '%s[%s]%s %s\n' "$C_INFO" "$(date +%H:%M:%S)" "$C_END" "$*"; }
ok()   { printf '%s✔%s %s\n' "$C_OK" "$C_END" "$*"; }
warn() { printf '%s!%s %s\n' "$C_WARN" "$C_END" "$*"; }
die()  { printf '%s✘%s %s\n' "$C_ERR" "$C_END" "$*" >&2; exit 1; }
dim()  { printf '%s   %s%s\n' "$C_DIM" "$*" "$C_END"; }

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dir)        INSTALL_DIR="${2:?}"; shift 2 ;;
        --src)        SRC_DIR="${2:?}"; shift 2 ;;
        --repo)       REPO_URL="${2:?}"; shift 2 ;;
        --config)     CONFIG_SRC="${2:?}"; shift 2 ;;
        --update)     SRC_DIR="${SRC_DIR:-$(cd "$(dirname "$0")" && pwd)}"; shift ;;
        --yes|-y)     ASSUME_YES=1; shift ;;
        --login)      DO_LOGIN=1; shift ;;
        --no-service) WITH_SERVICE=0; shift ;;
        --skip-deps)  SKIP_DEPS=1; shift ;;
        --pip-index)  PIP_INDEX="${2:?}"; shift 2 ;;
        -h|--help)    usage ;;
        *)            die "未知参数: $1（-h 看帮助）" ;;
    esac
done

[ "$(id -u)" -eq 0 ] || die "请用 root 运行：sudo bash $0"

# ---------------------------------------------------------------------------
# 0. 环境探测
# ---------------------------------------------------------------------------
OS_ID=""; OS_LIKE=""; OS_PRETTY="unknown"
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-}"; OS_LIKE="${ID_LIKE:-}"; OS_PRETTY="${PRETTY_NAME:-$ID}"
fi

case "$OS_ID $OS_LIKE" in
    *ubuntu*|*debian*)              PKG=apt ;;
    *centos*|*rhel*|*rocky*|*alma*|*fedora*|*openeuler*|*anolis*) PKG=dnf ;;
    *)                              PKG="" ;;
esac

log "系统: $OS_PRETTY    包管理器: ${PKG:-未识别}"
command -v python3 >/dev/null 2>&1 || [ "$SKIP_DEPS" -eq 1 ] || warn "还没装 python3，安装依赖时会装上"

# ---------------------------------------------------------------------------
# 1. 系统依赖
# ---------------------------------------------------------------------------
install_deps_apt() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq || warn "apt-get update 失败，继续尝试安装"
    apt-get install -y -qq \
        python3 python3-pip python3-venv python3-dev \
        ca-certificates curl unzip git xvfb \
        fonts-noto-cjk fonts-wqy-zenhei fonts-wqy-microhei \
        || warn "部分 apt 包安装失败（中文字体/ Xvfb 缺失会导致截图乱码或无法无头运行）"
    # Playwright 需要的系统库
    apt-get install -y -qq libnss3 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
        libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 libx11-xcb1 \
        || warn "chromium 系统库可能不全，后面 playwright install-deps 会再补一次"
}

install_deps_dnf() {
    dnf install -y -q python3 python3-pip python3-devel \
        ca-certificates curl unzip git \
        xorg-x11-server-Xvfb \
        google-noto-sans-cjk-ttc-fonts google-noto-serif-cjk-ttc-fonts \
        wqy-zenhei-fonts \
        nss atk cups-libs libdrm libxkbcommon libXcomposite libXdamage \
        libXrandr mesa-libgbm pango cairo alsa-lib at-spi2-atk libX11-xcb \
        || warn "部分 dnf 包安装失败，可稍后手动补齐"
}

if [ "$SKIP_DEPS" -eq 1 ]; then
    dim "跳过系统依赖安装（--skip-deps）"
elif [ "$PKG" = "apt" ]; then
    log "安装系统依赖（apt，第一次会慢一点）..."
    install_deps_apt && ok "系统依赖安装完成"
elif [ "$PKG" = "dnf" ]; then
    log "安装系统依赖（dnf）..."
    install_deps_dnf && ok "系统依赖安装完成"
else
    warn "没识别出包管理器，请手动安装：python3 / python3-venv / xvfb / 中文字体 / chromium 依赖"
fi

command -v python3 >/dev/null 2>&1 || die "python3 仍不可用，请先安装 python3"

# ---------------------------------------------------------------------------
# 2. 准备源码
# ---------------------------------------------------------------------------
if [ -z "$SRC_DIR" ]; then
    SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

mkdir -p "$(dirname "$INSTALL_DIR")"

if [ -n "$REPO_URL" ]; then
    log "从 git 拉取源码: $REPO_URL"
    if [ -d "$INSTALL_DIR/.git" ]; then
        git -C "$INSTALL_DIR" pull --ff-only || warn "git pull 失败，继续用现有代码"
    else
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" || die "git clone 失败"
    fi
elif [ -f "$SRC_DIR/renewcat.py" ]; then
    log "从本地目录安装: $SRC_DIR"
    mkdir -p "$INSTALL_DIR"
    # 只覆盖代码与文档，绝不动 config.yaml / cookies / 运行状态
    for f in *.py README.md AI_SPEC.yaml requirements.txt install.sh config.example.yaml; do
        [ -f "$SRC_DIR/$f" ] && cp -f "$SRC_DIR/$f" "$INSTALL_DIR/$f"
    done
    [ -d "$SRC_DIR/deploy" ] && cp -rf "$SRC_DIR/deploy" "$INSTALL_DIR/"
else
    die "找不到源码：$SRC_DIR 里没有 renewcat.py（用 --src 或 --repo 指定）"
fi
ok "源码就位: $INSTALL_DIR"

cd "$INSTALL_DIR" || die "进不去 $INSTALL_DIR"

# ---------------------------------------------------------------------------
# 3. Python 虚拟环境 + 依赖
# ---------------------------------------------------------------------------
if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
    log "创建虚拟环境 .venv ..."
    python3 -m venv "$INSTALL_DIR/.venv" || die "venv 创建失败（apt install python3-venv / dnf install python3-pip）"
fi
VENV="$INSTALL_DIR/.venv/bin"

pip_install() {
    if [ -n "$PIP_INDEX" ]; then
        if "$VENV/pip" install -q --timeout 30 -i "$PIP_INDEX" "$@" 2>/dev/null; then
            return 0
        fi
        warn "镜像源 $PIP_INDEX 没成功，回退官方 PyPI（会慢一些）"
    fi
    "$VENV/pip" install -q --timeout 60 "$@"
}

log "安装 Python 依赖（playwright / playwright-stealth / pyyaml / requests / pillow）..."
pip_install --upgrade pip || warn "pip 升级失败，继续"
pip_install -r "$INSTALL_DIR/requirements.txt" || die "pip install 失败：可换源重试 bash install.sh --pip-index https://pypi.org/simple"
ok "Python 依赖安装完成"

# ---------------------------------------------------------------------------
# 4. Chromium
# ---------------------------------------------------------------------------
log "检查 Playwright Chromium ..."
if "$VENV/python" - <<'PY' >/dev/null 2>&1
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    b.close()
PY
then
    ok "Chromium 已可用"
else
    log "下载 Chromium（约 150MB，走国内镜像）..."
    if ! PLAYWRIGHT_DOWNLOAD_HOST="$PW_MIRROR" "$VENV/playwright" install chromium; then
        warn "镜像下载失败，回退官方源再试一次"
        "$VENV/playwright" install chromium || warn "chromium 下载失败，稍后可手动执行： .venv/bin/playwright install chromium"
    fi
    "$VENV/playwright" install-deps chromium >/dev/null 2>&1 || warn "playwright install-deps 未成功，可能缺系统库"
fi

# ---------------------------------------------------------------------------
# 5. 配置
# ---------------------------------------------------------------------------
detect_public_ip() {
    for u in https://api.ipify.org https://ifconfig.me/ip https://ip.sb; do
        ip="$(curl -fsS --max-time 6 "$u" 2>/dev/null | tr -d '[:space:]')"
        if printf '%s' "$ip" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
            printf '%s' "$ip"; return 0
        fi
    done
    return 1
}

wizard() {
    printf '\n%s===== 配置向导 =====%s（直接回车 = 保持示例值）\n' "$C_INFO" "$C_END"
    local v
    read -r -p "三丰云手机号: "            v; SFY_PHONE="$v"
    read -r -p "三丰云密码: "              v; SFY_PASSWORD="$v"
    read -r -p "知乎登录手机号/邮箱: "      v; SFY_ZH_EMAIL="$v"
    read -r -p "知乎密码: "                v; SFY_ZH_PASSWORD="$v"
    read -r -p "钉钉机器人 webhook: "       v; SFY_WEBHOOK="$v"
    read -r -p "钉钉加签 secret(SEC开头): " v; SFY_SECRET="$v"
    read -r -p "三丰云产品页 URL: "         v; SFY_PRODUCT_URL="$v"

    local ip
    ip="$(detect_public_ip || true)"
    if [ -n "$ip" ]; then
        read -r -p "本机公网地址（推送二维码用）[$ip]: " v
        [ -z "$v" ] && v="$ip"
    else
        read -r -p "本机公网地址（推送二维码用，可留空）: " v
    fi
    SFY_QR_BASE="$v"

    SFY_PHONE="$SFY_PHONE" SFY_PASSWORD="$SFY_PASSWORD" \
    SFY_ZH_EMAIL="$SFY_ZH_EMAIL" SFY_ZH_PASSWORD="$SFY_ZH_PASSWORD" \
    SFY_WEBHOOK="$SFY_WEBHOOK" SFY_SECRET="$SFY_SECRET" \
    SFY_PRODUCT_URL="$SFY_PRODUCT_URL" SFY_QR_BASE="$SFY_QR_BASE" \
    "$VENV/python" - "$INSTALL_DIR/config.yaml" <<'PY'
import os, sys
import yaml

path = sys.argv[1]
cfg = yaml.safe_load(open(path, encoding="utf-8"))

def pick(key, default=""):
    v = (os.environ.get(key) or "").strip()
    return v or default

cfg.setdefault("sanfengyun", {})
cfg["sanfengyun"]["phone"] = pick("SFY_PHONE", cfg["sanfengyun"].get("phone", ""))
cfg["sanfengyun"]["password"] = pick("SFY_PASSWORD", cfg["sanfengyun"].get("password", ""))

zh = cfg.setdefault("zhihu", {})
zh["email"] = pick("SFY_ZH_EMAIL", zh.get("email", ""))
zh["password"] = pick("SFY_ZH_PASSWORD", zh.get("password", ""))

dt = cfg.setdefault("dingtalk", {})
dt["webhook"] = pick("SFY_WEBHOOK", dt.get("webhook", ""))
dt["secret"] = pick("SFY_SECRET", dt.get("secret", ""))

st = cfg.setdefault("settings", {})
st["qr_public_base"] = pick("SFY_QR_BASE", st.get("qr_public_base", ""))

url = pick("SFY_PRODUCT_URL")
if url:
    for p in cfg.get("products", []):
        if p.get("key") == "vps":
            p["url"] = url.strip()

with open(path, "w", encoding="utf-8") as f:
    f.write("# 由 install.sh 生成的配置\n")
    yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
print("配置已写入", path)
PY
}

if [ -f "$INSTALL_DIR/config.yaml" ]; then
    ok "已存在 config.yaml，保留原配置（不覆盖）"
elif [ -n "$CONFIG_SRC" ]; then
    cp -f "$CONFIG_SRC" "$INSTALL_DIR/config.yaml" && ok "已使用指定配置: $CONFIG_SRC"
else
    cp -f "$INSTALL_DIR/config.example.yaml" "$INSTALL_DIR/config.yaml" || die "缺少 config.example.yaml"
    if [ "$ASSUME_YES" -eq 1 ] || [ ! -t 0 ]; then
        warn "非交互模式：已用示例配置，记得手动改 $INSTALL_DIR/config.yaml"
    else
        wizard
        ok "配置完成"
    fi
fi

# ---------------------------------------------------------------------------
# 6. 配置自检（占位符 = 没改）
# ---------------------------------------------------------------------------
CONFIG_OK=1
if "$VENV/python" - "$INSTALL_DIR/config.yaml" <<'PY'
import sys
import yaml

cfg = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))

def bad(v):
    s = "" if v is None else str(v)
    return (not s.strip()) or ("你的" in s) or ("xxx" in s.lower()) or ("实例ID" in s) or ("access_token=xxx" in s)

problems = []
sf = cfg.get("sanfengyun") or {}
if bad(sf.get("phone")) or bad(sf.get("password")):
    problems.append("sanfengyun.phone / password")
zh = cfg.get("zhihu") or {}
if bad(zh.get("email")) or bad(zh.get("password")):
    problems.append("zhihu.email / password")
dt = cfg.get("dingtalk") or {}
if dt.get("enabled") and bad(dt.get("webhook")):
    problems.append("dingtalk.webhook")
for p in cfg.get("products") or []:
    if p.get("enabled") and bad(p.get("url")):
        problems.append(f"products[{p.get('key')}].url")

print("未填/占位的配置: " + (", ".join(problems) if problems else "无"))
sys.exit(1 if problems else 0)
PY
then
    ok "配置项已填写"
else
    CONFIG_OK=0
    warn "上面这些还没填，改完 $INSTALL_DIR/config.yaml 再启动服务"
fi

# ---------------------------------------------------------------------------
# 7. systemd
# ---------------------------------------------------------------------------
if [ "$WITH_SERVICE" -eq 1 ] && command -v systemctl >/dev/null 2>&1; then
    log "注册 systemd 服务 sanfengyun ..."
    cat > /etc/systemd/system/renewcat.service <<EOF
[Unit]
Description=Sanfengyun auto renewal (zhihu publisher)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/renewcat.py
Environment=PYTHONUNBUFFERED=1
KillSignal=SIGINT
TimeoutStopSec=30
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable renewcat >/dev/null 2>&1
    if [ "$CONFIG_OK" -eq 1 ]; then
        systemctl restart renewcat
        sleep 6
        if systemctl is-active --quiet renewcat; then
            ok "服务已启动（journalctl -u renewcat -f 看日志）"
        else
            warn "服务没起来，排查：journalctl -u renewcat -n 50 --no-pager"
        fi
    else
        warn "配置没填完，服务已注册但先不启动：改完 config.yaml 后执行 systemctl start renewcat"
    fi
else
    dim "跳过 systemd（--no-service 或系统无 systemctl）"
fi

# ---------------------------------------------------------------------------
# 8. 自检
# ---------------------------------------------------------------------------
log "自检 ..."
if "$VENV/python" -m py_compile "$INSTALL_DIR"/*.py; then ok "代码编译通过"; else warn "有文件编译失败"; fi
if "$VENV/python" -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); import renewcat; print('IMPORT_OK')" >/dev/null 2>&1; then
    ok "依赖导入正常（playwright / yaml / stealth 都在）"
else
    warn "导入失败，检查 .venv 里的依赖：$VENV/pip install -r $INSTALL_DIR/requirements.txt"
fi

# ---------------------------------------------------------------------------
# 9. 可选：扫码登录知乎
# ---------------------------------------------------------------------------
if [ "$DO_LOGIN" -eq 1 ]; then
    log "触发知乎扫码登录（二维码会推到钉钉）..."
    "$VENV/python" "$INSTALL_DIR/zhihu_login.py" || warn "登录没完成，稍后可手动重跑： $VENV/python $INSTALL_DIR/zhihu_login.py"
fi

printf '\n%s================ 部署完成 ================%s\n' "$C_OK" "$C_END"
cat <<EOF
安装目录 : $INSTALL_DIR
虚拟环境 : $INSTALL_DIR/.venv
配置文件 : $INSTALL_DIR/config.yaml
日志     : journalctl -u renewcat -f   或   tail -f /root/run.log

常用命令：
  systemctl status renewcat        看状态
  systemctl restart renewcat       改完配置重启
  $VENV/python $INSTALL_DIR/renewcat.py --test    手动跑一次（不提交）
  $VENV/python $INSTALL_DIR/zhihu_login.py                   知乎重新扫码登录
  bash $0 --update                   更新代码并重启
EOF
if [ "$DO_LOGIN" -eq 0 ]; then
    printf '\n%s下一步建议：%s先跑一次 %s--test%s，确认能发文再开正式提交。\n' "$C_INFO" "$C_END" "$C_INFO" "$C_END"
fi
