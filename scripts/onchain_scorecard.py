#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web3trading · 六维链上打分卡计算器

把 references/six-dimensions.md 的六维框架 + references/execution-playbook.md
的打分卡模板程序化：输入指标 → 输出六维小计、触发项、趋势过滤、抄底/逃顶判定、建议仓位。

纯标准库，无第三方依赖。

用法:
    python onchain_scorecard.py --demo                  # 用 2026-09-06 BTC 真实快照演示
    python onchain_scorecard.py --input metrics.json    # 跑自己的指标
    python onchain_scorecard.py --template              # 打印 metrics.json 模板

metrics.json 所有字段均为可选；缺失的项记为 N/A，不参与判定（也不误判为满足）。
布尔字段用 true/false。数值字段会自动按阈值判定，也可直接用布尔值覆盖。
"""

import argparse
import json
import sys

# ---------------------------------------------------------------- 维度定义

# 每项: (key, 中文名, 默认是否必须人工填)
DIMENSIONS = {
    "D1": {
        "name": "估值水位",
        "items": [
            ("mvrv_lt_1", "MVRV < 1.0"),
            ("mvrv_z_lt_0", "MVRV Z < 0"),
            ("nupl_lt_025", "NUPL < 0.25"),
            ("ahr999_le_045", "Ahr999 ≤ 0.45"),
            ("profit_supply_lt_50", "利润供应% < 50"),
            ("price_lt_1rp", "价格 < 1.0 RP"),
        ],
    },
    "D2": {
        "name": "筹码结构",
        "items": [
            ("urpd_down_green", "下方 URPD 绿色承接"),
            ("lth_new_high", "LTH 持仓创新高"),
            ("price_above_sth_cost", "价格站上 STH 成本"),
            ("far_end_hodl", "远端筹码惜售"),
            ("exchange_balance_down", "交易所余额下降"),
        ],
    },
    "D3": {
        "name": "主力行为",
        "items": [
            ("whale_inflow_high", "鲸鱼净流入高分位"),
            ("whale_addr_up_price_down", "价↓鲸鱼地址↑ 背离"),
            ("capitulation_released", "投降盘已释放"),
            ("etf_positive", "ETF 持续净流入"),
            ("sopr_stable", "SOPR 企稳 >1"),
        ],
    },
    "D4": {
        "name": "资金情绪",
        "items": [
            ("stablecoin_expanding", "稳定币扩张"),
            ("spot_volume_up", "现货量回升"),
            ("region_sentiment_positive", "分区域情绪转正"),
            ("fg_reasonable", "恐贪 <25 或处于合理区"),
            ("active_addr_up", "活跃地址回升"),
        ],
    },
    "D5": {
        "name": "衍生品与杠杆",
        "items": [
            ("funding_mild", "资金费率温和"),
            ("oi_not_overheated", "OI 未过热"),
            ("no_put_inversion", "无 Put-Call 倒挂"),
        ],
    },
    "D6": {
        "name": "宏观与事件",
        "items": [
            ("macro_easing", "降息/宽松定价"),
            ("bond_yield_down", "美债收益率回落"),
            ("no_event_risk", "无重大事件风险"),
        ],
    },
}

# 逃顶（派发）相关触发项 —— 与抄底项互斥，单独统计
TOP_ITEMS = [
    ("mvrv_z_gt_3", "MVRV Z > 3"),
    ("nupl_gt_075", "NUPL > 0.75 (Euphoria)"),
    ("profit_supply_gt_95", "利润供应% > 95"),
    ("lth_daily_profit_gt_1b", "LTH 30 日日均获利 > $10 亿"),
    ("realized_profit_spike", "已实现利润单日 > $10 亿"),
    ("urpd_up_red", "URPD 上方持续红色派发柱"),
    ("ltp_2y_taking_profit", "币龄 >2Y 大规模止盈"),
    ("etf_cover_distribution", "ETF 利好掩护出货（拉盘+利好同步）"),
    ("sentiment_divergence", "资金情绪与价格背离"),
    ("exchange_inflow_plus_greed", "交易所余额净流入 + NUPL 极贪婪"),
]

# 数值阈值自动判定（key -> (数值key, 比较函数, 说明)）
NUMERIC_RULES = [
    ("mvrv_lt_1", "mvrv", lambda v: v < 1.0),
    ("mvrv_z_lt_0", "mvrv_z", lambda v: v < 0),
    ("nupl_lt_025", "nupl", lambda v: v < 0.25),
    ("ahr999_le_045", "ahr999", lambda v: v <= 0.45),
    ("profit_supply_lt_50", "profit_supply_pct", lambda v: v < 50),
    ("mvrv_z_gt_3", "mvrv_z", lambda v: v > 3),
    ("nupl_gt_075", "nupl", lambda v: v > 0.75),
    ("profit_supply_gt_95", "profit_supply_pct", lambda v: v > 95),
]

DEMO_METRICS = {
    "asset": "BTC",
    "date": "2026-09-06",
    "price": 79846,
    # 趋势过滤（抄底前置条件）
    "ma200_slope_30d_pct": -1.17,
    # D1 真实估值
    "mvrv": 1.497,
    "mvrv_z": 0.893,
    "nupl": 0.332,
    "ahr999": 0.528,
    "profit_supply_pct": 70.5,
    # 人工布尔判定（D2–D6，付费/半付费指标）
    "exchange_balance_down": True,
    "capitulation_released": True,
    "etf_positive": True,
    "sopr_stable": True,
    "stablecoin_expanding": False,
    "spot_volume_up": False,
    "active_addr_up": False,
    "fg_reasonable": True,
    "funding_mild": True,
    "oi_not_overheated": True,
    "no_put_inversion": True,
    "macro_easing": False,
    "bond_yield_down": False,
    "no_event_risk": False,
    # D2 付费项不可得 → 留空即 N/A
}

TEMPLATE = {
    "asset": "BTC",
    "date": "YYYY-MM-DD",
    "price": 0,
    "ma200_slope_30d_pct": 0.0,
    "mvrv": 0.0,
    "mvrv_z": 0.0,
    "nupl": 0.0,
    "ahr999": 0.0,
    "profit_supply_pct": 0.0,
    "exchange_balance_down": False,
    "capitulation_released": False,
    "etf_positive": False,
    "sopr_stable": False,
    "stablecoin_expanding": False,
    "spot_volume_up": False,
    "active_addr_up": False,
    "fg_reasonable": False,
    "funding_mild": False,
    "oi_not_overheated": False,
    "no_put_inversion": False,
    "macro_easing": False,
    "bond_yield_down": False,
    "no_event_risk": False,
}


# ---------------------------------------------------------------- 计算逻辑

def resolve_item(key, m):
    """返回 (state, note)：state ∈ True/False/None(N/A)"""
    if key in m and isinstance(m[key], bool):
        return m[key], "人工判定"
    for bkey, numkey, fn in NUMERIC_RULES:
        if bkey == key and numkey in m and isinstance(m[numkey], (int, float)):
            return fn(m[numkey]), f"{numkey}={m[numkey]}"
    return None, "N/A"


def evaluate(m):
    dim_scores, dim_detail = {}, {}
    total_trigger = 0
    for code, dim in DIMENSIONS.items():
        hit, rows = 0, []
        for key, label in dim["items"]:
            state, note = resolve_item(key, m)
            rows.append((label, state, note))
            if state is True:
                hit += 1
        dim_scores[code] = hit
        dim_detail[code] = (dim["name"], hit, len(dim["items"]), rows)
        total_trigger += hit

    # 逃顶触发
    top_hits = []
    for key, label in TOP_ITEMS:
        state, note = resolve_item(key, m)
        if state is True:
            top_hits.append((label, note))

    # 趋势过滤
    slope = m.get("ma200_slope_30d_pct")
    trend_ok = None if slope is None else (slope > 0)

    return dim_scores, dim_detail, total_trigger, top_hits, trend_ok, slope


def dca_zone(m):
    """按 Ahr999 判定屯币区间：抄底区 / 定投区 / 观望区。返回 (状态, 说明)"""
    a = m.get("ahr999")
    if not isinstance(a, (int, float)):
        return None, "Ahr999 N/A"
    if a <= 0.45:
        return "抄底区", f"Ahr999={a} ≤ 0.45"
    if a <= 1.2:
        return "定投区", f"Ahr999={a} 处于 0.45–1.2"
    return "观望区", f"Ahr999={a} > 1.2"


def build_verdict(m, dim_scores, total_trigger, top_hits, trend_ok):
    d1 = dim_scores.get("D1", 0)
    lines = []
    zone, zone_note = dca_zone(m)

    # ---- 抄底判定
    if trend_ok is True:
        if d1 >= 2 and total_trigger >= 3:
            pos = min(20 * total_trigger, 100)
            lines.append(f"【抄底】趋势过滤通过 + D1={d1}(≥2) + 总触发={total_trigger}(≥3)")
            lines.append(f"        → 建议建仓 {pos}%，分 3 批，每批间隔 ≥1 周，留 20% 现金应对二次探底")
        else:
            miss = []
            if d1 < 2:
                miss.append(f"D1 估值仅 {d1}/6（需 ≥2）")
            if total_trigger < 3:
                miss.append(f"总触发仅 {total_trigger}（需 ≥3）")
            lines.append("【抄底】趋势过滤通过，但 " + "；".join(miss))
            lines.append("        → 不动手，继续观察（不满 3 项坚决不动）")
    elif trend_ok is False:
        lines.append("【抄底】❌ 趋势过滤不通过（MA200 斜率 ≤ 0）→ 不采纳任何抄底信号")
        if zone == "定投区":
            lines.append(f"        → 已进入{zone}（{zone_note}）：允许小额定投 10–30%，禁止趋势加仓")
        elif zone == "抄底区":
            lines.append(f"        → 已进{zone}（{zone_note}），但趋势未确认：仅小额定投，等 MA200 斜率翻正再谈建仓")
        elif zone == "观望区":
            lines.append(f"        → {zone}（{zone_note}）且趋势向下：不建仓，等待")
        else:
            lines.append("        → 仅允许定投区小额定投，禁止趋势加仓")
    else:
        lines.append("【抄底】⚠️ 缺 MA200 斜率数据，趋势过滤无法判定（不默认通过）")

    # ---- 逃顶判定
    if top_hits:
        n = len(top_hits)
        if n >= 3:
            stage = {3: "第一批减 25%", 4: "第二批再减 25% (累计 50%)", 5: "第三批再减 25% (累计 75%)"}
            action = stage.get(n, "已触发 5 项以上：累计减至 75%，永远保留 25% 底仓")
            lines.append(f"【逃顶】触发 {n} 项（≥3）→ {action}")
        else:
            lines.append(f"【逃顶】触发 {n} 项（<3）→ 不启动减仓，继续观察")
        for label, note in top_hits:
            lines.append(f"        · {label}  ({note})")
    else:
        lines.append("【逃顶】0 项触发 → 无减仓信号")

    return lines


def render(m, dim_detail, dim_scores, total_trigger, trend_ok, slope, verdict):
    out = []
    out.append("=" * 68)
    out.append(f"  链上数据六维打分卡 · {m.get('asset','?')} · {m.get('date','?')}")
    price = m.get("price")
    if price:
        out.append(f"  价格：${price:,}")
    out.append("=" * 68)

    out.append("")
    out.append("【趋势过滤】(抄底前置条件)")
    if slope is None:
        out.append("  MA200 30 日斜率：N/A  → 无法判定")
    else:
        flag = "✅ 通过" if trend_ok else "❌ 不通过"
        out.append(f"  MA200 30 日斜率：{slope:+.2f}%   → {flag}")

    zone, zone_note = dca_zone(m)
    if zone:
        out.append(f"  Ahr999 屯币区间：{zone}  ({zone_note})")

    out.append("")
    out.append("【六维打分】")
    for code in ["D1", "D2", "D3", "D4", "D5", "D6"]:
        name, hit, total, rows = dim_detail[code]
        out.append(f"  {code} {name}：{hit}/{total}")
        for label, state, note in rows:
            if state is True:
                mark = "✅"
            elif state is False:
                mark = "· "
            else:
                mark = "N/A"
            tail = f"  [{note}]" if note not in ("人工判定", "N/A") else ""
            out.append(f"      {mark} {label}{tail}")
    out.append(f"  —— 总触发项：{total_trigger}")

    out.append("")
    out.append("【判定】")
    for line in verdict:
        out.append("  " + line)

    out.append("")
    out.append("-" * 68)
    out.append("  铁律：L1 单独不成立，必须与 L2 共振；L3 不通过时只能小额定投。")
    out.append("  回测：加 MA200 趋势过滤后，抄底 90 天胜率 56% → 78%。")
    out.append("  免责：方法论与数据整理，不构成投资建议。样本小、存在幸存者偏差。")
    out.append("-" * 68)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="web3trading 六维链上打分卡计算器")
    ap.add_argument("--demo", action="store_true", help="用 2026-09-06 BTC 快照演示")
    ap.add_argument("--input", help="指标 JSON 文件路径")
    ap.add_argument("--template", action="store_true", help="打印 metrics.json 模板")
    args = ap.parse_args()

    if args.template:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return 0

    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                m = json.load(f)
        except Exception as e:
            print(f"[错误] 读取 {args.input} 失败：{e}", file=sys.stderr)
            return 1
    elif args.demo:
        m = DEMO_METRICS
    else:
        ap.print_help()
        return 1

    dim_scores, dim_detail, total_trigger, top_hits, trend_ok, slope = evaluate(m)
    verdict = build_verdict(m, dim_scores, total_trigger, top_hits, trend_ok)
    print(render(m, dim_detail, dim_scores, total_trigger, trend_ok, slope, verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
