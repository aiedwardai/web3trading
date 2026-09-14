#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web3trading / 回测脚本（A 层：信号锚点 → 真实收益）

方法：
  取 PPT/PDF 中**明确记录过判断的历史时点**（信号日），用 DefiLlama 拉真实价格，
  计算信号日之后 30/60/90 天的真实涨跌幅，检验"逃顶/抄底"判断的实际效果。

诚实边界（必读）：
  - 信号日来自原作者真实判断（有 PPT 页码出处），**不是事后拟合**；
  - 链上指标的历史序列（MVRV/NUPL/URPD/鲸鱼分群）无免费源，
    因此"触发了几条规则"只能按原始材料中记载的读数还原，未记载的项标 unknown；
  - 收益是真实价格算出来的，不是估计。
"""

import datetime as dt
import json
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
COINS = {"BTC": "coingecko:bitcoin", "ETH": "coingecko:ethereum",
         "SOL": "coingecko:solana", "BNB": "coingecko:binancecoin"}


def price_on(date_str, symbols, retries=3):
    ts = int(dt.datetime.strptime(date_str, "%Y-%m-%d")
             .replace(tzinfo=dt.timezone.utc).timestamp())
    ids = ",".join(COINS[s] for s in symbols)
    for i in range(retries):
        try:
            req = urllib.request.Request(
                f"https://coins.llama.fi/prices/historical/{ts}/{ids}", headers=UA)
            data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
            return {s: round(data["coins"][COINS[s]]["price"], 2) for s in symbols}
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                return {"error": str(e)}
            time.sleep(2)
    return {}


def plus_days(d, n):
    return (dt.datetime.strptime(d, "%Y-%m-%d") + dt.timedelta(days=n)).strftime("%Y-%m-%d")


# 信号锚点：date, asset, call(抄底/逃顶/转熊), 触发规则项数(known/unknown), 出处
SIGNALS = [
    {"date": "2024-03-14", "asset": "BTC", "call": "top", "fired": 3, "unknown": 5,
     "src": "PPT s7 去年三月判断波段逃顶止盈", "note": "BTC 73.8k 阶段顶"},
    {"date": "2024-12-17", "asset": "BTC", "call": "top", "fired": 4, "unknown": 4,
     "src": "PPT s7/s8 十二月逃顶；鲸鱼参与度 62%→38%", "note": "BTC 首破 10 万后"},
    {"date": "2025-02-25", "asset": "BTC", "call": "top", "fired": 3, "unknown": 5,
     "src": "PPT s9/s10 2025年2月提示下跌趋势开始", "note": "牛→熊关键转折点"},
    {"date": "2025-04-09", "asset": "BTC", "call": "bottom", "fired": 4, "unknown": 2,
     "src": "PPT s11/s12 BTC四月抄底；超级鲸鱼买入+期权一边倒看跌", "note": "BTC ~76k"},
    {"date": "2025-04-19", "asset": "ETH", "call": "bottom", "fired": 4, "unknown": 2,
     "src": "PPT s3 ETH $1585 抄底；MVRV 跌破 0.6RP", "note": "目标 1850-2050-2200"},
    {"date": "2025-06-11", "asset": "ETH", "call": "top", "fired": 4, "unknown": 4,
     "src": "PPT s3/s4 ETH $2815 提示短期到顶；Bitfinex 100万枚加速卖出+Blackrock 利好",
     "note": "拉盘+利好=掩护出货"},
    {"date": "2025-07-02", "asset": "BTC", "call": "target", "fired": 0, "unknown": 0,
     "src": "PPT s41 2025 BTC 不言顶，至少 130K-150K", "note": "目标价检验"},
    {"date": "2025-10-09", "asset": "BNB", "call": "top", "fired": 6, "unknown": 2,
     "src": "PDF《BNB链上数据与行情分析》BNB 1349.99 全部换仓 BTC",
     "note": "MVRV Z 3.6 / 泡沫 202% / 无量拉升"},
    {"date": "2026-09-06", "asset": "BTC", "call": "now", "fired": 0, "unknown": 0,
     "src": "当前快照", "note": "BTC ~79.8k"},
]

HORIZONS = [30, 60, 90]


def run():
    syms = sorted({s["asset"] for s in SIGNALS})
    need = {}
    for s in SIGNALS:
        for h in [0] + HORIZONS:
            d = plus_days(s["date"], h)
            need.setdefault(d, []).append(s["asset"])
    # 一次性按日期取（同一天的多个币合并成一次请求）
    today = dt.datetime.now(dt.timezone.utc).date()
    cache = {}
    for d in sorted(need):
        if dt.datetime.strptime(d, "%Y-%m-%d").date() > today:
            print(f"  skip future {d}", file=sys.stderr)
            continue
        assets = sorted(set(need[d]))
        cache[d] = price_on(d, assets)
        print(f"  fetched {d} {assets} -> {cache[d]}", file=sys.stderr)

    rows = []
    for s in SIGNALS:
        d0 = s["date"]
        p0 = cache.get(d0, {}).get(s["asset"])
        row = {**s, "price_at_signal": p0, "fwd": {}}
        for h in HORIZONS:
            dh = plus_days(d0, h)
            ph = cache.get(dh, {}).get(s["asset"])
            if isinstance(p0, (int, float)) and isinstance(ph, (int, float)) and p0:
                row["fwd"][f"d{h}"] = {"date": dh, "price": ph,
                                       "ret_pct": round((ph / p0 - 1) * 100, 2)}
            else:
                row["fwd"][f"d{h}"] = {"date": dh, "price": ph, "ret_pct": None}
        rows.append(row)
    return {"fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "source": "DefiLlama coins.llama.fi historical prices", "signals": rows}


if __name__ == "__main__":
    res = run()
    out = sys.argv[1] if len(sys.argv) > 1 else None
    txt = json.dumps(res, ensure_ascii=False, indent=2)
    print(txt)
    if out:
        open(out, "w", encoding="utf-8").write(txt)
        print(f"[saved] {out}", file=sys.stderr)
