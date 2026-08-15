# -*- coding: utf-8 -*-
"""
analyze_search_demand.py — 用户主动搜索数据分析：搜索需求 × 内容供给缺口

数据来源：MediaCrawler 采集的搜索联想词 jsonl（search_suggest_*.jsonl，随每日采集自动生成）
方法：
  1. 需求侧：联想词出现频次（按联想位次加权，第1位=用户搜索意图最强）
  2. 供给侧：该词在笔记库（标题/标签/正文）中被覆盖的笔记数
  3. 缺口 = 需求强度 / 供给规模 → 高需求低供给 = 蓝海关键词
"""
import argparse
import base64
import glob
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analyze_xhs import load_notes
from report_common import NAV_CSS, apply_nav, nav_html

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_suggests(data_dir):
    """读取全部联想词记录：[(keyword, suggestions)]"""
    rows = []
    for path in sorted(glob.glob(str(Path(data_dir) / "search_suggest_*.jsonl"))):
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                suggs = d.get("suggestions") or []
                if suggs:
                    rows.append((d.get("keyword", ""), suggs))
    return rows


def demand_stats(rows):
    """加权需求强度：联想词位次越靠前权重越高（1/位次）"""
    weight = Counter()
    raw = Counter()
    for kw, suggs in rows:
        for i, s in enumerate(suggs):
            weight[s] += 1.0 / (i + 1)
            raw[s] += 1
    return weight, raw


