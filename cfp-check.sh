#!/bin/bash
# Weekly CFP check for the deadline calendar (run by launchd every Monday).
# Runs Claude Code headless with the fixed, scoped prompt in cfp-check-prompt.md.
# Tool access is allowlisted to the minimum needed: curl (fetch official CFPs),
# python3 (regenerate outputs), basic file reads/writes in this directory.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
LOG="$DIR/cfp-check.log"

ALLOWED="Bash(curl:*),Bash(python3:*),Bash(ls:*),Read,Edit,Write,Glob"

# API 配置（ANTHROPIC_*）存放在仓库外的 ~/.claude/cfp-check.env，避免 token 进入公开仓库
ENV_FILE="$HOME/.claude/cfp-check.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

echo "=== CFP check started $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"
/Users/haomeng/.local/bin/claude -p "$(cat "$DIR/cfp-check-prompt.md")" \
    --allowedTools "$ALLOWED" \
    >> "$LOG" 2>&1
rc=$?
echo "=== CFP check finished $(date '+%Y-%m-%d %H:%M:%S') (exit $rc) ===" >> "$LOG"

# 核查成功后：有文件变化则提交并推送，公开站点随之更新；
# 核查失败则不碰 git，避免把错误状态推上线。
if [ "$rc" -eq 0 ]; then
    # 代理自动探测：本机代理端口连得上才走代理，否则直连。
    # 全局 git config 里配了 http(s).proxy，直连时必须显式置空覆盖它。
    PROXY_HOST=127.0.0.1
    PROXY_PORT=10808
    if (exec 3<>"/dev/tcp/$PROXY_HOST/$PROXY_PORT") 2>/dev/null; then
        exec 3>&-
        PROXY_URL="http://$PROXY_HOST:$PROXY_PORT"
        export HTTPS_PROXY="$PROXY_URL" HTTP_PROXY="$PROXY_URL"
        echo "=== proxy up at $PROXY_HOST:$PROXY_PORT, pushing through it ===" >> "$LOG"
    else
        PROXY_URL=""
        unset HTTPS_PROXY HTTP_PROXY
        echo "=== no proxy at $PROXY_HOST:$PROXY_PORT, pushing directly ===" >> "$LOG"
    fi
    GIT_PROXY=(-c "http.proxy=$PROXY_URL" -c "https.proxy=$PROXY_URL")

    if git status --porcelain | grep -q .; then
        git add -A
        if git -c user.name="Meng Hao" -c user.email="menghao303@gmail.com" \
               commit -m "CFP check $(date '+%Y-%m-%d'): refresh data and generated files" >> "$LOG" 2>&1; then
            if git "${GIT_PROXY[@]}" push >> "$LOG" 2>&1; then
                echo "=== pushed to GitHub ===" >> "$LOG"
            else
                echo "=== git push FAILED (see log above) ===" >> "$LOG"
            fi
        else
            echo "=== git commit FAILED (see log above) ===" >> "$LOG"
        fi
    else
        echo "=== no changes, nothing to push ===" >> "$LOG"
    fi
else
    echo "=== check failed (exit $rc), skipping git push ===" >> "$LOG"
fi
exit 0
