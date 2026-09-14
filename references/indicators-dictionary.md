# 指标全景字典（46 项）

> 标注：🟢 免费可得 ｜ 🟡 免费层部分可得 ｜ 🔴 需付费（Glassnode Advanced+ / CryptoQuant / LookNode 付费层）

| # | 维度 | 指标 | 数据源 | 可得性 | 看多阈值 | 看空阈值 |
|---|---|---|---|---|---|---|
| 1 | D1 | MVRV | LookNode / Glassnode | 🟡 | <1.0 | >2.4 |
| 2 | D1 | MVRV Z-Score | LookNode / Glassnode | 🟡 | <0 | >3（>6 极端） |
| 3 | D1 | NUPL | LookNode / Glassnode | 🟡 | <0.25 | >0.75 |
| 4 | D1 | Ahr999 | LookNode | 🟢 | ≤0.45 | >1.2 |
| 5 | D1 | MVRV Pricing Bands（0.6/1.0/2.4/3.2 RP） | Glassnode | 🟡 | <0.6 RP | >2.4 RP |
| 6 | D1 | 利润供应 % | LookNode / Glassnode | 🟡 | <50% | >95% |
| 7 | D1 | 已实现价格 RP | LookNode | 🟢 | 价格 < RP | 价格 > 2.4 RP |
| 8 | D1 | CVDD / 平衡价格 | LookNode / Glassnode | 🟡 | 接近 = 深底 | 远离 |
| 9 | D1 | NVT | LookNode | 🟢 | 低位 | 高位 |
| 10 | D1 | 距 ATH 回撤 | LookNode / 自算 | 🟢 | >-50% | 接近 0 |
| 11 | D2 | URPD | Glassnode | 🔴 | 下方绿色承接 | 上方红色派发 |
| 12 | D2 | URPD DIFF | Glassnode | 🔴 | 下方净增 | 上方净减 |
| 13 | D2 | LTH 持仓供应 | Glassnode / CryptoQuant | 🔴 | 创新高 | 首次显著减仓 |
| 14 | D2 | STH 持仓供应 | Glassnode | 🔴 | 下降 | 激增 |
| 15 | D2 | STH 成本价 | Glassnode / CryptoQuant | 🔴 | 价格站上 | 跌破不收回 |
| 16 | D2 | LTH 成本价 | CryptoQuant | 🔴 | 价格远高于 | 跌破 |
| 17 | D2 | UTXO 能量带（4 段） | LookNode | 🟡 | 远端惜售 | 近端集中抛售 |
| 18 | D2 | 币龄分布（>2Y / >12M） | LookNode / Glassnode | 🟡 | 稳定 | 大规模止盈 |
| 19 | D2 | 筹码密集区 / 稀疏区 | Glassnode / CryptoQuant | 🔴 | 下方密集 | 上方密集 |
| 20 | D2 | 交易所余额 | LookNode / Glassnode | 🟢 | 下降 | 60 天大幅净流入 |
| 21 | D2 | 活跃地址数 | blockchain.info / LookNode | 🟢 | 30 日 + | 30 日 - 且价新高 |
| 22 | D3 | 鲸鱼群组地址数 | Glassnode | 🔴 | 价↓数↑ | 价↑数↓ |
| 23 | D3 | 鲸鱼群组净流入 | Glassnode | 🔴 | 创 99 分位 | 持续净流出 |
| 24 | D3 | 已实现利润（单日） | LookNode / Glassnode | 🟡 | 低位 | 单日 >$10 亿 |
| 25 | D3 | 已实现亏损（单日） | LookNode | 🟢 | 爆量 = 投降释放 | 二次爆量 = 二次探底 |
| 26 | D3 | LTH 30 日日均获利 | Glassnode | 🔴 | 低位 | >$10 亿且与 STH 差 >3 倍 |
| 27 | D3 | 交易所净流 | LookNode | 🟢 | 净流出 | 大额净流入 |
| 28 | D3 | SOPR / LTH-SOPR | Bitfinex / Glassnode | 🟡 | 稳定 >1 | <0.9 |
| 29 | D3 | ETF 日/周净流入 | SoSoValue / Farside | 🟢 | 持续正 | 单周大幅转负 |
| 30 | D3 | ETF 平均成本 | 自算 / SoSoValue | 🟢 | 现价高于 | 现价低于（浮亏压力） |
| 31 | D3 | LTH 30 日派发量 | CryptoQuant | 🔴 | 有买家吸收 | 无买家且持续 |
| 32 | D4 | 分区域资金情绪（美/亚/欧） | Glassnode | 🔴 | 欧区先正 | 美区回落 + 亚区上升 |
| 33 | D4 | 稳定币总市值 | DeFiLlama / LookNode | 🟢 | 7 日 >+$15 亿 | 7 日 <-$10 亿 |
| 34 | D4 | 稳定币转账量 | 各源 | 🟢 | 与市值同步涨 | 市值停滞而转账暴增 |
| 35 | D4 | CEX 净流入（买盘规模） | Glassnode | 🔴 | 与稳定币同步扩张 | 背离 |
| 36 | D4 | 现货成交量 | CMC / Bitget | 🟢 | 放量突破 | 缩量上涨 |
| 37 | D4 | 链上成交额 30 日变化 | blockchain.info | 🟢 | 转正 | 大幅负（如 -63%） |
| 38 | D4 | 散户交易需求（<$10k） | Glassnode | 🔴 | 见底回升 | 降 >5% |
| 39 | D4 | mempool 费率 | mempool.space | 🟢 | 回升 | 1–2 sat/vB（极冷） |
| 40 | D4 | 恐贪指数 | alternative.me / CoinGlass | 🟢 | <25 | >75 |
| 41 | D4 | BTC Dominance | CMC | 🟢 | 上升（避险） | 下降（轮动至 alt） |
| 42 | D5 | 资金费率 | LookNode / 各所 | 🟢 | 温和正 | 极端正（拥挤） |
| 43 | D5 | 合约 OI | LookNode / Coinglass | 🟢 | 平稳 | 历史高 + 价滞涨 |
| 44 | D5 | Put-Call 比率 / 倒挂 | Deribit / Glassnode | 🟡 | 正常 | 中期 Put > 远期 Put |
| 45 | D5 | 隐含波动率 IV | 期权市场 | 🟢 | 事件后回落 | 极低 + 重大事件 |
| 46 | D6 | 美联储利率概率 | CME FedWatch / Polymarket | 🟢 | 降息定价 | 加息定价 >50% |

---

## 降级替代原则

> 🔴 付费指标缺失时，用 🟢 代理（映射见下），但**代理指标必须加趋势过滤，否则胜率 ≈ 随机**。

| 原指标 | 代理指标 | 数据源 |
|---|---|---|
| MVRV < 0.6RP / 利润供应% <50% | 价格 < MA200 | blockchain.info |
| 资金情绪背离 / 散户退潮 | F&G 极值 + 活跃地址 30 日变化 | alternative.me / blockchain.info |
| 已实现利润峰值 / 长持派发 | 距 200 日低点涨幅 + MA200 乖离 | 派生 |
| 无量拉升 | 链上成交 USD 30 日变化 | blockchain.info |

**⚠️ 特别警告**：代理版**逃顶**信号 30/60/90 天胜率 50%/38%/50% ≈ 随机。
**逃顶必须用真实指标**（MVRV Z / NUPL / 利润供应% / 已实现利润 / LTH 派发）。