def supply_count(df, term):
    """供给：笔记库中标题/标签/正文命中该词的笔记数"""
    t = term.lower()
    hit = df["title"].str.lower().str.contains(t, regex=False, na=False)
    hit |= df["tags"].astype(str).str.lower().str.contains(t, regex=False, na=False)
    hit |= df["desc"].fillna("").str.lower().str.contains(t, regex=False, na=False)
    return int(hit.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_suggests(args.data_dir)
    if not rows:
        print("未找到搜索联想词数据（search_suggest_*.jsonl），请先运行含联想词采集的 MediaCrawler 版本")
        sys.exit(1)

    df = load_notes(args.data_dir)
    weight, raw = demand_stats(rows)

    # 供给计算（只对需求词计算，控制计算量）
    terms = list(weight.keys())
    supply = {}
    for t in terms:
        supply[t] = supply_count(df, t)

    demand_max = max(weight.values()) or 1
    gap_rows = []
    for t in terms:
        s = supply[t]
        d = weight[t]
        gap = d / max(s, 1)          # 供给为0时用1避免除零
        gap_rows.append({
            "搜索词": t,
            "需求强度": round(d, 2),
            "被联想次数": raw[t],
            "笔记供给": s,
            "缺口指数": round(gap, 2),
            "判断": "蓝海（供<5）" if s < 5 else ("机会（供<30）" if s < 30 else ("饱和（供≥100）" if s >= 100 else "正常")),
        })
    gap_df = pd.DataFrame(gap_rows).sort_values("需求强度", ascending=False)

    # 图1：Top 需求词
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    top = gap_df.head(20).iloc[::-1]
    axes[0].barh(top["搜索词"], top["需求强度"], color="#4d9fff")
    axes[0].set_title("用户主动搜索需求 Top20（联想词加权）")
    axes[0].tick_params(colors="white")
    axes[0].tick_params(axis="y", labelsize=8)

    # 图2：需求 vs 供给 散点（对数）
    top50 = gap_df.head(50)
    axes[1].scatter(top50["笔记供给"] + 1, top50["需求强度"] + 0.01, s=40, c="#ff2e4d", alpha=0.7)
    axes[1].set_xscale("log")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("笔记供给量（对数）")
    axes[1].set_ylabel("搜索需求强度（对数）")
    axes[1].set_title("供需散点：左上角 = 蓝海词（需求高供给少）")
    for _, r in top50.head(12).iterrows():
        axes[1].annotate(r["搜索词"], (r["笔记供给"] + 1, r["需求强度"] + 0.01),
                         fontsize=8, color="#ccc", xytext=(3, 3), textcoords="offset points")
    axes[1].tick_params(colors="white")
    axes[1].grid(True, color="#32323f", lw=0.5, which="both")
    plt.tight_layout()
    chart_path = out_dir / "chart_search_demand.png"
    plt.savefig(chart_path, dpi=110, facecolor="#1e1e28")
    plt.close()

    blue_ocean = gap_df[(gap_df["笔记供给"] < 5)].head(15)
    blue_rows = "".join(
        "<tr><td>%s</td><td>%.2f</td><td>%d</td><td>%d</td><td>%s</td></tr>"
        % (r["搜索词"], r["需求强度"], r["被联想次数"], r["笔记供给"], r["判断"])
        for _, r in blue_ocean.iterrows()
    )

    all_rows = "".join(
        "<tr><td>%s</td><td>%.2f</td><td>%d</td><td>%d</td><td>%.2f</td><td>%s</td></tr>"
        % (r["搜索词"], r["需求强度"], r["被联想次数"], r["笔记供给"], r["缺口指数"], r["判断"])
        for _, r in gap_df.head(60).iterrows()
    )

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>搜索需求分析报告</title>
<style>
body{background:#131318;color:#e8e8ee;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:24px;margin:0;max-width:1080px;margin:0 auto}
h1{color:#ff2e4d;font-size:22px;text-align:center}
h2{color:#ffb84d;font-size:16px;margin:24px 0 10px}
section{background:#1e1e28;border:1px solid #32323f;border-radius:12px;padding:16px;margin-bottom:16px}
%(nav_css)s
.tbl{width:100%%;border-collapse:collapse;font-size:12px}
.tbl th,.tbl td{padding:7px 10px;border-bottom:1px solid #32323f;text-align:left}
.tbl th{color:#9a9aa8}
.hint{color:#9a9aa8;font-size:11px;margin:8px 0}
</style></head><body>
%(nav)s
<h1>搜索需求分析报告</h1>
<p class="hint" style="text-align:center">用户主动搜索联想词 %(n_terms)d 个 · 来自 %(n_records)d 条采集记录 · 对照笔记库 %(n_notes)d 条 · 生成时间 %(ts)s</p>
<section><h2>需求与供给总览</h2><img src="data:image/png;base64,%(chart)s" style="max-width:100%%"></section>
<section><h2>蓝海关键词（高需求 × 低供给）</h2>
<table class="tbl"><thead><tr><th>搜索词</th><th>需求强度</th><th>被联想次数</th><th>笔记供给</th><th>判断</th></tr></thead><tbody>%(blue_rows)s</tbody></table>
<p class="hint">这些词用户搜得多但内容少，是最值得做的选题入口。</p></section>
<section><h2>完整供需表（按需求强度排序，前60）</h2>
<table class="tbl"><thead><tr><th>搜索词</th><th>需求强度</th><th>被联想次数</th><th>笔记供给</th><th>缺口指数</th><th>判断</th></tr></thead><tbody>%(all_rows)s</tbody></table></section>
<section><h2>方法与局限</h2>
<p class="hint">
1. 需求 = 搜索联想词位次加权（第1位联想词代表当前最热搜索意图）。<br>
2. 供给 = 笔记库标题/标签/正文命中该词的笔记数（只覆盖已采集笔记，低估真实供给）。<br>
3. 联想词随每日采集累积，时间越久越稳定；短周期数据波动大。
</p></section>
</body></html>""" % {
        "nav_css": NAV_CSS, "nav": nav_html("search"),
        "n_terms": len(gap_df), "n_records": len(rows), "n_notes": len(df),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "chart": base64.b64encode(chart_path.read_bytes()).decode(),
        "blue_rows": blue_rows, "all_rows": all_rows,
    }
    report_path = out_dir / "report_search.html"
    report_path.write_text(html, encoding="utf-8")

    print("=" * 64)
    print("搜索需求分析 | 联想词 %d 个 | 采集记录 %d 条 | 笔记库 %d 条" % (len(gap_df), len(rows), len(df)))
    print("=" * 64)
    print("蓝海关键词 Top10：")
    print(blue_ocean[["搜索词", "需求强度", "笔记供给"]].to_string(index=False))
    print("-" * 64)
    print("需求强度 Top15：")
    print(gap_df.head(15)[["搜索词", "需求强度", "被联想次数", "笔记供给"]].to_string(index=False))
    print("HTML 报告:", report_path)


if __name__ == "__main__":
    main()
