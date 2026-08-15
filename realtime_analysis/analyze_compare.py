# -*- coding: utf-8 -*-
"""
analyze_compare.py — 选题对比分析：我的选题 vs 总体 vs 随机抽样子集

回答「小红书整体用户行为是否趋于一致」：
  1. 你的选题子集 与 全体样本 的指标对比
  2. Bootstrap：随机抽取与你子集等量的样本 500 次，形成指标分布
  3. 你的指标落在分布中的百分位（z 值）→ 显著偏离 or 与整体一致
  4. 多维一致性指数：你的子集特征向量距离 是否落在随机样本距离的正常区间内

用法：
  python analyze_compare.py --data-dir <jsonl目录> --my-keywords "英文学习,AI" --out-dir <报告目录>
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analyze_xhs import CATEGORY_COLORS, classify_note, load_notes
from report_common import apply_nav, nav_html, NAV_CSS

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

METRIC_LABELS = {
    "median_interact": "中位互动",
    "boom_rate": "爆款率(≥1k)",
    "collect_like": "收藏赞比(中位)",
    "median_age": "中位年龄(天)",
    "median_velocity": "中位日均互动",
    "video_share": "视频占比",
}


def metrics_of(sub):
    if len(sub) == 0:
        return None
    age = sub["age_days"].values
    vel = sub["interact"].values / np.maximum(age, 0.01)
    return {
        "median_interact": float(np.median(sub["interact"])),
        "boom_rate": float((sub["interact"] >= 1000).mean()),
        "collect_like": float(sub["collect_like"].median()) if sub["collect_like"].notna().any() else 0.0,
        "median_age": float(np.median(age)),
        "median_velocity": float(np.median(vel)),
        "video_share": float((sub["type"] == "视频").mean()),
    }


def bootstrap_metrics(df, n, k, seed=42):
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(k):
        idx = rng.integers(0, len(df), size=n)
        samples.append(metrics_of(df.iloc[idx]))
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--my-keywords", default="英文学习,AI")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_notes(args.data_dir)
    now_ts = max(int(df["publish_ts"].max()), int(datetime.now().timestamp() * 1000))
    df["category"] = df.apply(classify_note, axis=1)
    df["age_days"] = (now_ts - df["publish_ts"]) / 86400e3
    df = df[df["age_days"] >= 0.01]

    my_kws = [k.strip() for k in args.my_keywords.split(",") if k.strip()]
    mine = df[df["keyword"].isin(my_kws)]
    other = df[~df["keyword"].isin(my_kws)]
    if len(mine) < 5:
        print("我的选题样本不足（%d 条），请检查 --my-keywords 或先采集数据" % len(mine))
        sys.exit(1)

    overall = metrics_of(df)
    mine_m = metrics_of(mine)
    boot = bootstrap_metrics(df, len(mine), 500)

    # 单指标 z 值与百分位
    rows = []
    for key, label in METRIC_LABELS.items():
        vals = np.array([b[key] for b in boot])
        mean, std = vals.mean(), vals.std() + 1e-12
        z = (mine_m[key] - mean) / std
        pct = float((vals <= mine_m[key]).mean())
        sig = "显著偏高" if pct >= 0.975 else ("显著偏低" if pct <= 0.025 else "与整体一致")
        rows.append({
            "指标": label,
            "我的选题": round(mine_m[key], 1),
            "全体样本": round(overall[key], 1),
            "随机样本均值±σ": "%.1f ± %.1f" % (mean, std),
            "z值": round(z, 2),
            "百分位": "%.0f%%" % (pct * 100),
            "判断": sig,
        })
    table = pd.DataFrame(rows)

    # 多维一致性：z 向量欧氏距离
    keys = list(METRIC_LABELS.keys())
    z_all = {}
    for key in keys:
        vals = np.array([b[key] for b in boot])
        z_all[key] = (mine_m[key] - vals.mean()) / (vals.std() + 1e-12)
    my_dist = float(np.linalg.norm(np.array([z_all[k] for k in keys])))

    boot_dists = []
    for b in boot:
        zv = np.array([(b[k] - np.array([x[k] for x in boot]).mean())
                       / (np.array([x[k] for x in boot]).std() + 1e-12) for k in keys])
        boot_dists.append(float(np.linalg.norm(zv)))
    consistency_pct = float((np.array(boot_dists) <= my_dist).mean())

    if consistency_pct >= 0.975:
        verdict = "显著偏离整体：你的赛道有独特的行为模式（机会或陷阱并存，值得深挖原因）"
    elif consistency_pct >= 0.05:
        verdict = "与平台整体用户行为一致：你的赛道没有特殊待遇，按通用规律运营即可"
    else:
        verdict = "比随机样本更接近整体：你的赛道是平台的典型结构，规律最适用"

    # 品类结构对比
    mine_cat = mine["category"].value_counts(normalize=True)
    all_cat = df["category"].value_counts(normalize=True)
    cat_rows = ""
    for cat in all_cat.index[:8]:
        m = mine_cat.get(cat, 0.0)
        a = all_cat.get(cat, 0.0)
        diff = m - a
        cat_rows += ("<tr><td>%s</td><td>%.0f%%</td><td>%.0f%%</td><td>%+.0f%%</td></tr>"
                     % (cat, m * 100, a * 100, diff * 100))

    # 图1：中位互动 bootstrap 分布 + 我的位置
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    vals = [b["median_interact"] for b in boot]
    axes[0].hist(vals, bins=35, color="#4d9fff", alpha=0.8)
    axes[0].axvline(mine_m["median_interact"], color="#ff2e4d", lw=2.5,
                    label="我的选题 %s" % f'{mine_m["median_interact"]:,.0f}')
    axes[0].axvline(overall["median_interact"], color="#ffb84d", lw=2, ls="--",
                    label="全体 %s" % f'{overall["median_interact"]:,.0f}')
    axes[0].set_title("中位互动：随机抽样分布 vs 我的选题")
    axes[0].legend(fontsize=9)
    axes[0].tick_params(colors="white")

    # 图2：z 值雷达式条形（多指标偏离）
    zl = [z_all[k] for k in keys]
    colors = ["#5ad1a1" if abs(z) < 2 else "#ff2e4d" for z in zl]
    axes[1].barh([METRIC_LABELS[k] for k in keys], zl, color=colors)
    axes[1].axvline(0, color="#666", lw=0.8)
    axes[1].axvline(2, color="#4dd16f", ls="--", lw=0.8)
    axes[1].axvline(-2, color="#4dd16f", ls="--", lw=0.8)
    axes[1].set_title("各指标 z 值（虚线外=显著偏离）")
    axes[1].tick_params(colors="white")
    plt.tight_layout()
    chart_path = out_dir / "chart_compare.png"
    plt.savefig(chart_path, dpi=110, facecolor="#1e1e28")
    plt.close()

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>选题对比分析报告</title>
<style>
body{background:#131318;color:#e8e8ee;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:24px;margin:0;max-width:1080px;margin:0 auto}
h1{color:#ff2e4d;font-size:22px;text-align:center}
h2{color:#ffb84d;font-size:16px;margin:24px 0 10px}
section{background:#1e1e28;border:1px solid #32323f;border-radius:12px;padding:16px;margin-bottom:16px}
%(nav_css)s
.tbl{width:100%%;border-collapse:collapse;font-size:12px}
.tbl th,.tbl td{padding:7px 10px;border-bottom:1px solid #32323f;text-align:left}
.tbl th{color:#9a9aa8}
.verdict{background:rgba(77,209,111,.07);border:1px solid #4dd16f;border-radius:10px;padding:14px 18px;margin:14px 0;font-size:14px}
.hint{color:#9a9aa8;font-size:11px;margin:8px 0}
.summary{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin:12px 0}
.m-card{background:#242430;border-radius:10px;padding:10px 16px;text-align:center;min-width:130px}
.m-card b{display:block;font-size:11px;color:#9a9aa8;font-weight:400}
.m-card span{font-size:16px;color:#ff2e4d;font-weight:700}
</style></head><body>
%(nav)s
<h1>选题对比分析报告</h1>
<p class="hint" style="text-align:center">我的选题：%(my_kws)s（%(n_mine)d 条） · 对照全体 %(n_all)d 条 · 随机抽样 500 次 · 生成时间 %(ts)s</p>
<div class="verdict"><b>结论：</b>%(verdict)s（一致性指数：落在随机样本正常区间内的概率 %(pct).0f%%）</div>
<div class="summary">
  <div class="m-card"><b>我的·中位互动</b><span>%(my_med)s</span></div>
  <div class="m-card"><b>全体·中位互动</b><span>%(all_med)s</span></div>
  <div class="m-card"><b>我的·爆款率</b><span>%(my_boom).0f%%</span></div>
  <div class="m-card"><b>我的·收藏赞比</b><span>%(my_cl).2f</span></div>
</div>
<section><h2>逐项指标对比（Bootstrap 500 次）</h2>%(table)s
<p class="hint">百分位&gt;97.5%% = 显著偏高，&lt;2.5%% = 显著偏低，中间 = 与整体一致</p></section>
<section><h2>偏离可视化</h2><img src="data:image/png;base64,%(chart)s" style="max-width:100%%"></section>
<section><h2>品类结构：我的选题 vs 全体</h2>
<table class="tbl"><thead><tr><th>品类</th><th>我的选题</th><th>全体</th><th>差异</th></tr></thead><tbody>%(cat_rows)s</tbody></table></section>
<section><h2>方法与局限</h2>
<p class="hint">
1. 随机抽样为有放回 Bootstrap（同规模 500 次），分布即「如果平台行为随机一致」的基准。<br>
2. 热排序幸存者样本：全体样本本身已是胜出者，对比的是「胜出者内部结构」。<br>
3. z&gt;2 才算显著；样本小时波动大，结论仅供参考。
</p></section>
</body></html>""" % {
        "nav_css": NAV_CSS, "nav": nav_html("compare"),
        "my_kws": args.my_keywords, "n_mine": len(mine), "n_all": len(df),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "verdict": verdict, "pct": consistency_pct * 100,
        "my_med": f'{mine_m["median_interact"]:,.0f}', "all_med": f'{overall["median_interact"]:,.0f}',
        "my_boom": mine_m["boom_rate"] * 100, "my_cl": mine_m["collect_like"],
        "table": table.to_html(classes="tbl", index=False, escape=False),
        "chart": __import__("base64").b64encode(chart_path.read_bytes()).decode(),
        "cat_rows": cat_rows,
    }

    report_path = out_dir / "report_compare.html"
    report_path.write_text(html, encoding="utf-8")

    print("=" * 64)
    print("选题对比分析 | 我的选题 n=%d | 全体 n=%d | 一致性指数=%.0f%%" % (len(mine), len(df), consistency_pct * 100))
    print("=" * 64)
    print(table.to_string(index=False))
    print("-" * 64)
    print("结论:", verdict)
    print("HTML 报告:", report_path)


if __name__ == "__main__":
    main()
