#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
web3trading / LookNode 取数脚本（2026-09-06 逆向实测）

LookNode（https://www.looknode.com）是中文一站式链上数据平台，
其前端 SPA 调用的 REST API **免登录即可取大部分指标**（付费层除外），
大陆网络可直连。本脚本封装 本框架所需的全部免费端点。

=====================================================================
重要实测结论（踩坑记录，勿重复踩）：
1. API 基址必须用 https://www.looknode.com/api
   bundle 里的 https://wp.looknode.com/api 证书已过期且返回占位页（wefcsdfw），不可用。
2. wp.looknode.com 的 TLS 证书过期（SEC_E_CERT_EXPIRED），
   本脚本默认跳过证书校验（公开行情数据，风险可接受）。
3. 响应统一格式：{"code":100,"message":"操作成功","data":[...]}，
   data 元素为 {t, v} 或 {t, v1..v13}（v1..v13 为分交易所/分桶字段）。
4. t 时间戳单位不统一：MVRVZ/NUPL 等 t 为毫秒；Ahr999/bFundingRateDetail 等 t 为秒。
   判断规则：t < 1e11 视为秒。
5. 交易所类端点需要 ?ex=all 等参数（否则 500 "s is null"）。
6. code=4001 "JWT parsed err" = 付费层（需登录 token），免费层自动跳过。

免费端点清单（六维框架映射）：
  估值水位: mCapRealizedRatio(真实MVRV) MVRVZ(Z值+市值/已实现市值) NUPL Ahr999
            realizePrice(已实现价格) CVDD balancedPrice historyRetracement(ATH回撤)
  筹码结构: percentInLoss(亏损供应%) holdTime(币龄分布v1..v13) getActiveAddNum newAddress
  资金情绪: fearAndGreedy stablecoinSupply btcEtfDetailFlow(ETF) bFundingRateDetail(费率)
            bOpenInterestDetail(持仓量)
  鲸鱼行为: exNetFlow2(交易所净流,需?ex=all) exBalance2(交易所余额,需?ex=all)
            realizedProfitUsd realizedLos(已实现盈亏USD) perVolumePro perVolumeLos
  网络健康: hashRate difficultyRibbon advanceNVT bdd marketHealth

付费端点（code=4001，需登录 JWT，脚本自动跳过）：
  STHMVRV LTHMVRV STHNUPL LTHNUPL URPD_ATH URPD_PER URPD_ATH_STH URPD_ATH_LTH
  lth_sopr lthPositionChange LTHSupPro LTHSupLos STHSupPro STHSupLos realizedLossUsdForT1

Glassnode 对照（需付费 API key，env: GLASSNODE_API_KEY）：
  真实 MVRV        = /v1/metrics/market/mvrv            (Advanced)
  MVRV Z-Score    = /v1/metrics/market/mvrv_z_score    (Advanced)
  NUPL            = /v1/metrics/market/nupl            (Advanced)
  Realized Price  = /v1/metrics/market/realized_price  (Advanced)
  SOPR/aSOPR      = /v1/metrics/indicators/sopr|asopr  (Advanced)
  RHODL           = /v1/metrics/indicators/rhodl_ratio (Advanced)
  URPD 等筹码分布  = Cost Basis Distribution            (Professional)
  交易所净流       = /v1/metrics/transactions/... flows (Advanced)
  认证：api_key query 参数；免费 Standard 层仅 Tier1 基础量价指标。

用法：
  python fetch_looknode.py                  # 拉全部免费指标最新值
  python fetch_looknode.py --json out.json  # 落盘 JSON
  python fetch_looknode.py --ep NUPL        # 单指标（含末 3 个数据点）
