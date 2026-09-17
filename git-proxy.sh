#!/bin/bash
# 共享的 git 代理探测：被 cfp-check.sh 和 gitp 引用（source），不单独执行。
#
# 背景：全局 git config 里常驻 http.proxy/https.proxy = http://127.0.0.1:10808，
# 指向本机的代理客户端。代理没启动时这个端口连不上，任何 git 网络操作都会直接
# 报 "Failed to connect to 127.0.0.1 port 10808"，而 GitHub 本身是能直连的。
# 所以：端口连得上就走代理，连不上就直连——直连时必须用 -c 显式把配置置空，
# 否则全局配置仍然生效。
#
# detect_git_proxy 设置两个全局量：
#   GIT_PROXY      —— 传给 git 的 -c 参数数组，用法 git "${GIT_PROXY[@]}" push
#   GIT_PROXY_NOTE —— 一行说明，调用方决定要不要打日志
GIT_PROXY_HOST="${GIT_PROXY_HOST:-127.0.0.1}"
GIT_PROXY_PORT="${GIT_PROXY_PORT:-10808}"

detect_git_proxy() {
    local url
    if (exec 3<>"/dev/tcp/$GIT_PROXY_HOST/$GIT_PROXY_PORT") 2>/dev/null; then
        exec 3>&-
        url="http://$GIT_PROXY_HOST:$GIT_PROXY_PORT"
        export HTTP_PROXY="$url" HTTPS_PROXY="$url"
        GIT_PROXY_NOTE="proxy up at $GIT_PROXY_HOST:$GIT_PROXY_PORT, going through it"
    else
        url=""
        unset HTTP_PROXY HTTPS_PROXY
        GIT_PROXY_NOTE="no proxy at $GIT_PROXY_HOST:$GIT_PROXY_PORT, connecting directly"
    fi
    GIT_PROXY=(-c "http.proxy=$url" -c "https.proxy=$url")
}
