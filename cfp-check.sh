#!/bin/bash
# Weekly CFP check for the deadline calendar (run by launchd every Monday).
# Runs Claude Code headless with the fixed, scoped prompt in cfp-check-prompt.md.
# Tool access is allowlisted to the minimum needed: curl (fetch official CFPs),
# python3 (regenerate outputs), basic file reads/writes in this directory.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
LOG="$DIR/cfp-check.log"
FAIL_MARKER="$DIR/.cfp-check-failed"

ALLOWED="Bash(curl:*),Bash(python3:*),Bash(ls:*),Read,Edit,Write,Glob"

log() { echo "=== $* ===" >> "$LOG"; }

# 发布环节出问题时必须看得见：写日志 + 落一个标记文件 + 弹系统通知。
# 2026-09-14 那次就是因为失败完全无声，站点停更了十天才被发现。
fail() {
    local msg="$1"
    log "$msg"
    { date '+%Y-%m-%d %H:%M:%S'; echo "$msg"; } > "$FAIL_MARKER"
    osascript -e "display notification \"$msg\" with title \"CFP check 发布失败\"" >/dev/null 2>&1 || true
}

# 清理没有进程持有的陈旧 git 锁。
# git 在持锁期间会一直打开锁文件，所以「文件存在 + lsof 查不到持有者」
# 就是上一个 git 进程崩溃/被强杀留下的残留。2026-09-07 一次被杀掉的
# auto-gc 留下了 index.lock / HEAD.lock / objects/maintenance.lock 三个锁，
# 之后每周的自动提交都被它们挡住。
# $1 = 最小存留分钟数，默认 10（刚出现的锁可能属于正在启动的 git，先放过）。
clear_stale_git_locks() {
    local min_age="${1:-10}" lock
    while IFS= read -r lock; do
        [ -e "$lock" ] || continue
        if lsof -- "$lock" >/dev/null 2>&1; then
            log "lock held by a live process, left alone: $lock"
            continue
        fi
        if [ "$min_age" -eq 0 ] || [ -n "$(find "$lock" -mmin +"$min_age" 2>/dev/null)" ]; then
            rm -f "$lock" && log "removed stale git lock: $lock"
        fi
    done < <(find "$DIR/.git" -name '*.lock' -type f 2>/dev/null)
}

do_commit() {
    git -c user.name="Meng Hao" -c user.email="menghao303@gmail.com" \
        commit -m "CFP check $(date '+%Y-%m-%d'): refresh data and generated files" >> "$LOG" 2>&1
}

# 使用 Claude Code 已登录的账号（凭据在 Keychain 里，不需要仓库内的任何 token）。
# 显式清掉可能从环境继承来的第三方网关变量，避免 job 被指到别的 endpoint。
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_MODEL \
      ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL

log "CFP check started $(date '+%Y-%m-%d %H:%M:%S')"

# 上次运行如果卡住没提交，工作区里会留着未提交的改动；开跑前先清锁，
# 这样本次的 git add -A 会把积压的改动一并带上。
clear_stale_git_locks

/Users/haomeng/.local/bin/claude -p "$(cat "$DIR/cfp-check-prompt.md")" \
    --allowedTools "$ALLOWED" \
    >> "$LOG" 2>&1
rc=$?
log "CFP check finished $(date '+%Y-%m-%d %H:%M:%S') (exit $rc)"

if [ "$rc" -ne 0 ]; then
    fail "check failed (exit $rc), skipping git push"
    exit 1
fi

# 核查成功后：有文件变化则提交并推送，公开站点随之更新。
# 代理自动探测：本机代理端口连得上才走代理，否则直连。
# 全局 git config 里配了 http(s).proxy，直连时必须显式置空覆盖它。
PROXY_HOST=127.0.0.1
PROXY_PORT=10808
if (exec 3<>"/dev/tcp/$PROXY_HOST/$PROXY_PORT") 2>/dev/null; then
    exec 3>&-
    PROXY_URL="http://$PROXY_HOST:$PROXY_PORT"
    export HTTPS_PROXY="$PROXY_URL" HTTP_PROXY="$PROXY_URL"
    log "proxy up at $PROXY_HOST:$PROXY_PORT, pushing through it"
else
    PROXY_URL=""
    unset HTTPS_PROXY HTTP_PROXY
    log "no proxy at $PROXY_HOST:$PROXY_PORT, pushing directly"
fi
GIT_PROXY=(-c "http.proxy=$PROXY_URL" -c "https.proxy=$PROXY_URL")

if git status --porcelain | grep -q .; then
    git add -A >> "$LOG" 2>&1
    if ! do_commit; then
        # 第一次失败最常见的原因就是陈旧锁：不看存留时间再清一次，然后重试。
        log "commit failed, clearing locks and retrying once"
        clear_stale_git_locks 0
        if ! do_commit; then
            fail "git commit FAILED twice (see log above) — changes left uncommitted"
            exit 1
        fi
    fi
    if ! git "${GIT_PROXY[@]}" push >> "$LOG" 2>&1; then
        fail "git push FAILED (see log above) — commit is local only"
        exit 1
    fi
    log "pushed to GitHub"
else
    log "no changes, nothing to push"
fi

# 收尾自检：本地 HEAD 必须和远端 main 一致，否则说明有东西没发出去。
git "${GIT_PROXY[@]}" fetch origin main >> "$LOG" 2>&1
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
    fail "local HEAD differs from origin/main after publish — site may be stale"
    exit 1
fi

rm -f "$FAIL_MARKER"
log "publish verified, local HEAD == origin/main"
exit 0
