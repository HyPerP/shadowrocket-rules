#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_modules.py — 校验 extras/*.module（Shadowrocket 模块）语法与跨模块冲突。

为什么需要它
------------
这些模块会被上传到 HyPerP/shadowrocket-rules，手机端按「远程模块 URL」自动更新。
一旦模块语法坏了，手机上表现为模块加载失败/规则静默不生效，很难排查；
所以推送前在本地或 CI 里跑一遍本脚本，把格式/冲突问题挡在手机之外。

用法
----
    python tools/validate_modules.py                      # 校验 extras/ 下所有 *.module
    python tools/validate_modules.py --dir extras
    python tools/validate_modules.py --files extras/bilibili-adblock.module
    python tools/validate_modules.py --allow-scripts      # 允许启用行内 script-path（默认禁止）
    python tools/validate_modules.py --quiet

校验内容
--------
1. 文件编码：UTF-8 无 BOM、LF 换行、无行尾空白、无制表符；
2. 头部 #!name 唯一且非空；#!desc/#!author/#!homepage 建议齐全（缺失只提示）；
3. 节结构：[Rule] / [URL Rewrite] / [MITM] 各最多一个；节内注释与空行允许；
4. [Rule] 行：`TYPE,VALUE,POLICY[,参数...]`，类型/策略/参数白名单检查；
5. [URL Rewrite] 行：`pattern - reject|reject-dict|...` 或 `pattern target 302|307`，
   正则必须能编译；
6. [MITM]：模块内 hostname 必须带 `%APPEND%`；禁止 ca-p12/ca-passphrase 等证书私钥字段；
7. 默认禁止启用状态的第三方脚本（script-path），可选 `--allow-scripts` 放行；
8. 跨模块冲突：同一域名在不同模块里一个 DIRECT 一个 REJECT（或 DOMAIN 落在
   对向策略的 DOMAIN-SUFFIX 之下）→ 报错；同模块内重复规则、多模块重复 URL 改写 → 提示。

