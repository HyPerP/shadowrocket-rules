# deezertidal `fanqie.module` 规则审计（结合 2026-10-29 ~ 11-04 真机日志）

> 背景：用户之前用 [`deezertidal/shadowrocket-rules/modules/fanqie.module`](https://github.com/deezertidal/shadowrocket-rules/blob/main/modules/fanqie.module)，
> 该模块已停止维护；最后使用时的副作用是**抖音图片、评论加载不出来**。本文把它逐条对照我们的模块与 8 份真机日志，
> 说明哪些规则还有用、哪些必须放弃。

## 1. 结论

- **有用的部分：我们的模块已经全部包含**（v1.12），不需要再从旧模块补规则。
- **旧模块里真正伤抖音的是两条“一刀切”规则**，我们一直没启用，也不建议启用：
  1. `DOMAIN-KEYWORD,zijieapi,REJECT`
  2. `DOMAIN-SUFFIX,bytedance.com,REJECT`
- 旧模块没有解决“番茄阅读页信息流广告”的能力（没有 http-response 脚本），这也是我们最终改用
  `fanqie-loon` 的 `fanqie_ad_filter.js` 的原因。

## 2. 旧模块两条“有害规则”的日志证据

统计范围：本机 8 份日志（10-29 ×2、10-30、11-02、11-03、11-04 ×3），共 158,572 条请求。

### 2.1 `DOMAIN-KEYWORD,zijieapi,REJECT`

在日志里会命中 **11,384 条**，其中 **136 条当前是 DIRECT（正常放行）**：

| 被误伤的域名 | DIRECT 次数 | 用途判断 |
| --- | --- | --- |
| `gecko5-hj.zijieapi.com` / `gecko.zijieapi.com` | 25 / 22 | 资源/配置下发 |
| `bsync3-normal-hj/-lf/.zijieapi.com` | 17 / 12 / 9 | 同步/设置 |
| `saveu5-normal-lf/-hl.zijieapi.com` | 9 / 8 | 上传/保存 |
| `ma.zijieapi.com` / `ma3-normal-hl` | 7 / 1 | 监控 |
| `imapi5-oth-lf.zijieapi.com` | 6 | **IM/评论/私信** |
| `vcs-hj/vcs-lf.zijieapi.com` | 5 / 1 | 内容/配置 |
| `abtest3-misc-*` / `keyhub` / `verify` / `edge-inference-*` | 若干 | AB 实验、密钥、验证 |

→ 这正好解释**抖音评论、图片、部分页面加载不出来**。

### 2.2 `DOMAIN-SUFFIX,bytedance.com,REJECT`

命中 **22 条**，全部是 DIRECT：

- `pitaya.bytedance.com` ×22（AB 实验配置下发）

→ 拦掉会影响字节系 App 的配置/实验能力，不必要。

## 3. 其余规则对照

| 旧模块规则 | 日志命中 | 我们的处理 |
| --- | --- | --- |
| `p6/p9-ad-sign.byteimg.com` REJECT | 由 `p*-ad-sign.byteimg.com` 通配覆盖 | 已有（F1 段；A3 先放行 p3-ad-sign/p3-tt） |
| `DOMAIN-SUFFIX,byteimg.com,DIRECT` | — | **不采用**：会撤销我们对 `p*-ad-sign` 的 REJECT；改用 p3-ad-sign/p3-tt 精确白名单 |
| `i/i-lq/is/mcs/security-lq/tnc3-*.snssdk.com` | 全部已 REJECT | 已有 |
| `dig.bdurl.net` | 8,168 次，均 REJECT | 已有 |
| `activity-ag.awemeughun.com`、`sf3-ttcdn-tos.pstatp.com`、`pglstatp-toutiao.com`、`byteorge/bytegoofy` | 命中即 REJECT | 已有 |
| `v6-novelapp.ixigua.com`、`*novelapp.ixigua.com`、`*default.ixigua.com` | 命中 | 已有（DOMAIN-SUFFIX / 通配） |
| `msync-im1-vip6-std.easemob.com`、`apd-pcdnwxlogin.teg.tencent-cloud.net` | 3 次，且被主 DOMAIN-SET 拦 | 保持注释：可能影响其它 App 的聊天/微信登录 |
| `api.iegadp.qq.com` | 0 次 | 无证据，未加 |
| IP-CIDR 6 条 | — | 已有：`101.36.166.16/30`（覆盖 /32）、`180.96.2.114/32` 等 |
| `[URL Rewrite]` 14 条（pangolin、pglstatp/pstatp、byteimg、gurd、snssdk、adim） | — | **全部已有**（R2–R6 段，含 `toutiao.mp4`、`web.business.image`、`tos-cn-i-1yzifmftcy`） |

## 4. 现在的方案（v1.12）

- 番茄**信息流/推荐 feed** 广告：由 `[Script] fanqie-feed`（fanqie-loon 的 `fanqie_ad_filter.js`）按 JSON 广告标记过滤；
- 番茄**开屏/激励/Banner**：穿山甲 SDK 域名 + `gurd` 素材包 + `vas-lf-x` 广告标签规则；
- 番茄**章末/视频流**：`vas-lf-x` 只拦 `encode_user_tag=ad_`；视频流本身仍可能残留（Loon 插件作者也注明此限制）；
- 抖音：不启用 `zijieapi` / `bytedance.com` 一刀切；R1 pull-flv、`p*-developer*.bytemaimg`、诊断 MITM 已回滚。

## 5. 给用户的建议

1. 手机上**只保留我们的通用模块**，删除/停用旧的 `fanqie.module`（两条一刀切规则会与我们的规则叠加，抖音必坏）；
2. 更新到 v1.12，确认 HTTPS 解密开启（脚本必须 MITM）；
3. 若番茄 feed 广告仍在：先确认脚本是否执行（番茄接口是否走 QUIC 绕过 MITM），再导日志；
4. 若抖音还有异常：先确认旧模块已删除，再导日志核对命中的具体规则。
