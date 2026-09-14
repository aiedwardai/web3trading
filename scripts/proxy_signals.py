#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web3trading / 代理规则回测（B 层：可每日运行的量化版本）

为什么需要 B 层：
  原规则依赖 MVRV / NUPL / URPD / LTH-STH 分群 / 鲸鱼群组，
  这些**没有免费数据源**（Glassnode 需付费 key），无法每日自动跑。
  B 层用免费可得的真实指标构造"代理版"，让框架能落地成 daily 打分。

代理映射（务必理解这是近似，不是原指标）：
  原: MVRV < 0.6RP / 利润供应% <50%   →  代理: 价格 < MA200（长期成本线之下）
  原: 资金情绪与价格背离 / 散户退潮    →  代理: F&G 极值 + 活跃地址 30 日变化
  原: 已实现利润峰值 / 长持派发       →  代理: 距 200 日低点涨幅 + MA200 乖离
  原: 无量拉升                        →  代理: 链上成交 USD 30 日变化

信号：满足 ≥3 项触发；连续触发只取首日（去噪）。
"""

import datetime as dt
import json
import sys
import urllib.request
from collections import OrderedDict

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def get_json(u):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(u, headers=UA), timeout=30).read().decode())


def day(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def series(chart, timespan="5years"):
    d = get_json(f"https://api.blockchain.info/charts/{chart}?timespan={timespan}&format=json")
    return OrderedDict((day(p["x"]), float(p["y"])) for p in d["values"])


def fng_all():
    d = get_json("https://api.alternative.me/fng/?limit=0")
    return OrderedDict((day(int(x["timestamp"])), int(x["value"])) for x in d["data"])


def ma(ordered, date, n):
    keys = list(ordered.keys())
    if date not in keys:
        return None
    i = keys.index(date)
    if i < n - 1:
        return None
    vals = [ordered[k] for k in keys[i - n + 1:i + 1]]
    return sum(vals) / n


def chg(ordered, date, n):
    keys = list(ordered.keys())
    if date not in keys:
        return None
    i = keys.index(date)
    if i < n:
        return None
    old = ordered[keys[i - n]]
    return (ordered[date] / old - 1) * 100 if old else None


def rolling_extreme(ordered, date, n, mode):
    keys = list(ordered.keys())
    if date not in keys:
        return None
    i = keys.index(date)
    if i < n:
        return None
    w = [ordered[k] for k in keys[i - n:i + 1]]
    return max(w) if mode == "max" else min(w)


def build():
    print("拉取 BTC 价格 / 活跃地址 / 链上成交额 / F&G ...", file=sys.stderr)
    px = series("market-price")
    addr = series("n-unique-addresses")
    vol = series("estimated-transaction-volume-usd")
    fng = fng_all()
    print(f"价格 {len(px)} 点 / 地址 {len(addr)} / 成交 {len(vol)} / F&G {len(fng)}",
          file=sys.stderr)

    dates = [d for d in px.keys() if d >= "2023-06-01"]
    feats, signals = {}, []

    for d in dates:
        p = px[d]
        m200 = ma(px, d, 200)
        if not m200:
            continue
        f = {
            "price": p, "ma200": round(m200, 2),
            "dev_ma200": round((p / m200 - 1) * 100, 2),
            "fng": fng.get(d),
            "addr_d30": None if addr.get(d) is None or chg(addr, d, 30) is None else round(chg(addr, d, 30), 2),
            "vol_d30": None if vol.get(d) is None or chg(vol, d, 30) is None else round(chg(vol, d, 30), 2),
            "hi200": rolling_extreme(px, d, 200, "max"),
            "lo200": rolling_extreme(px, d, 200, "min"),
        }
        f["dd_from_hi200"] = round((p / f["hi200"] - 1) * 100, 2) if f["hi200"] else None
        f["up_from_lo200"] = round((p / f["lo200"] - 1) * 100, 2) if f["lo200"] else None
        # 趋势过滤用：MA200 自身 30 日斜率（>0 表示长期趋势仍向上）
        m200_prev = ma(px, d, 200)
        keys_tmp = list(px.keys())
        idx = keys_tmp.index(d)
        m200_ago = None
        if idx >= 229:
            sub = OrderedDict((k, px[k]) for k in keys_tmp[idx - 229:idx - 29])
            m200_ago = sum(sub.values()) / len(sub) if len(sub) == 200 else None
        f["ma200_slope30"] = (round((m200_prev / m200_ago - 1) * 100, 2)
                              if (m200_ago and m200_prev) else None)

        # ---- 抄底代理（≥3 项）
        b = []
        if f["fng"] is not None and f["fng"] <= 25:
            b.append("F&G≤25 极度恐慌")
        if f["dev_ma200"] is not None and f["dev_ma200"] < 0:
            b.append("价格<MA200")
        if f["addr_d30"] is not None and f["addr_d30"] < -5:
            b.append("活跃地址30日萎缩")
        if f["dd_from_hi200"] is not None and f["dd_from_hi200"] <= -25:
            b.append("距200日高回撤≥25%")
        if f["vol_d30"] is not None and f["vol_d30"] < -30:
            b.append("链上成交30日萎缩≥30%")

        # ---- 逃顶代理（≥3 项）
        t = []
        if f["fng"] is not None and f["fng"] >= 75:
            t.append("F&G≥75 贪婪")
        if f["dev_ma200"] is not None and f["dev_ma200"] > 40:
            t.append("MA200乖离>40%")
        if f["up_from_lo200"] is not None and f["up_from_lo200"] >= 100:
            t.append("较200日低点翻倍")
        if f["addr_d30"] is not None and f["addr_d30"] < -3 and f["dev_ma200"] > 20:
            t.append("价在高位但活跃地址回落")
        if f["vol_d30"] is not None and f["vol_d30"] < -20 and f["dev_ma200"] > 20:
            t.append("高位无量")

        feats[d] = f
        slope = f.get("ma200_slope30")
        if len(b) >= 3:
            signals.append({"date": d, "type": "bottom", "fired": b, "n": len(b),
                            "price": p, "ma200_slope30": slope,
                            "trend_ok": bool(slope is not None and slope > 0)})
        if len(t) >= 3:
            signals.append({"date": d, "type": "top", "fired": t, "n": len(t),
                            "price": p, "ma200_slope30": slope, "trend_ok": True})

    # 去噪：同类型连续信号 30 天内只留首个
    dedup, last = [], {"bottom": None, "top": None}
    for s in signals:
        prev = last[s["type"]]
        if prev and (dt.datetime.strptime(s["date"], "%Y-%m-%d")
                     - dt.datetime.strptime(prev, "%Y-%m-%d")).days < 30:
            continue
        last[s["type"]] = s["date"]
        dedup.append(s)

    # 后续 30/60/90 天真实收益
    keys = list(px.keys())
    for s in dedup:
        i = keys.index(s["date"]) if s["date"] in keys else None
        s["fwd"] = {}
        for h in (30, 60, 90):
            if i is None or i + h >= len(keys):
                s["fwd"][f"d{h}"] = None
                continue
            s["fwd"][f"d{h}"] = round((px[keys[i + h]] / s["price"] - 1) * 100, 2)

    return {"built_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "window": [dates[0], dates[-1]], "n_signals": len(dedup), "signals": dedup}


def report(res):
    print("\n" + "=" * 96)
    print("BTC 代理规则回测 | 窗口", res["window"][0], "~", res["window"][1],
          "| 信号数", res["n_signals"])
    print("=" * 96)
    for typ, label in [("bottom", "抄底"), ("top", "逃顶")]:
        ss = [s for s in res["signals"] if s["type"] == typ]
        print(f"\n【{label}信号】{len(ss)} 个")
        print(f"{'日期':<12}{'价格':>10}{'项':>4} {'30d':>8}{'60d':>8}{'90d':>8}  触发项")
        print("-" * 96)
        hit = {30: 0, 60: 0, 90: 0}
        tot = {30: 0, 60: 0, 90: 0}
        for s in ss:
            cells = []
            for h in (30, 60, 90):
                v = s["fwd"].get(f"d{h}")
                if v is None:
                    cells.append("   n/a")
                    continue
                tot[h] += 1
                good = (v < 0) if typ == "top" else (v > 0)
                if good:
                    hit[h] += 1
                cells.append(f"{v:+7.1f}%")
            print(f"{s['date']:<12}{s['price']:>10.0f}{s['n']:>4} " + " ".join(cells)
                  + "  " + "; ".join(s["fired"][:3]))
        if tot[30]:
            print(f"\n  >>> {label}命中率（方向正确）: "
                  f"30d {hit[30]}/{tot[30]} = {hit[30]/tot[30]*100:.0f}% | "
                  f"60d {hit[60]}/{tot[60]} = {hit[60]/tot[60]*100:.0f}% | "
                  f"90d {hit[90]}/{tot[90]} = {hit[90]/tot[90]*100:.0f}%")
    # 趋势过滤对比：抄底信号只在 MA200 仍向上时才采纳
    bs = [s for s in res["signals"] if s["type"] == "bottom"]
    f_ok = [s for s in bs if s.get("trend_ok")]
    if f_ok:
        print(f"\n【抄底 + 趋势过滤（MA200 斜率>0 才采纳）】{len(f_ok)}/{len(bs)} 个信号保留")
        print(f"{'日期':<12}{'价格':>10} {'30d':>8}{'60d':>8}{'90d':>8}{'MA200斜率':>10}")
        print("-" * 60)
        hit, tot = {30: 0, 60: 0, 90: 0}, {30: 0, 60: 0, 90: 0}
        for s in f_ok:
            cells = []
            for h in (30, 60, 90):
                v = s["fwd"].get(f"d{h}")
                if v is None:
                    cells.append("   n/a"); continue
                tot[h] += 1
                if v > 0:
                    hit[h] += 1
                cells.append(f"{v:+7.1f}%")
            print(f"{s['date']:<12}{s['price']:>10.0f} " + " ".join(cells)
                  + f"{s.get('ma200_slope30') if s.get('ma200_slope30') is not None else '-':>10}")
        print("\n  >>> 过滤后抄底命中率: "
              + " | ".join(f"{h}d {hit[h]}/{tot[h]} = {hit[h]/tot[h]*100:.0f}%"
                           for h in (30, 60, 90) if tot[h]))

    print("\n注：代理指标是对原框架的近似（MVRV/NUPL/URPD 无免费源），仅用于把框架落地成每日可跑的打分。")


if __name__ == "__main__":
    r = build()
    report(r)
    if len(sys.argv) > 1:
        json.dump(r, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[saved] {sys.argv[1]}", file=sys.stderr)