"""

import argparse
import datetime as dt
import json
import os
import ssl
import sys
import time
import urllib.request

BASE = "https://www.looknode.com/api"

# 免费端点 -> (说明, 需要的query参数)
FREE_ENDPOINTS = {
    # --- 估值水位 ---
    "mCapRealizedRatio":   ("真实 MVRV（市值/已实现市值）", ""),
    "MVRVZ":               ("MVRV Z-Score（v1=市值 v2=已实现市值 v3=Z值）", ""),
    "NUPL":                ("NUPL 未实现盈亏比", ""),
    "Ahr999":              ("Ahr999 抄底指数（<0.45 抄底区 / <1.2 定投区）", ""),
    "realizePrice":        ("已实现价格 Realized Price（USD）", ""),
    "CVDD":                ("CVDD 顶部估值", ""),
    "balancedPrice":       ("平衡价格（底部锚）", ""),
    "historyRetracement":  ("距 ATH 回撤比例", ""),
    # --- 筹码结构 ---
    "percentInLoss":       ("亏损供应百分比（利润供应%=1-v）", ""),
    "holdTime":            ("币龄分布 v1..v13", ""),
    "getActiveAddNum":     ("活跃地址数", ""),
    "newAddress":          ("新增地址数", ""),
    # --- 资金情绪 ---
    "fearAndGreedy":       ("恐惧贪婪指数", ""),
    "stablecoinSupply":    ("稳定币供应（USD）", ""),
    "btcEtfDetailFlow":    ("美国 BTC ETF 流入流出明细（分发行商 v1..v13）", ""),
    "bFundingRateDetail":  ("各交易所永续资金费率（v1..v13）", ""),
    "bOpenInterestDetail": ("各交易所合约持仓量（v1..v13）", ""),
    # --- 鲸鱼行为 ---
    "exNetFlow2":          ("交易所净流量 BTC（all=全所）", "?ex=all"),
    "exBalance2":          ("交易所余额 BTC", "?ex=all"),
    "realizedProfitUsd":   ("已实现利润（USD/日）", ""),
    "realizedLos":         ("已实现亏损（USD/日）", ""),
    "perVolumePro":        ("盈利交易量占比", ""),
    "perVolumeLos":        ("亏损交易量占比", ""),
    # --- 网络健康 ---
    "hashRate":            ("算力（TH/s，v1=当日 v2=7日均线）", ""),
    "difficultyRibbon":    ("难度丝带（v1..v3 不同周期均线）", ""),
    "advanceNVT":          ("NVT 比率", ""),
    "bdd":                 ("实际销毁天数 BDD", ""),
    "marketHealth":        ("市场健康度", ""),
}

PREMIUM_ENDPOINTS = [
    "STHMVRV", "LTHMVRV", "STHNUPL", "LTHNUPL", "URPD_ATH", "URPD_PER",
    "URPD_ATH_STH", "URPD_ATH_LTH", "lth_sopr", "lthPositionChange",
    "LTHSupPro", "LTHSupLos", "STHSupPro", "STHSupLos", "realizedLossUsdForT1",
]

# 跳过证书校验：wp 子域证书过期；www 主域正常但统一放宽以求稳
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TIMEOUT = 30


def _get(url, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX).read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 * (i + 1))
    raise last


def _ts_iso(t):
    """t 毫秒或秒（<1e11 视为秒）-> ISO 日期"""
    if t is None:
        return None
    t = float(t)
    if t < 1e11:
        t *= 1000
    return dt.datetime.fromtimestamp(t / 1000).strftime("%Y-%m-%d")


def fetch_series(ep, params="", retries=2):
    """返回 (points, err)。points 为原始 data 列表；失败返回 ([], err_str)"""
    try:
        j = json.loads(_get(f"{BASE}/{ep}{params}", retries))
    except Exception as e:  # noqa: BLE001
        return [], f"HTTP_ERR {e}"
    if j.get("code") != 100:
        return [], f"code={j.get('code')} {str(j.get('message'))[:60]}"
    d = j.get("data")
    return (d if isinstance(d, list) else []), None


def latest(points):
    """取最后一个数据点 -> {date, v, v1..v13}；空返回 None"""
    if not points:
        return None
    p = points[-1]
    out = {"date": _ts_iso(p.get("t"))}
    for k, v in p.items():
        if k != "t":
            out[k] = v
    return out


def snapshot():
    """拉全部免费指标 -> {name: {desc, date, ...values, err}}"""
    out = {"base": BASE, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    for ep, (desc, params) in FREE_ENDPOINTS.items():
        pts, err = fetch_series(ep, params)
        rec = {"desc": desc, "n": len(pts)}
        if err:
            rec["err"] = err
        else:
            last = latest(pts)
            if last:
                rec.update(last)
            # 部分指标附带历史用于变化判断（30 天前值）
            if len(pts) > 30:
                p30 = pts[-31]
                v30 = p30.get("v", p30.get("v1"))
                if isinstance(v30, (int, float)):
                    rec["v_30d_ago"] = v30
        out[ep] = rec
    return out


def fmt_val(rec):
    if "err" in rec:
        return f"N/A ({rec['err']})"
    keys = [k for k in rec if k.startswith("v") and k[1:].isdigit() or k == "v"]
    vals = {k: rec[k] for k in ("v", "v1", "v2", "v3") if k in rec and rec[k] is not None}
    if not vals:
        return "N/A"
    if "v" in vals and len(vals) == 1:
        v = vals["v"]
        return f"{v:,.2f}" if isinstance(v, float) else str(v)
    return " ".join(f"{k}={vals[k]:,.4g}" for k in sorted(vals))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="落盘 JSON 路径")
    ap.add_argument("--ep", help="仅取单个端点（打印末 3 点）")
    args = ap.parse_args()

    if args.ep:
        params = FREE_ENDPOINTS.get(args.ep, ("", ""))[1]
        pts, err = fetch_series(args.ep, params)
        if err:
            print(f"{args.ep}: {err}")
            sys.exit(1)
        print(f"{args.ep}: n={len(pts)}")
        for p in pts[-3:]:
            print(" ", _ts_iso(p.get("t")), {k: v for k, v in p.items() if k != "t"})
        return

    snap = snapshot()
    print(f"# LookNode 免费链上指标快照  base={BASE}")
    print(f"# 拉取时间(UTC): {snap['fetched_at']}\n")
    cur_cat = None
    for ep, (desc, _) in FREE_ENDPOINTS.items():
        rec = snap.get(ep, {})
        print(f"{ep:20} [{rec.get('date','-')}] {fmt_val(rec):32} # {desc}"
              + (f"  (30d前: {rec['v_30d_ago']:,.4g})" if "v_30d_ago" in rec else ""))
    errs = [e for e, r in snap.items() if isinstance(r, dict) and "err" in r]
    if errs:
        print(f"\n[失败端点] {', '.join(errs)}")
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        json.dump(snap, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[OK] JSON -> {args.json}")


if __name__ == "__main__":
    main()
