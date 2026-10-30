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
