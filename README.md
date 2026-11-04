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

`extras/adblock.module`：把 **B 站 + 番茄小说/红果短剧 + 微博 + APP 启动页开屏（约 188 个 App）** 的 App 专项广告合并为一个通用模块
（域名规则 + URL 改写 + 可选 MITM；默认启用 B站脚本（app2smile）与番茄 feed 脚本（fanqie-loon）、不含证书）。

- Shadowrocket 使用：配置 → 模块 → 右上角 `+` → 填写链接 →
  `https://cdn.jsdelivr.net/gh/HyPerP/shadowrocket-rules@main/extras/adblock.module`
- 原始地址（jsDelivr 不稳时）：`https://raw.githubusercontent.com/HyPerP/shadowrocket-rules/main/extras/adblock.module`
- 开启「自动更新 → 模块 → 自动后台更新」后，本仓库更新即自动同步到手机；
- 校验工具：`tools/validate_modules.py`（`python tools/validate_modules.py --dir extras`）；
  `.github/workflows/validate-modules.yml` 会在 push 时自动校验模块语法。
- 需要 HTTPS 解密的只有 B 站第 3/4 层、B站脚本层、番茄 HTTPS 改写层与番茄 feed 脚本层；红果/微博/B站第 1、2 层不需要。

> 2026-11-02 更新：追加 APP 启动页/开屏广告规则（整合 deezertidal/shadowrocket-rules 的 startingad.module，242 条启用 URL 改写，约 188 个 App（12 条过宽/疑似误伤默认注释；[MITM] 保留被规则用到的 211 个新增域））；模块 [MITM] 增至 228 组域名，不开 HTTPS 解密时该部分不生效。

> 2026-11-02 追加 B站脚本层：[Script] 启用 app2smile/rules 的 bilibili-json.js（推荐页/开屏）与 bilibili-proto.js（视频页 View/DynAll），需 HTTPS 解密；MITM 随之增至 228 组。B站异常时注释对应脚本行即可回滚。

> 2026-11-03 追加番茄章末/底部视频广告通道规则：vas-lf-x 只拦带 `encode_user_tag=ad_` 的视频（URL-REGEX，避免整域误伤抖音/正常视频）+ lf-reward-video.bytedcdn.com。

> 2026-11-04 v1.12/v1.13：番茄信息流广告改用 http-response 脚本 `fanqie-feed`（移植自 Loon 插件 fanqie-loon，过滤 feed JSON 里的广告条目）；回滚误伤抖音的 R1 pull-flv、`p*-developer*.bytemaimg` 与诊断 MITM；新增 fanqie-loon 档位 B 的 apm/toblog.snssdk 监控域。模块 81.1 KB / 1,147 行 / SHA256 `CB21221D…`，`[Rule]` 142、URL Rewrite 274、MITM 228、Script 3。

> 旧 deezertidal `fanqie.module` 的逐条审计（哪些已包含、`DOMAIN-KEYWORD,zijieapi` 等为何会误伤抖音）：[docs/fanqie-module-audit.md](docs/fanqie-module-audit.md)。

## 主配置远端副本（2026-11-04）

- `extras/shadowrocket_merged.conf`：主配置的远端副本，`[General]` 带 `update-url`。
- Shadowrocket「配置 → ➕ → 从 URL 下载」：
  `https://cdn.jsdelivr.net/gh/HyPerP/shadowrocket-rules@main/extras/shadowrocket_merged.conf`
- 添加后到「设置 → 自动更新 → 配置」打开自动后台更新（间隔 1 天）；会自动覆盖手机上的本地修改。
- raw 备用：`https://raw.githubusercontent.com/HyPerP/shadowrocket-rules/main/extras/shadowrocket_merged.conf`
