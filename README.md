# shadowrocket-rules

Shadowrocket 用的**纯广告域名列表**，供配置里的 `DOMAIN-SET` 引用（自动更新）。

- `extras/adblock-217heidai-domains.list`：纯域名列表（一行一个域名，无注释），
  由 `217heidai/adblockfilters` 的 `adblockdomain.txt`（GPL-3.0，每 8 小时更新）清洗后生成，
  并合并了 Johnshall 内嵌广告表中未被其覆盖的域名（`extras/johnshall-only-domains.list`）。
- `.github/workflows/update-adblocklist.yml`：每 8 小时自动拉取上游最新列表并提交。
- `tools/sync_adblocklist.py`：同步脚本（可本地手动运行）。

## 用法（Shadowrocket）

在配置文件 `[Rule]` 最上面加一行：

```
DOMAIN-SET,https://cdn.jsdelivr.net/gh/HyPerP/shadowrocket-rules@main/extras/adblock-217heidai-domains.list,REJECT
```

或（国内访问 jsDelivr 不稳时）：

```
DOMAIN-SET,https://raw.githubusercontent.com/HyPerP/shadowrocket-rules/main/extras/adblock-217heidai-domains.list,REJECT
```

## 来源与许可

- 上游数据：<https://github.com/217heidai/adblockfilters>（GPL-3.0），
  其上游又包含 AdGuard、EasyList、EasyPrivacy、jiekouAD、OISD、hagezi、StevenBlack、Pollock 等公开规则源。
- Johnshall 补充域名来源：<https://github.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever>（CC BY-SA 4.0）。
- 本仓库仅做格式清洗/合并，规则内容的版权与许可遵循上游；如需分发请保留上述来源说明。

## App 去广告模块（单文件通用版，2026-10-30）

`extras/adblock.module`：把 **B 站 + 番茄小说/红果短剧 + 微博** 的 App 专项广告合并为一个通用模块
（域名规则 + URL 改写 + 可选 MITM；默认不启用任何第三方脚本、不含证书）。

- Shadowrocket 使用：配置 → 模块 → 右上角 `+` → 填写链接 →
  `https://cdn.jsdelivr.net/gh/HyPerP/shadowrocket-rules@main/extras/adblock.module`
- 原始地址（jsDelivr 不稳时）：`https://raw.githubusercontent.com/HyPerP/shadowrocket-rules/main/extras/adblock.module`
- 开启「自动更新 → 模块 → 自动后台更新」后，本仓库更新即自动同步到手机；
- 校验工具：`tools/validate_modules.py`（`python tools/validate_modules.py --dir extras`）；
  `.github/workflows/validate-modules.yml` 会在 push 时自动校验模块语法。
- 需要 HTTPS 解密的只有 B 站第 3/4 层与番茄 HTTPS 改写层；红果/微博/B站第 1、2 层不需要。
