#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web3trading / 取数脚本
在大陆网络环境下的可用数据源封装（已实测 2026-09-06）。

可用（OK）：
  - coins.llama.fi        历史/当前价格（BTC/ETH/SOL/BNB…，coingecko id 体系）
  - api.blockchain.info   BTC 链上指标（活跃地址 / 算力 / 链上成交 USD / UTXO / mempool）
  - api.alternative.me    恐惧贪婪指数（含全历史）
  - stablecoins.llama.fi  稳定币市值
  - mempool.space         mempool / 费率 / 区块

不可用（墙 / 需 key）——脚本会跳过并标记 N/A，不要浪费时间去重试：
  - api.coingecko.com      Tunnel 502
  - api.binance.com        Tunnel 502
  - www.okx.com            Tunnel 502
  - api.exchange.coinbase.com / api.kraken.com / www.bitstamp.net  Tunnel 502
  - api.coincap.io         Tunnel 502
  - min-api.cryptocompare.com  需 API key
  - api.glassnode.com      需 API key（MVRV / NUPL / URPD / LTH-STH 只能靠它）

用法：
  python fetch_chain_data.py                 # 拉当前快照，输出到 stdout + --out 指定 json
  python fetch_chain_data.py --history 2025-04-09,2025-06-11,2026-09-06
  python fetch_chain_data.py --backfill 730  # 拉近 N 天日线价格序列（回测用）
