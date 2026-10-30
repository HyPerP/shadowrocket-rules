#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_adblocklist.py — 生成「可直接给 Shadowrocket DOMAIN-SET 用」的纯广告域名列表。

数据源
------
217heidai/adblockfilters 的发布产物 `adblockdomain.txt`（每 8 小时更新；合并 AdGuard/EasyList/
EasyPrivacy/jiekouAD/OISD/hagezi 等 15+ 个上游源，已去重、已剔除无法解析的域名）。
它是纯域名列表（带 `!` 头注释），清洗后可直接作为 Shadowrocket 的 DOMAIN-SET 文件使用。

本脚本做的事
------------
1. 下载最新 adblockdomain.txt（直链失败时自动尝试仓库推荐的加速镜像）；
2. 去掉 `!` / `#` 注释与非法行，去重；
3. 可选合并 `extras/johnshall-only-domains.list`（Johnshall 内嵌表里有、217heidai 没有的 9906 个域名，
   避免换源后丢失这部分覆盖）；
4. 写出纯净的域名列表（无注释，一行一个域名），供你放到自己的 GitHub 仓库/Gist 后用
   `DOMAIN-SET,<URL>,REJECT` 引用（Shadowrocket 会自动更新）。

用法（在项目根目录执行）
------------------------
    python tools/sync_adblocklist.py                 # 下载 + 清洗 + 合并，写到 extras/adblock-217heidai-domains.list
    python tools/sync_adblocklist.py --check         # 只检查直链/镜像可达性
    python tools/sync_adblocklist.py --from-file raw.txt   # 用本地已下载的 adblockdomain.txt
    python tools/sync_adblocklist.py --proxy http://127.0.0.1:7890
    python tools/sync_adblocklist.py --out my-domains.list --no-merge

只用 Python 标准库，无需 pip 安装。
"""

import argparse
import hashlib
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(PROJECT_ROOT, "extras", "adblock-217heidai-domains.list")
JOHN_EXTRAS = os.path.join(PROJECT_ROOT, "extras", "johnshall-only-domains.list")

RELEASE_FILE = "adblockdomain.txt"
GITHUB_URL = (
    "https://github.com/217heidai/adblockfilters/releases/download/rule/" + RELEASE_FILE
)
MIRRORS = [
    ("GitHub 直链", GITHUB_URL),
    ("gh-proxy.com", "https://gh-proxy.com/" + GITHUB_URL),
    ("ghfast.top", "https://ghfast.top/" + GITHUB_URL),
    ("github.boki.moe", "https://github.boki.moe/" + GITHUB_URL),
]

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)


def make_opener(proxy):
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener()


def fetch(url, proxy=None, timeout=180):
    opener = make_opener(proxy)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def parse_domains(text):
    """清洗：去注释/空行/非法域名，去重。"""
    out, seen = [], set()
    bad = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("!", "#", ";")):
            continue
        d = s.lower()
        if DOMAIN_RE.match(d):
            if d not in seen:
                seen.add(d)
                out.append(d)
        else:
            bad += 1
    return out, bad


def read_local(path):
    with open(path, "rb") as fh:
        return fh.read()


def save_domains(path, domains):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(domains) + "\n")
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    os.replace(tmp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 Shadowrocket DOMAIN-SET 用的纯广告域名列表")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出文件（默认 extras/adblock-217heidai-domains.list）")
    parser.add_argument("--from-file", default=None, help="用本地已下载的 adblockdomain.txt（离线）")
    parser.add_argument("--proxy", default=None, help="下载代理，如 http://127.0.0.1:7890")
    parser.add_argument("--check", action="store_true", help="只检查直链/镜像可达性，不写文件")
    parser.add_argument("--no-merge", action="store_true", help="不与 johnshall-only-domains.list 合并")
    args = parser.parse_args(argv)

    try:
        if args.check:
            ok = False
            for name, url in MIRRORS:
                try:
                    data = fetch(url, args.proxy, timeout=60)
                    print("OK   %-16s %8d B  %s" % (name, len(data), url))
                    ok = True
                except Exception as exc:  # noqa: BLE001
                    print("FAIL %-16s %s\n     %s" % (name, url, exc))
            return 0 if ok else 1

        if args.from_file:
            raw = read_local(os.path.abspath(args.from_file))
            source = "本地文件 <{0}>".format(args.from_file)
            print("读取本地文件:", args.from_file, len(raw), "B")
        else:
            raw = None
            for name, url in MIRRORS:
                print("尝试下载:", name, url)
                try:
                    raw = fetch(url, args.proxy)
                    if "!" not in raw[:200].decode("utf-8", "ignore") and b"Title:" not in raw[:500]:
                        print("  返回内容不像 adblockdomain.txt，跳过")
                        raw = None
                        continue
                    source = "{0} <{1}>".format(name, url)
                    print("  成功，", len(raw), "B")
                    break
                except Exception as exc:  # noqa: BLE001
                    print("  失败:", exc)
            if raw is None:
                raise RuntimeError(
                    "所有下载源都失败。可尝试：--proxy http://127.0.0.1:7890 / --from-file <本地文件>"
                )

        text = raw.decode("utf-8", "replace")
        domains, bad = parse_domains(text)
        print("解析出域名: {0} 个，跳过非法行: {1} 个".format(len(domains), bad))
        if not domains:
            raise RuntimeError("没有解析出任何域名，已中止（未写文件）。")

        if not args.no_merge and os.path.isfile(JOHN_EXTRAS):
            extras, _ = parse_domains(open(JOHN_EXTRAS, encoding="utf-8").read())
            before = len(domains)
            merged = list(domains)
            seen = set(domains)
            added = 0
            for d in extras:
                if d not in seen:
                    seen.add(d)
                    merged.append(d)
                    added += 1
            domains = merged
            print("合并 johnshall-only-domains.list: +{0} 个（{1} -> {2}）".format(added, before, len(domains)))

        out_path = os.path.abspath(args.out)
        save_domains(out_path, domains)
        size = os.path.getsize(out_path)
        sha = hashlib.sha256(open(out_path, "rb").read()).hexdigest()
        print("")
        print("已生成:", out_path)
        print("  域名数: {0} | 文件大小: {1:.2f} MB | SHA256: {2}".format(len(domains), size / 1048576.0, sha))
        print("  生成时间: {0} | 数据源: 217heidai/adblockfilters".format(
            datetime.now().strftime("%Y-%m-%d %H:%M")))
        print("")
        print("下一步：")
        print("  1) 把这个文件上传到你的 GitHub 仓库（或 Gist），拿到直链/镜像链接；")
        print("  2) 在配置 [Rule] 最上面加一行：")
        print("     DOMAIN-SET,https://cdn.jsdelivr.net/gh/<账号>/<仓库>@main/{0},REJECT".format(
            os.path.basename(out_path)))
        print("  3) 想自动更新：把 tools/github-action-adblocklist.yml 复制到你仓库的 .github/workflows/ 下。")
        return 0
    except RuntimeError as exc:
        print("\n[错误]", exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
