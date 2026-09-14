#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web3trading / 每日监控看板生成器

编排：fetch_chain_data.snapshot() -> 评分（免费代理规则）-> Markdown 看板
落盘到工作区 monitor/ 目录：
  monitor/daily_chain_monitor_YYYY-MM-DD.md   每日看板
  monitor/snapshot_YYYY-MM-DD.json            原始快照
  monitor/proxy_YYYY-MM-DD.json               代理打分明细
  monitor/weekly_chain_review_YYYY-MM-DD.md   周一额外周报

用法：
  python gen_daily_report.py
  python gen_daily_report.py --date 2026-09-06   # 指定日期（UTC 取数）
设计原则（本框架铁律）：
  - 结论先行：抄底 / 观望 / 减仓
  - 实测项 / 代理项 / N/A 三类必须明确标注
  - 抄底信号必须先过趋势过滤（MA200 斜率>0），否则不采纳
  - 不给绝对目标价
"""

import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fetch_chain_data as fc   # noqa: E402
import fetch_looknode as ln     # noqa: E402
import proxy_signals as ps      # noqa: E402

WORKSPACE = "D:/AIworkspace/workbuddy/0906-AI投研-蒸馏链上数据研报"
MON = os.path.join(WORKSPACE, "monitor")

BG_RED = "#C8161D"
GREEN = "#1A8F4C"


# ------------------------------------------------------------- 工具
def ma_at(series, end_idx, n):
    """series: list[(date,price)]，返回截至 end_idx 的 n 日均线"""
    if end_idx < n - 1:
        return None
    vals = [v for _, v in series[end_idx - n + 1:end_idx + 1]]
    return sum(vals) / len(vals) if len(vals) == n else None


def rolling_extreme_at(series, end_idx, n, mode):
    if end_idx < n:
        return None
    w = [v for _, v in series[end_idx - n + 1:end_idx + 1]]
    return max(w) if mode == "max" else min(w)


def safe(obj, key, default=None):
    if isinstance(obj, dict) and key in obj:
        v = obj[key]
        return v if not isinstance(v, str) or "N/A" not in v else default
    return default


# ------------------------------------------------------------- 当前快照评分
def score_now(snap):
    """用 fetch 快照 + BTC 日线序列 评估 5 项抄底 / 5 项逃顶代理规则"""
    price = safe(snap.get("price", {}), "BTC", {}).get("price")
    out = {"price": price, "bottom": [], "top": [], "trend_ok": None, "fng": None,
           "ma200": None, "dev_ma200": None}

    # 日线序列（BTC 近 400 天）
    try:
        ser = fc.price_series(400, ["BTC"])["BTC"]
        idx = len(ser) - 1
        ma200 = ma_at(ser, idx, 200)
        ma200_30ago = ma_at(ser, idx - 30, 200) if idx >= 30 else None
        hi200 = rolling_extreme_at(ser, idx, 200, "max")
        lo200 = rolling_extreme_at(ser, idx, 200, "min")
        out["ma200"] = round(ma200, 2) if ma200 else None
        out["dev_ma200"] = round((price / ma200 - 1) * 100, 2) if (price and ma200) else None
        dd_hi = round((price / hi200 - 1) * 100, 2) if (price and hi200) else None
        up_lo = round((price / lo200 - 1) * 100, 2) if (price and lo200) else None
        slope = (round((ma200 / ma200_30ago - 1) * 100, 2)
                 if (ma200 and ma200_30ago) else None)
        out["trend_ok"] = bool(slope is not None and slope > 0)
        out["ma200_slope30"] = slope
    except Exception as e:  # noqa: BLE001
        dd_hi = up_lo = slope = None
        out["series_err"] = str(e)

    # F&G 最新
    fg = snap.get("fear_greed") or []
    fng_val = fg[0]["value"] if fg and isinstance(fg[0], dict) else None
    out["fng"] = fng_val

    # 链上：活跃地址 30 日变化、链上成交额 30 日变化
    oc = snap.get("btc_onchain") or {}
    addr_d30 = safe(oc.get("active_addresses"), "d30_change_pct")
    vol_d30 = safe(oc.get("onchain_volume_usd"), "d30_change_pct")

    dev = out["dev_ma200"]
    # ---- 抄底 5 项
    b = []
    if fng_val is not None:
        b.append(("F&G ≤ 25 极度恐慌", fng_val <= 25, fng_val))
    if dev is not None:
        b.append(("价格 < MA200（长期成本线下）", dev < 0, f"{dev:+.1f}%"))
    if addr_d30 is not None:
        b.append(("活跃地址 30 日萎缩 <-5%", addr_d30 < -5, f"{addr_d30:+.1f}%"))
    if dd_hi is not None:
        b.append(("距 200 日高点回撤 ≥25%", dd_hi <= -25, f"{dd_hi:+.1f}%"))
    if vol_d30 is not None:
        b.append(("链上成交额 30 日萎缩 ≥30%", vol_d30 < -30, f"{vol_d30:+.1f}%"))
    out["bottom"] = b

    # ---- 逃顶 5 项
    t = []
    if fng_val is not None:
        t.append(("F&G ≥ 75 贪婪", fng_val >= 75, fng_val))
    if dev is not None:
        t.append(("MA200 乖离 > 40%", dev > 40, f"{dev:+.1f}%"))
    if up_lo is not None:
        t.append(("较 200 日低点涨幅 ≥100%", up_lo >= 100, f"{up_lo:+.1f}%"))
    if addr_d30 is not None and dev is not None:
        t.append(("价高位但活跃地址回落", addr_d30 < -3 and dev > 20,
                  f"addr {addr_d30:+.1f}% / dev {dev:+.1f}%"))
    if vol_d30 is not None and dev is not None:
        t.append(("高位无量（成交 30 日萎缩）", vol_d30 < -20 and dev > 20,
                  f"vol {vol_d30:+.1f}% / dev {dev:+.1f}%"))
    out["top"] = t

    out["bottom_fired"] = sum(1 for _, ok, _ in b if ok)
    out["top_fired"] = sum(1 for _, ok, _ in t if ok)
    return out


def verdict(s):
    """结论：抄底 / 减仓 / 观望（先过趋势过滤）"""
    b, t = s["bottom_fired"], s["top_fired"]
    trend = s.get("trend_ok")
    if t >= 3:
        return "减仓 / 防御", f"逃顶代理触发 {t} 项（≥3 即预警，须分批减仓）"
    if b >= 3 and trend:
        return "抄底区关注", f"抄底代理触发 {b} 项且趋势过滤通过（MA200 斜率>0）"
    if b >= 3 and not trend:
        return "观望（趋势未确认）", f"抄底触发 {b} 项，但 MA200 斜率≤0，下降趋势不采纳"
    return "观望", f"抄底 {b} 项 / 逃顶 {t} 项，均未达 ≥3 阈值"


# --------------------------------------------------- LookNode 真实估值信号
def real_valuation(price, lns):
    """用 LookNode 真实指标做 本框架『估值水位』打分（非代理）。
    返回 {bottom:[(名,ok,值)], top:[...], vals:{...}, zone: str}"""
    def g(ep, key="v"):
        rec = lns.get(ep) or {}
        return rec.get(key)

    mvrv = g("mCapRealizedRatio")
    z = g("MVRVZ", "v3")
    nupl = g("NUPL")
    ahr = g("Ahr999")
    rp = g("realizePrice")
    pil = g("percentInLoss")           # 亏损供应比例
    pip = (1 - pil) if isinstance(pil, (int, float)) else None  # 利润供应比例
    ret = {"bottom": [], "top": [], "vals": {}}

    if mvrv is not None:
        ret["vals"]["MVRV"] = mvrv
        ret["bottom"].append(("MVRV < 1.0（价格低于已实现价格）", mvrv < 1.0, f"{mvrv:.3f}"))
    if z is not None:
        ret["vals"]["MVRV_Z"] = z
        ret["bottom"].append(("MVRV Z-Score < 0（历史底部区）", z < 0, f"{z:.3f}"))
        ret["top"].append(("MVRV Z-Score > 6（历史顶部区）", z > 6, f"{z:.3f}"))
    if nupl is not None:
        ret["vals"]["NUPL"] = nupl
        ret["bottom"].append(("NUPL < 0.25（希望/恐惧区）", nupl < 0.25, f"{nupl:.3f}"))
        ret["top"].append(("NUPL > 0.75（狂喜区）", nupl > 0.75, f"{nupl:.3f}"))
    if ahr is not None:
        ret["vals"]["Ahr999"] = ahr
        ret["bottom"].append(("Ahr999 ≤ 0.45（抄底区；<1.2 定投区）", ahr <= 0.45, f"{ahr:.3f}"))
    if pip is not None:
        ret["vals"]["profit_supply"] = pip
        ret["bottom"].append(("利润供应 < 50%（抄底阈值）", pip < 0.50, f"{pip*100:.1f}%"))
        ret["top"].append(("利润供应 > 95%（浮筹全利润）", pip > 0.95, f"{pip*100:.1f}%"))
    if rp is not None and price:
        ret["vals"]["realized_price"] = rp
        ret["bottom"].append((f"价格 < 已实现价格 ${rp:,.0f}", price < rp, f"${price:,.0f}"))

    ret["bottom_fired"] = sum(1 for _, ok, _ in ret["bottom"] if ok)
    ret["top_fired"] = sum(1 for _, ok, _ in ret["top"] if ok)

    # 估值区带判词
    if ahr is not None:
        if ahr <= 0.45:
            zone = "历史抄底区（Ahr999<0.45）"
        elif ahr <= 1.2:
            zone = "定投区（Ahr999 0.45~1.2）"
        else:
            zone = "持有/观望区（Ahr999>1.2）"
    else:
        zone = "N/A"
    ret["zone"] = zone
    return ret


# ------------------------------------------------------------- Markdown
def md_daily(snap, sc, rv, v_text, v_reason, date_str):
    price = sc.get("price")
    fg = snap.get("fear_greed") or []
    fng_now = fg[0] if fg else {}
    stable = snap.get("stablecoin") or {}
    memp = snap.get("mempool")
    bma = snap.get("btc_ma") or {}

    def row(items):
        return "| " + " | ".join(items) + " |"

    lines = []
    lines.append(f"# 链上数据每日监控看板 · {date_str}\n")
    lines.append(f"> **结论：{v_text}** —— {v_reason}\n")
    lines.append("## 1. 当前快照\n")
    lines.append(row(["指标", "数值", "说明"]))
    lines.append(row(["---", "---", "---"]))
    lines.append(row(["BTC 价格", f"${price:,.0f}" if price else "N/A",
                      "DefiLlama"]))
    lines.append(row(["ETH 价格", f"${safe(snap.get('price',{}),'ETH',{}).get('price','N/A')}",
                      "DefiLlama"]))
    lines.append(row(["F&G 指数", f"{fng_now.get('value','N/A')} ({fng_now.get('label','-')})",
                      "alternative.me"]))
    lines.append(row(["稳定币总市值", f"${stable.get('total_usd',0)/1e9:,.1f}B" if stable.get('total_usd') else "N/A",
                      "stablecoins.llama.fi"]))
    lines.append(row(["MA200 乖离", f"{bma.get('dev_ma200_pct','N/A')}%",
                      "blockchain.info 价格序列"]))
    lines.append(row(["mempool 费率", f"{safe(memp,'fastest_fee')} sat/vB" if isinstance(memp, dict) else "N/A",
                      "mempool.space"]))
    lines.append("")

    lines.append("## 2. 六维信号打分（代理 + 实测混合）\n")
    lines.append("> ⚠️ 本看板按 **六维框架（D1 筹码 / D2 资金情绪 / D3 估值 / D4 鲸鱼 / D5 衍生品 / D6 宏观）** 组织："
                 "本节为 D1 筹码/量能代理信号，2.5 节为 D3 估值真实指标（LookNode 实测）；"
                 "D2/D4/D5/D6 完整判定见 `onchain_scorecard.py`。\n")
    lines.append(f"### 抄底代理（当前 {sc['bottom_fired']}/5，趋势过滤={'通过' if sc.get('trend_ok') else '不通过'}）\n")
    lines.append(row(["规则", "状态", "当前值"]))
    lines.append(row(["---", "---", "---"]))
    for name, ok, val in sc["bottom"]:
        lines.append(row([name, "✅" if ok else "⬜", str(val)]))
    lines.append("")
    lines.append(f"### 逃顶代理（当前 {sc['top_fired']}/5）\n")
    lines.append(row(["规则", "状态", "当前值"]))
    lines.append(row(["---", "---", "---"]))
    for name, ok, val in sc["top"]:
        lines.append(row([name, "✅" if ok else "⬜", str(val)]))
    lines.append("")

    # --- 真实估值指标（LookNode 实测）---
    vals = rv.get("vals", {})
    lines.append("## 2.5 真实估值指标（LookNode 实测，非代理）\n")
    lines.append(row(["指标", "最新值", "30 天前", "框架阈值"]))
    lines.append(row(["---", "---", "---", "---"]))
    mvrv = vals.get("MVRV"); z = vals.get("MVRV_Z"); nupl = vals.get("NUPL")
    ahr = vals.get("Ahr999"); rp = vals.get("realized_price"); pip = vals.get("profit_supply")
    lines.append(row(["真实 MVRV", f"{mvrv:.3f}" if mvrv else "N/A", "—",
                      "<1.0 抄底区"]))
    lines.append(row(["MVRV Z-Score", f"{z:.3f}" if z else "N/A", "—",
                      "<0 底部 / >6 顶部"]))
    lines.append(row(["NUPL", f"{nupl:.3f}" if nupl else "N/A", "—",
                      "<0.25 底部 / >0.75 顶部"]))
    lines.append(row(["Ahr999", f"{ahr:.3f}" if ahr else "N/A", "—",
                      "≤0.45 抄底 / ≤1.2 定投"]))
    lines.append(row(["已实现价格 RP", f"${rp:,.0f}" if rp else "N/A", "—",
                      "0.6RP=$%s（深底带）" % f"{rp*0.6:,.0f}" if rp else "—"]))
    lines.append(row(["利润供应", f"{pip*100:.1f}%" if pip else "N/A", "—",
                      "<50% 抄底 / >95% 顶部"]))
    lines.append("")
    lines.append(f"### 真实抄底信号（{rv['bottom_fired']}/{len(rv['bottom'])}）\n")
    lines.append(row(["规则", "状态", "当前值"]))
    lines.append(row(["---", "---", "---"]))
    for name, ok, val in rv["bottom"]:
        lines.append(row([name, "✅" if ok else "⬜", str(val)]))
    lines.append("")
    lines.append(f"### 真实逃顶信号（{rv['top_fired']}/{len(rv['top'])}）\n")
    lines.append(row(["规则", "状态", "当前值"]))
    lines.append(row(["---", "---", "---"]))
    for name, ok, val in rv["top"]:
        lines.append(row([name, "✅" if ok else "⬜", str(val)]))
    lines.append("")
    lines.append(f"**估值区带**：{rv.get('zone','N/A')}（Ahr999 口径）\n")
    ex_nf = None
    _lns = rv.get("_lns") or {}
    if _lns.get("exNetFlow2", {}).get("v") is not None:
        ex_nf = _lns["exNetFlow2"]["v"]
    if _lns.get("exBalance2", {}).get("v") is not None:
        if ex_nf is not None:
            nf_note = "（净流出交易所=吸筹迹象）" if ex_nf < 0 else "（净流入交易所=派发迹象）"
        else:
            nf_note = ""
        lines.append(f"- 交易所余额 {_lns['exBalance2']['v']:,.0f} BTC"
                     + (f"，昨日净流 {ex_nf:+,.0f} BTC" if ex_nf is not None else "")
                     + nf_note)
    if _lns.get("realizedProfitUsd", {}).get("v") is not None:
        lp = _lns["realizedProfitUsd"]["v"]; ll = _lns.get("realizedLos", {}).get("v") or 0
        lines.append(f"- 已实现盈亏：利润 ${lp/1e6:,.0f}M vs 亏损 ${ll/1e6:,.0f}M"
                     "（亏损骤增=投降盘，利润骤增=派发嫌疑）")
    lines.append("")

    lines.append("## 3. 趋势过滤\n")
    lines.append(f"- MA200 斜率(30日)：`{sc.get('ma200_slope30','N/A')}%` → "
                 f"{'趋势向上，可采纳抄底' if sc.get('trend_ok') else '趋势向下，抄底信号不采纳'}\n")

    lines.append("## 4. 数据来源与代理说明\n")
    lines.append("- **真实指标（LookNode 免费层实测）**：MVRV / MVRV Z / NUPL / Ahr999 / 已实现价格 / "
                 "利润供应% / 交易所净流&余额 / 已实现盈亏 / 资金费率&持仓量 / ETF 流 / 稳定币 / F&G / 活跃地址 / NVT")
    lines.append("- **实测可得（其他免费源）**：价格(DefiLlama)、BTC 活跃地址/算力/链上成交额(blockchain.info)、"
                 "F&G(alternative.me)、稳定币市值(llama.fi)、费率(mempool.space)")
    lines.append("- **代理近似**：仅『筹码结构/鲸鱼』维度仍用代理（URPD、LTH/STH 分群、鲸鱼群组地址数）")
    lines.append("- **付费才可得更细数据**：LookNode 付费层（URPD、LTH/STH MVRV/NUPL、Supply 盈亏）；"
                 "Glassnode（需付费 API key，env: GLASSNODE_API_KEY）")
    lines.append("- **被墙不取**：CoinGecko / 币安 / OKX / Coinbase（勿重试）\n")

    lines.append("## 5. 风险免责\n")
    lines.append("本看板为方法论与数据分析**不构成投资建议**。代理规则回测样本小（过滤后 9 信号），"
                 "真实胜率低于报告数字；抄底须趋势过滤通过且分批，逃顶须分批减仓。\n")
    lines.append("---")
    lines.append(f"\n生成时间(UTC)：{snap.get('generated_at_utc','-')}  |  脚本：gen_daily_report.py")
    return "\n".join(lines)


def md_weekly(snap, sc, v_text, v_reason, date_str, prev_snap):
    lines = [f"# 链上数据周度复盘 · {date_str}（周一）\n",
             f"> **本周倾向：{v_text}** —— {v_reason}\n",
             "## 本周 vs 上周变化\n"]
    lines.append("| 指标 | 上周 | 本周 | 变化 |")
    lines.append("| --- | --- | --- | --- |")
    if prev_snap:
        def g(sp, k, sub=None):
            if sub:
                return safe(sp.get(k, {}), sub)
            return sp.get(k)
        p_now = safe(snap.get("price", {}), "BTC", {}).get("price")
        p_prev = safe(prev_snap.get("price", {}), "BTC", {}).get("price")
        fg_now = (snap.get("fear_greed") or [{}])[0].get("value")
        fg_prev = (prev_snap.get("fear_greed") or [{}])[0].get("value")
        st_now = (snap.get("stablecoin") or {}).get("total_usd")
        st_prev = (prev_snap.get("stablecoin") or {}).get("total_usd")
        lines.append(f"| BTC 价格 | {p_prev} | {p_now} | "
                     f"{round((p_now/p_prev-1)*100,2) if p_prev else 'N/A'}% |")
        lines.append(f"| F&G | {fg_prev} | {fg_now} | {fg_now-fg_prev if fg_now and fg_prev else 'N/A'} |")
        lines.append(f"| 稳定币市值 | {st_prev} | {st_now} | "
                     f"{round((st_now/st_prev-1)*100,2) if st_prev else 'N/A'}% |")
    else:
        lines.append("| （无上周快照，首次运行） | - | - | - |")
    lines.append("")
    lines.append("## 周级监控清单（本框架）\n")
    for it in ["稳定币市值 vs CEX 买盘是否同步（背离=预警）",
               "分区域资金情绪（美/亚/欧，欧区先行）—需 Glassnode",
               "LTH/STH 日均获利差距（派发迹象）—需 Glassnode",
               "期权 Put-Call 是否倒挂（顶部特征）—需 Glassnode",
               "URPD 筹码分布结构变化 —需 Glassnode"]:
        lines.append(f"- ☐ {it}")
    lines.append("")
    lines.append("## 操作倾向\n")
    lines.append(f"- 抄底代理 {sc['bottom_fired']}/5，逃顶代理 {sc['top_fired']}/5，"
                 f"趋势过滤={'通过' if sc.get('trend_ok') else '不通过'}")
    lines.append("- 结论同上每日看板；本周重点观察上述周级清单中可观测项的变化方向。\n")
    lines.append("---\n生成时间(UTC)：" + snap.get("generated_at_utc", "-"))
    return "\n".join(lines)


# ------------------------------------------------------------- main
def main():
    os.makedirs(MON, exist_ok=True)
    date_str = (sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--date"
                else dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"))

    print("拉取快照 ...", file=sys.stderr)
    snap = fc.snapshot()
    json.dump(snap, open(os.path.join(MON, f"snapshot_{date_str}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("拉取 LookNode 真实估值指标 ...", file=sys.stderr)
    lns = {}
    try:
        lns = ln.snapshot()
        json.dump(lns, open(os.path.join(MON, f"looknode_{date_str}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] LookNode 取数失败：{e}", file=sys.stderr)

    print("评分 ...", file=sys.stderr)
    sc = score_now(snap)
    rv = real_valuation(sc.get("price"), lns)
    rv["_lns"] = lns
    v_text, v_reason = verdict(sc)

    md = md_daily(snap, sc, rv, v_text, v_reason, date_str)
    dpath = os.path.join(MON, f"daily_chain_monitor_{date_str}.md")
    open(dpath, "w", encoding="utf-8").write(md)
    print(f"[OK] 每日看板 -> {dpath}", file=sys.stderr)

    # 周一（北京时间）额外周报
    bj = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    if bj.weekday() == 0:
        prev = None
        # 找最近一个旧快照
        for f in sorted(os.listdir(MON), reverse=True):
            if f.startswith("snapshot_") and f != f"snapshot_{date_str}.json":
                try:
                    prev = json.load(open(os.path.join(MON, f), encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    prev = None
                break
        wmd = md_weekly(snap, sc, v_text, v_reason, date_str, prev)
        wpath = os.path.join(MON, f"weekly_chain_review_{date_str}.md")
        open(wpath, "w", encoding="utf-8").write(wmd)
        print(f"[OK] 周一周报 -> {wpath}", file=sys.stderr)

    print(f"\n结论：{v_text} | {v_reason}")
    print(f"抄底代理 {sc['bottom_fired']}/5  逃顶代理 {sc['top_fired']}/5  "
          f"趋势过滤={'通过' if sc.get('trend_ok') else '不通过'}")
    if lns:
        print(f"真实估值(LookNode)：MVRV={rv['vals'].get('MVRV','-')}  Z={rv['vals'].get('MVRV_Z','-')}  "
              f"NUPL={rv['vals'].get('NUPL','-')}  Ahr999={rv['vals'].get('Ahr999','-')}"
              f"  利润供应={rv['vals'].get('profit_supply','-')}")
        print(f"真实抄底 {rv['bottom_fired']}/{len(rv['bottom'])}  "
              f"真实逃顶 {rv['top_fired']}/{len(rv['top'])}  估值区带：{rv.get('zone')}")


if __name__ == "__main__":
    main()