"""

import argparse
import datetime as dt
import json
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TIMEOUT = 30
COINS = {
    "BTC": "coingecko:bitcoin",
    "ETH": "coingecko:ethereum",
    "SOL": "coingecko:solana",
    "BNB": "coingecko:binancecoin",
    "XRP": "coingecko:ripple",
}


def get(url, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def get_json(url, retries=2):
    return json.loads(get(url, retries))


def ts_of(date_str):
    """'2025-04-09' -> unix ts (UTC 00:00)"""
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def fmt_ts(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 价格
def price_now(symbols):
    ids = ",".join(COINS[s] for s in symbols)
    data = get_json(f"https://coins.llama.fi/prices/current/{ids}")
    out = {}
    for s in symbols:
        c = data.get("coins", {}).get(COINS[s])
        if c:
            out[s] = {"price": round(c["price"], 2), "ts": fmt_ts(c["timestamp"]),
                      "confidence": c.get("confidence")}
    return out


def price_on(dates, symbols):
    """批量取历史价格：一次一天一请求（DefiLlama 端点只支持单时间戳）"""
    out = {}
    for d in dates:
        ts = ts_of(d)
        ids = ",".join(COINS[s] for s in symbols)
        try:
            data = get_json(f"https://coins.llama.fi/prices/historical/{ts}/{ids}")
            out[d] = {s: round(data["coins"][COINS[s]]["price"], 2)
                      for s in symbols if COINS[s] in data.get("coins", {})}
        except Exception as e:  # noqa: BLE001
            out[d] = {"error": str(e)}
    return out


def price_series(days, symbols, source="blockchain"):
    """日线序列。BTC 用 blockchain.info（5y 全量，稳）；其它币 DefiLlama 无批量历史端点，逐日取（慢）。"""
    if source == "blockchain" and symbols == ["BTC"]:
        d = get_json("https://api.blockchain.info/charts/market-price?timespan=5years&format=json")
        ser = [(fmt_ts(p["x"]), float(p["y"])) for p in d["values"]]
        return {"BTC": ser[-days:]}
    raise SystemExit("非 BTC 的日线序列请用 price_on() 按日期取点，DefiLlama 无免费批量端点。")


# ---------------------------------------------------------------- 链上
def btc_onchain():
    """BTC 链上指标 + 30 天变化率"""
    charts = {
        "active_addresses": "n-unique-addresses",
        "hash_rate_ths": "hash-rate",
        "onchain_volume_usd": "estimated-transaction-volume-usd",
        "tx_per_day": "n-transactions",
    }
    out = {}
    for k, ch in charts.items():
        try:
            d = get_json(f"https://api.blockchain.info/charts/{ch}?timespan=60days&format=json")
            vals = [p["y"] for p in d["values"]]
            if not vals:
                out[k] = "N/A"
                continue
            cur = vals[-1]
            prev = vals[-31] if len(vals) >= 31 else vals[0]
            out[k] = {"latest": round(float(cur), 2),
                      "d30_change_pct": round((float(cur) / float(prev) - 1) * 100, 2)}
        except Exception as e:  # noqa: BLE001
            out[k] = f"N/A ({type(e).__name__})"
    return out


def fear_greed(limit=7):
    d = get_json(f"https://api.alternative.me/fng/?limit={limit}")
    return [{"date": fmt_ts(int(x["timestamp"])), "value": int(x["value"]),
             "label": x["value_classification"]} for x in d["data"]]


def stablecoin_mcap():
    """稳定币总市值（本框架：稳定币市值 vs CEX 买盘 是否同步）"""
    d = get_json("https://stablecoins.llama.fi/stablecoins")
    total = 0.0
    top = []
    for a in d.get("peggedAssets", []):
        circ = (a.get("circulating") or {}).get("peggedUSD") or 0
        if isinstance(circ, (int, float)):
            total += circ
            top.append((a["symbol"], circ))
    top.sort(key=lambda x: -x[1])
    return {"total_usd": round(total), "top": [(s, round(v)) for s, v in top[:6]]}


def mempool():
    try:
        f = get_json("https://mempool.space/api/v1/fees/recommended")
        return {"fastest_fee": f.get("fastestFee"), "hour_fee": f.get("hourFee"),
                "min_fee": f.get("minimumFee")}
    except Exception as e:  # noqa: BLE001
        return f"N/A ({type(e).__name__})"


# ---------------------------------------------------------------- 派生
def ma(series, n):
    vals = [v for _, v in series]
    if len(vals) < n:
        return None
    return round(sum(vals[-n:]) / n, 2)


def snapshot():
    syms = list(COINS.keys())
    res = {"generated_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
           "price": {}, "btc_onchain": {}, "fear_greed": {}, "stablecoin": {}, "mempool": {},
           "errors": []}
    for name, fn in [("price", lambda: price_now(syms)),
                     ("btc_onchain", btc_onchain),
                     ("fear_greed", lambda: fear_greed(7)),
                     ("stablecoin", stablecoin_mcap),
                     ("mempool", mempool)]:
        try:
            res[name] = fn()
        except Exception as e:  # noqa: BLE001
            res[name] = "N/A"
            res["errors"].append(f"{name}: {type(e).__name__}: {e}")

    # BTC 均线位（本框架：价格 vs MA200 / MA60 乖离）
    try:
        ser = price_series(400, ["BTC"])["BTC"]
        cur = ser[-1][1]
        res["btc_ma"] = {"price": cur, "ma50": ma(ser, 50), "ma200": ma(ser, 200),
                         "dev_ma200_pct": round((cur / ma(ser, 200) - 1) * 100, 2) if ma(ser, 200) else None}
    except Exception as e:  # noqa: BLE001
        res["errors"].append(f"btc_ma: {e}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", help="逗号分隔日期，如 2025-04-09,2025-06-11")
    ap.add_argument("--symbols", default="BTC,ETH")
    ap.add_argument("--out", help="输出 json 路径")
    ap.add_argument("--backfill", type=int, help="拉 BTC 近 N 天日线")
    a = ap.parse_args()

    if a.history:
        res = price_on([d.strip() for d in a.history.split(",")],
                       [s.strip().upper() for s in a.symbols.split(",")])
    elif a.backfill:
        res = price_series(a.backfill, ["BTC"])
    else:
        res = snapshot()

    txt = json.dumps(res, ensure_ascii=False, indent=2)
    print(txt)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\n[saved] {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
