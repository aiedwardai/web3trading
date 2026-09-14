# 数据源可用性实测（大陆网络环境）

> 实测日期：2026-09-06 | 环境：Windows / 北京

动手前先看这张表。**不要浪费时间重试被墙的源。**

---

## ⭐ LookNode（中文平台，免费层 = 本框架估值维度主力源）

> 2026-09-06 逆向其 SPA（`app.bundle.js`）实测确认。**免费免登录**，大陆直连，
> 覆盖框架估值/资金情绪/鲸鱼行为三大维度的**真实指标**（不再是代理）。

- **API 基址：`https://www.looknode.com/api/{endpoint}`**（响应 `{"code":100,"data":[{t,v}|{t,v1..v13}]}`）
- ⚠️ **坑1**：bundle 里的 `wp.looknode.com/api` 证书已过期 + 返回占位页，**不可用**，必须用 www
- ⚠️ **坑2**：交易所类端点必须带 `?ex=all`（否则 500 "s is null"）
- ⚠️ **坑3**：`t` 时间戳秒/毫秒混用（`t<1e11` 视为秒）
- ⚠️ **坑4**：`code=4001 "JWT parsed err"` = 付费层，免费脚本自动跳过
- ⚠️ **坑5**：`newAddress`、`difficultyRibbon` 端点已停止更新（数据停在 2025-12 / 2025-10），别用

### 免费端点 → 本框架映射（封装见 `scripts/fetch_looknode.py`）

| 框架维度 | 端点 | 含义 / 框架阈值 |
|---|---|---|
| 估值 | `mCapRealizedRatio` | **真实 MVRV**（<1.0 抄底区） |
| 估值 | `MVRVZ` | v1=市值 v2=已实现市值 **v3=MVRV Z**（<0 底 / >6 顶） |
| 估值 | `NUPL` | **真实 NUPL**（<0.25 底 / >0.75 顶） |
| 估值 | `Ahr999` | **Ahr999 指数**（≤0.45 抄底区 / ≤1.2 定投区） |
| 估值 | `realizePrice` | **已实现价格 RP**（0.6RP=深底带，1.0RP=熊市支撑） |
| 估值 | `CVDD` / `balancedPrice` / `historyRetracement` | 底部锚 / 平衡价 / ATH 回撤% |
| 筹码 | `percentInLoss` | 亏损供应%（**利润供应%=1-v，<50% 抄底**） |
| 筹码 | `holdTime` | 币龄分布 v1..v13 |
| 情绪 | `fearAndGreedy` / `stablecoinSupply` | F&G / 稳定币规模 |
| 情绪 | `bFundingRateDetail` / `bOpenInterestDetail` | 各所资金费率 / 合约持仓量 |
| 情绪 | `btcEtfDetailFlow` | 美国 BTC ETF 分发行商流入流出 |
| 鲸鱼 | `exNetFlow2?ex=all` / `exBalance2?ex=all` | **交易所净流 / 余额**（净流出=吸筹迹象） |
| 鲸鱼 | `realizedProfitUsd` / `realizedLos` / `perVolumePro|Los` | 已实现盈亏 USD（投降盘/派发识别） |
| 网络 | `hashRate` / `advanceNVT` / `bdd` / `marketHealth` | 算力 / NVT / BDD |

### 付费层（需登录 JWT，免费拿不到）
URPD_ATH/PER（**URPD DIFF 仍拿不到**）、STH/LTH MVRV & NUPL 分拆、LTH/STH Supply 盈亏、
lth_sopr、lthPositionChange。

---

## ✅ 其他可用

| 源 | 端点 | 提供 | 备注 |
|---|---|---|---|
| **DefiLlama** | `https://coins.llama.fi/prices/current/coingecko:{id}` | 当前价格 | 多币逗号分隔 |
| | `https://coins.llama.fi/prices/historical/{unix_ts}/coingecko:{id}` | 历史价格 | **回测主力源**，confidence 0.99 |
| **blockchain.info** | `https://api.blockchain.info/charts/{chart}?timespan=5years&format=json` | BTC 链上指标 | 5 年日线，稳 |
| | chart = `market-price` | BTC 日线价格 | 与 DefiLlama 交叉验证一致（79,832 vs 79,821） |
| | chart = `n-unique-addresses` | 活跃地址 | 本框架维度 1/2 |
| | chart = `hash-rate` | 算力 | |
| | chart = `estimated-transaction-volume-usd` | 链上成交 USD | "无量拉升"代理 |
| | chart = `n-transactions` | 日交易笔数 | |
| | chart = `utxo-count` | UTXO 数量 | 注意 period=hour，数据量大 |
| **alternative.me** | `https://api.alternative.me/fng/?limit=0` | 恐惧贪婪指数全历史 | limit=0 返回全部 |
| **stablecoins.llama.fi** | `https://stablecoins.llama.fi/stablecoins` | 稳定币市值 | 框架"稳定币 vs 买盘"维度 |
| **mempool.space** | `https://mempool.space/api/v1/fees/recommended` | 费率 | |
| | `https://mempool.space/api/v1/blocks` | 区块 | |

---

## ❌ 不可用（已实测确认，别重试）

| 源 | 失败表现 |
|---|---|
| `api.coingecko.com` | Tunnel connection failed: 502 |
| `api.binance.com` | Tunnel 502 |
| `www.okx.com` | Tunnel 502 |
| `api.exchange.coinbase.com` | Tunnel 502 |
| `api.kraken.com` | Tunnel 502 |
| `www.bitstamp.net` | Tunnel 502 |
| `api.coincap.io` | Tunnel 502 |
| `min-api.cryptocompare.com` | HTTP 401，需 API key |
| `api.glassnode.com` | 需付费 key |

---

## 🔑 仍需付费 key 的指标（LookNode 免费层 + 其他免费源都拿不到）

- **URPD / URPD DIFF**（筹码分布结构）—— 本框架维度1核心，LookNode 付费层或 Glassnode Professional
- **STH/LTH 分拆**（MVRV、NUPL、日均获利差距、Supply 盈亏）—— LookNode 付费层 / Glassnode Advanced
- **鲸鱼群组地址数（1k–10k、≥10k）**
- **分区域资金情绪（美/亚/欧）**、期权 Put-Call

> 2026-09-06 更新：估值维度（MVRV/NUPL/Ahr999/RP/利润供应）已可从 LookNode **免费用真实值**，
> 免费数据能跑的从"全代理"升级为"估值真实 + 趋势/筹码代理"。
> 真实抄底/逃顶信号已接入 `gen_daily_report.py`（2.5 节）。URPD 等关键决策前仍须人工补查。

---

## 踩坑记录

1. **blockchain.info 的 `start` / `end` 参数不生效** —— 它会按 `timespan` 解释并返回固定点数。取长序列直接 `timespan=5years` 拉全量，再在本地按日期切片。
2. **同一指标不同 period** —— `utxo-count` 返回 period=hour，5 years 会有 4 万+ 点，按需用短 timespan。
3. **DefiLlama 历史端点一次只支持一个时间戳** —— 批量回测需循环请求，建议每请求间隔 1–2 秒并带重试。
4. **时间戳用 UTC** —— 与 DefiLlama / F&G 对齐，避免跨日错位。
5. **未来日期** —— DefiLlama 对未来时间戳返回空，回测脚本要跳过未来窗口（否则 `ret_pct = None`）。

---

## 交叉验证建议

至少用两个源对同一数值做校验：

- BTC 现价：DefiLlama vs blockchain.info（实测 79,821 vs 79,832，差 0.01%）
- 若两者差异 >1%，说明某源异常，报告里要标注