退出码：0 = 通过（可能有 warning）；1 = 有 error。
"""

import argparse
import re
import sys
from pathlib import Path

ALLOWED_SECTIONS = {
    "[Rule]",
    "[URL Rewrite]",
    "[MITM]",
    "[Host]",
    "[Hosts]",
    "[General]",
    "[Script]",
    "[Body Rewrite]",
    "[Map Local]",
    "[Header Rewrite]",
    "[Proxy]",
    "[Proxy Group]",
}
SINGLETON_SECTIONS = {"[Rule]", "[URL Rewrite]", "[MITM]"}
REQUIRED_SECTIONS = {"[Rule]"}

RULE_TYPES = {
    "DOMAIN",
    "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD",
    "DOMAIN-WILDCARD",
    "URL-REGEX",
    "USER-AGENT",
    "IP-CIDR",
    "IP-CIDR6",
    "GEOIP",
    "IP-ASN",
    "DST-PORT",
    "PROTOCOL",
    "RULE-SET",
    "DOMAIN-SET",
    "FINAL",
    "AND",
    "OR",
    "NOT",
}
DOMAIN_RULE_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD"}
POLICIES = {
    "REJECT",
    "REJECT-DICT",
    "REJECT-ARRAY",
    "REJECT-200",
    "REJECT-IMG",
    "REJECT-TINYGIF",
    "REJECT-VIDEO",
    "REJECT-DROP",
    "REJECT-NO-DROP",
    "DIRECT",
    "PROXY",
}
RULE_PARAMS = {
    "no-resolve",
    "extended-matching",
    "pre-matching",
    "force-remote-dns",
    "dns-failed",
}
RULESET_PARAMS = {"no-resolve", "extended-matching", "pre-matching"}
REJECT_POLICIES = {p for p in POLICIES if p.startswith("REJECT")}

URL_REWRITE_ACTIONS = {
    "reject",
    "reject-dict",
    "reject-array",
    "reject-200",
    "reject-img",
    "reject-tinygif",
    "reject-video",
    "reject-drop",
    "reject-no-drop",
    "header",
    "302",
    "307",
}
URL_REWRITE_RESERVED = {"header", "302", "307"}

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$", re.I)
HOSTNAME_ITEM_RE = re.compile(r"^[A-Za-z0-9_.*?*-]+$")
URL_REWRITE_RE = re.compile(r"^(?P<pat>.+?)\s+-\s+(?P<action>[A-Za-z0-9-]+)$")
URL_REWRITE_302_RE = re.compile(r"^(?P<pat>.+?)\s+(?P<target>\S+)\s+(?P<code>30[27])$")
SCRIPT_PATH_RE = re.compile(r"(?<![#\s])script-path\s*=")
CA_KEYS = ("ca-p12", "ca-passphrase", "ca-cert")
GENERIC_TLDS = {"com", "net", "org", "cn", "tv", "io", "co", "me", "info", "xyz", "top", "cc", "tv"}


class Diag:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, where, msg):
        self.errors.append((where, msg))

    def warn(self, where, msg):
        self.warnings.append((where, msg))


def read_module(path):
    raw = path.read_bytes()
    problems = []
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("文件带 UTF-8 BOM（Shadowrocket 模块应为无 BOM UTF-8）")
        raw = raw[3:]
    if b"\r\n" in raw:
        problems.append("文件使用 CRLF 换行（应为 LF）")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        problems.append("不是合法 UTF-8：%s" % exc)
        text = raw.decode("utf-8", "replace")
    return text, problems


def parse_sections(text):
    """返回 [(section_name, [(lineno, line), ...]), ...]；头部注释行归属 None 节。"""
    sections = []
    current = ("(header)", [])
    for idx, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]") and stripped in ALLOWED_SECTIONS:
            sections.append(current)
            current = (stripped, [])
            continue
        if stripped.startswith("[") and stripped.endswith("]") and len(stripped) <= 40:
            # 未知节：报错交给调用方处理
            sections.append(current)
            current = (stripped, [])
            continue
        current[1].append((idx, line))
    sections.append(current)
    return sections


def check_header(header_lines, name, diag):
    keys = {}
    for lineno, line in header_lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#!"):
            if "=" not in s:
                diag.error(name, "第 %d 行模块头格式错误：%s" % (lineno, s))
                continue
            k, v = s[2:].split("=", 1)
            k = k.strip().lower()
            keys.setdefault(k, []).append((lineno, v.strip()))
    if "name" not in keys:
        diag.error(name, "缺少 #!name")
    else:
        if len(keys["name"]) > 1:
            diag.error(name, "#!name 出现多次")
        if not keys["name"][0][1]:
            diag.error(name, "#!name 为空")
    for required in ("desc", "author", "homepage"):
        if required not in keys:
            diag.warn(name, "建议补充 #!%s" % required)
    for k, items in keys.items():
        if len(items) > 1 and k != "name":
            diag.warn(name, "#!%s 出现多次（第 %s 行）" % (k, ",".join(str(i[0]) for i in items)))
    return keys.get("name", [(0, "")])[0][1]


def check_rule_line(where, lineno, line, diag):
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("//"):
        return None
    if "=" in s and s.split("=", 1)[0].strip().isidentifier():
        # 节内参数行（如 h2 = true），调用方另行处理
        return None
    parts = [p.strip() for p in s.split(",")]
    if len(parts) < 3:
        diag.error(where, "第 %d 行规则字段不足（应为 TYPE,VALUE,POLICY）：%s" % (lineno, s))
        return None
    rtype, value, policy = parts[0], parts[1], parts[2]
    if rtype not in RULE_TYPES:
        diag.error(where, "第 %d 行未知规则类型 %r：%s" % (lineno, rtype, s))
        return None
    if not value:
        diag.error(where, "第 %d 行规则值为空：%s" % (lineno, s))
    if rtype == "FINAL":
        return None
    if policy not in POLICIES and not policy.strip():
        diag.error(where, "第 %d 行策略为空：%s" % (lineno, s))
    if policy.startswith("REJECT") and policy not in REJECT_POLICIES:
        diag.error(where, "第 %d 行未知 REJECT 变体 %r" % (lineno, policy))
    if rtype in ("RULE-SET", "DOMAIN-SET"):
        if len(parts) >= 3 and parts[2] not in POLICIES and not parts[2].startswith("REJECT"):
            diag.warn(where, "第 %d 行 %s 策略为自定义组名 %r（允许）" % (lineno, rtype, parts[2]))
        return None
    if rtype in DOMAIN_RULE_TYPES and rtype != "DOMAIN-WILDCARD":
        v = value.lower()
        if rtype == "DOMAIN" and not DOMAIN_RE.match(v):
            diag.error(where, "第 %d 行 DOMAIN 值不合法：%r" % (lineno, value))
        if rtype == "DOMAIN-SUFFIX" and not DOMAIN_RE.match(v):
            diag.error(where, "第 %d 行 DOMAIN-SUFFIX 值不合法：%r" % (lineno, value))
    for extra in parts[3:]:
        e = extra.strip()
        if not e:
            continue
        if e not in RULE_PARAMS:
            diag.warn(where, "第 %d 行未知规则参数 %r（如果是最新官方参数请同步本脚本）" % (lineno, e))
    # URL-REGEX 值必须是可编译正则
    if rtype == "URL-REGEX":
        try:
            re.compile(value)
        except re.error as exc:
            diag.error(where, "第 %d 行 URL-REGEX 正则无法编译（%s）：%r" % (lineno, exc, value))
    if rtype in DOMAIN_RULE_TYPES or rtype == "URL-REGEX":
        return {"type": rtype, "value": value if rtype == "URL-REGEX" else value.lower(),
                "policy": policy.upper(), "lineno": lineno, "raw": s}
    return None


def check_url_rewrite(where, lineno, line, diag):
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    m = URL_REWRITE_RE.match(s)
    if m:
        pat, action = m.group("pat").strip(), m.group("action").strip()
        if action not in URL_REWRITE_ACTIONS:
            diag.warn(where, "第 %d 行 URL 改写动作 %r 不在白名单（确认 Shadowrocket 支持）" % (lineno, action))
        try:
            re.compile(pat)
        except re.error as exc:
            diag.error(where, "第 %d 行 URL 改写正则无法编译（%s）：%r" % (lineno, exc, pat))
            return None
        return {"pattern": pat, "action": action.lower(), "lineno": lineno, "raw": s}
    m2 = URL_REWRITE_302_RE.match(s)
    if m2:
        pat = m2.group("pat").strip()
        try:
            re.compile(pat)
        except re.error as exc:
            diag.error(where, "第 %d 行 URL 改写正则无法编译（%s）：%r" % (lineno, exc, pat))
            return None
        return {"pattern": pat, "action": m2.group("code"), "lineno": lineno, "raw": s}
    if " " in s and not s.startswith("'"):
        diag.error(where, "第 %d 行 URL 改写格式无法识别（应为 `pattern - action` 或 `pattern target 302`）：%s" % (lineno, s))
    return None


def check_mitm(where, lines, diag):
    hostnames = []
    saw_hostname = False
    for lineno, line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        for key in CA_KEYS:
            if key in s.lower():
                diag.error(where, "第 %d 行包含证书私钥字段 %r（禁止把 CA 私钥放进公开仓库模块）" % (lineno, key))
        if "=" not in s:
            diag.error(where, "第 %d 行 [MITM] 无法识别的行：%s" % (lineno, s))
            continue
        k, v = s.split("=", 1)
        k, v = k.strip().lower(), v.strip()
        if k == "hostname":
            saw_hostname = True
            if "%APPEND%" not in v:
                diag.error(where, "第 %d 行模块 [MITM] hostname 缺少 %%APPEND%%（会覆盖主配置解密名单）" % lineno)
            v = v.replace("%APPEND%", "").strip()
            for item in re.split(r"[,\s]+", v):
                item = item.strip()
                if not item:
                    continue
                if not HOSTNAME_ITEM_RE.match(item):
                    diag.error(where, "第 %d 行 MITM 主机名不合法：%r" % (lineno, item))
                hostnames.append(item.lower())
        elif k in ("h2", "tcp-connection", "skip-server-cert-verify"):
            if v.lower() not in ("true", "false"):
                diag.error(where, "第 %d 行 MITM 参数 %s 值应为 true/false" % (lineno, k))
        else:
            diag.warn(where, "第 %d 行 [MITM] 未知键 %r（如果官方支持请同步本脚本）" % (lineno, k))
    if not saw_hostname:
        diag.error(where, "[MITM] 缺少 hostname 行")
    return hostnames


def check_file(path, diag, allow_scripts):
    name = path.name
    text, problems = read_module(path)
    for p in problems:
        diag.error(name, p)
    lines = text.split("\n")
    for idx, line in enumerate(lines, 1):
        if line != line.rstrip():
            diag.error(name, "第 %d 行有行尾空白" % idx)
        if "\t" in line:
            diag.warn(name, "第 %d 行含制表符" % idx)
    sections = parse_sections(text)
    seen = {}
    header_name = None
    domain_rules = []
    url_regexes = []
    url_rewrites = []
    mitm_hosts = []
    for sec, body in sections:
        if sec not in (None, "(header)"):
            if sec not in ALLOWED_SECTIONS:
                diag.error(name, "未知节 %r" % sec)
                continue
            seen[sec] = seen.get(sec, 0) + 1
        if sec == "(header)":
            header_name = check_header(body, name, diag)
        elif sec == "[Rule]":
            for lineno, line in body:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if re.match(r"^[A-Za-z0-9_-]+\s*=\s*\S+", s):
                    continue  # 节内参数
                r = check_rule_line(name, lineno, line, diag)
                if r:
                    if r["type"] == "URL-REGEX":
                        url_regexes.append(r)
                    else:
                        domain_rules.append(r)
        elif sec == "[URL Rewrite]":
            for lineno, line in body:
                r = check_url_rewrite(name, lineno, line, diag)
                if r:
                    url_rewrites.append(r)
        elif sec == "[MITM]":
            mitm_hosts = check_mitm(name, body, diag)
        elif sec in ("[Host]", "[Hosts]"):
            for lineno, line in body:
                hs = line.strip()
                if not hs or hs.startswith("#"):
                    continue
                if "=" not in hs:
                    diag.error(name, "第 %d 行 [Host] 格式应为 `域名 = IP` 或 `域名 = server:IP`：%s" % (lineno, hs))
                    continue
                hk, hv = [x.strip() for x in hs.split("=", 1)]
                if not hk or " " in hk:
                    diag.error(name, "第 %d 行 [Host] 域名不合法：%r" % (lineno, hk))
                hv2 = hv
                if hv2.lower().startswith("server:"):
                    hv2 = hv2.split(":", 1)[1].strip()
                import re as _re
                if not (_re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", hv2) or ":" in hv2):
                    diag.error(name, "第 %d 行 [Host] 目标应为 IPv4/IPv6 或 server:IP：%r" % (lineno, hv))
    for sec in REQUIRED_SECTIONS:
        if sec not in seen:
            diag.error(name, "缺少节 %s" % sec)
    for sec, count in seen.items():
        if sec in SINGLETON_SECTIONS and count > 1:
            diag.error(name, "节 %s 出现 %d 次（应只出现一次）" % (sec, count))
    # 默认禁止启用状态的脚本
    if not allow_scripts:
        for lineno, line in enumerate(lines, 1):
            if SCRIPT_PATH_RE.search(line) and not line.lstrip().startswith("#"):
                diag.error(name, "第 %d 行启用了第三方脚本 script-path（远程模块默认应注释掉脚本）" % lineno)
    # 同模块重复规则
    pair_seen = {}
    for r in domain_rules:
        key = (r["type"], r["value"])
        if key in pair_seen:
            prev = pair_seen[key]
            if prev["policy"] == r["policy"]:
                diag.warn(name, "第 %d 行规则与第 %d 行重复：%s" % (r["lineno"], prev["lineno"], r["raw"]))
            else:
                diag.error(name, "第 %d 行与第 %d 行同域名不同策略：%s vs %s" % (r["lineno"], prev["lineno"], prev["raw"], r["raw"]))
        else:
            pair_seen[key] = r
    return {
        "file": name,
        "header_name": header_name or "",
        "domain_rules": domain_rules,
        "url_regexes": url_regexes,
        "url_rewrites": url_rewrites,
        "mitm_hosts": mitm_hosts,
        "sections": seen,
    }


def _mitm_covered(host, mitm_hosts):
    import fnmatch
    host = host.lower().strip(".")
    for h in mitm_hosts:
        h = h.lower().strip()
        if not h:
            continue
        if h.startswith("*.") and (host == h[2:] or host.endswith(h[1:])):
            return True
        if "*" in h or "?" in h:
            if fnmatch.fnmatchcase(host, h):
                return True
        elif host == h:
            return True
    return False


def _literal_url_host(pattern):
    r"""从 `^https?:\/\/host\/...` 里取“纯字面主机名”；含正则元字符则返回 None。"""
    import re as _re
    m = _re.match(r"^\^?https\?:\\/\\/([^\\/?]+)", pattern)
    if not m:
        return None
    h = m.group(1).replace("\\", "")
    if _re.match(r"^[A-Za-z0-9.-]+$", h) and "." in h:
        return h
    return None


def mitm_coverage_check(modules, diag):
    """URL 改写 / URL-REGEX 里能解析出字面域名、且走 https 的，必须被 [MITM] 覆盖，否则静默失效。"""
    for m in modules:
        for r in m["url_rewrites"]:
            if "https" not in r["pattern"]:
                continue
            host = _literal_url_host(r["pattern"])
            if host and not _mitm_covered(host, m["mitm_hosts"]):
                diag.warn(m["file"], "第 %d 行 URL 改写含 https 但 [MITM] 未覆盖 %s（不开解密时静默失效）" % (
                    r["lineno"], host))
        for r in m.get("url_regexes", []):
            import re as _re
            hosts = _re.findall(r"[A-Za-z0-9-]+\.(?:com|net|cn|org|tv|io)", r["value"].replace("\\", ""))
            if not hosts:
                continue
            for h in hosts:
                if not _mitm_covered(h, m["mitm_hosts"]):
                    diag.warn(m["file"], "第 %d 行 URL-REGEX 可能是 https 规则但 [MITM] 未覆盖 %s（不覆盖则静默失效）" % (
                        r["lineno"], h))
                    break


def conflict_check(modules, diag):
    # 模块名跨文件唯一
    names = {}
    for m in modules:
        if m["header_name"]:
            names.setdefault(m["header_name"], []).append(m["file"])
    for name, files in names.items():
        if len(files) > 1:
            diag.error(name, "多个模块使用相同 #!name（手机模块列表中会混淆）：%s" % ", ".join(files))
    # 跨模块：同 type+value 不同策略
    table = {}
    for m in modules:
        for r in m["domain_rules"]:
            key = (r["type"], r["value"])
            table.setdefault(key, []).append((m["file"], r))
    for (rtype, value), items in table.items():
        policies = {it[1]["policy"] for it in items if it[1]["policy"] in POLICIES or it[1]["policy"].startswith("REJECT")}
        files = {it[0] for it in items}
        if len(files) > 1 and len(policies) > 1:
            diag.error(value, "跨模块同域名不同策略：%s -> %s（文件：%s）" % (
                value, sorted(policies), ", ".join(sorted(files))))
    # 跨模块 DOMAIN 落入对向策略的 DOMAIN-SUFFIX
    for m in modules:
        for r in m["domain_rules"]:
            if r["type"] != "DOMAIN" or r["policy"] not in ("DIRECT",) and not r["policy"].startswith("REJECT"):
                continue
            for m2 in modules:
                if m2["file"] == m["file"]:
                    continue
                for s in m2["domain_rules"]:
                    if s["type"] != "DOMAIN-SUFFIX":
                        continue
                    if not (r["value"] == s["value"] or r["value"].endswith("." + s["value"])):
                        continue
                    p1, p2 = r["policy"], s["policy"]
                    if (p1 == "DIRECT") != (p2 == "DIRECT"):
                        diag.warn(r["value"], "跨模块可能冲突：%s 的 DOMAIN %s=%s 落在 %s 的 DOMAIN-SUFFIX %s=%s 下（按模块顺序谁先命中谁生效）" % (
                            m["file"], r["value"], p1, m2["file"], s["value"], p2))
    # URL Rewrite 重复
    rewrites = {}
    for m in modules:
        for r in m["url_rewrites"]:
            key = r["pattern"]
            rewrites.setdefault(key, []).append((m["file"], r))
    for pat, items in rewrites.items():
        files = {it[0] for it in items}
        if len(files) > 1:
            diag.warn(pat, "多个模块包含相同 URL 改写：%s -> %s" % (
                pat, ", ".join(sorted(files))))


def main(argv=None):
    parser = argparse.ArgumentParser(description="校验 Shadowrocket 模块（extras/*.module）")
    parser.add_argument("--dir", default="extras", help="模块目录（默认 extras）")
    parser.add_argument("--files", nargs="*", default=None, help="只校验指定文件")
    parser.add_argument("--allow-scripts", action="store_true", help="允许启用状态的 script-path")
    parser.add_argument("--quiet", action="store_true", help="只输出错误/警告")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    if args.files:
        files = [Path(f) if Path(f).is_absolute() else (root / f) for f in args.files]
    else:
        base = Path(args.dir)
        if not base.is_absolute():
            base = root / base
        files = sorted(base.glob("*.module"))
    if not files:
        print("[ERROR] 没有找到任何 .module 文件", file=sys.stderr)
        return 1

    diag = Diag()
    modules = []
    for path in files:
        if not path.is_file():
            diag.error(str(path), "文件不存在")
            continue
        result = check_file(path, diag, args.allow_scripts)
        modules.append(result)
        if not args.quiet:
            sec = result["sections"]
            print("== %s ==" % result["file"])
            print("   name: %s" % result["header_name"])
            print("   sections: %s" % ", ".join("%s×%d" % (k, v) for k, v in sorted(sec.items())))
            print("   domain rules: %d | url-regex: %d | url rewrites: %d | mitm hosts: %d" % (
                len(result["domain_rules"]), len(result.get("url_regexes", [])),
                len(result["url_rewrites"]), len(result["mitm_hosts"])))
    conflict_check(modules, diag)
    mitm_coverage_check(modules, diag)

    for where, msg in diag.warnings:
        print("[WARN] %s: %s" % (where, msg))
    for where, msg in diag.errors:
        print("[ERROR] %s: %s" % (where, msg))
    print("")
    print("结果：%d 个模块，%d error，%d warning" % (len(modules), len(diag.errors), len(diag.warnings)))
    return 0 if not diag.errors else 1


if __name__ == "__main__":
    sys.exit(main())
