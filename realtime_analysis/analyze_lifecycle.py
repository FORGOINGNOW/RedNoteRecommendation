# -*- coding: utf-8 -*-
"""
analyze_lifecycle.py — 帖子生命周期分析：互动数 × 发布后时长

方法（横截面数据，每个笔记只有一个观测时点）：
  1. 年龄分桶：各年龄段笔记的互动水平 / 日均互动速率 / 爆款率
  2. log(年龄) ~ log(互动) 回归：生命周期增长/衰减斜率（分品类对比）
  3. 互动速率衰减曲线拟合：估计热度半衰期
  4. 品类生命周期类型：短命爆发型 / 平衡型 / 长青长尾型
  5. 速成爆款 vs 慢热长尾的占比结构

局限：
  - 样本为关键词搜索「按热度排序」的前 N 条 → 幸存者样本：能上榜的都是
    互动高且活到采样时点的笔记，早期夭折的笔记不可见
  - 横截面 ≠ 单帖追踪：速率为估计值，非真实增量曲线
"""
import re
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

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AGE_BINS = [(0, 3, "0-3天"), (3, 7, "3-7天"), (7, 30, "7-30天"),
            (30, 90, "30-90天"), (90, 365, "90天-1年"), (365, 10 ** 9, "1年以上")]


def build(df: pd.DataFrame, now_ts: int):
    df = df.copy()
    df["category"] = df.apply(classify_note, axis=1)
    df["age_days"] = (now_ts - df["publish_ts"]) / 86400e3
    df = df[df["age_days"] >= 0.01]
    df["log_age"] = np.log10(df["age_days"])
    df["log_interact"] = np.log10(df["interact"] + 1)
    df["velocity"] = df["interact"] / df["age_days"]          # 日均互动（估计速率）
    df["age_bucket"] = pd.cut(df["age_days"], bins=[b[0] for b in AGE_BINS] + [10 ** 9],
                              labels=[b[2] for b in AGE_BINS], right=False)
    return df


def ols_slope(x, y):
    X = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    r2 = 1 - float((resid ** 2).sum()) / max(float(((y - y.mean()) ** 2).sum()), 1e-12)
    return float(beta[0]), float(beta[1]), float(r2)


def age_bucket_stats(df):
    rows = []
    for lo, hi, label in AGE_BINS:
        sub = df[(df["age_days"] >= lo) & (df["age_days"] < hi)]
        if len(sub) == 0:
            continue
        rows.append({
            "年龄": label,
            "笔记数": len(sub),
            "中位互动": round(sub["interact"].median()),
            "中位日均互动": round(sub["velocity"].median()),
            "爆款率(≥1k)": round((sub["interact"] >= 1000).mean(), 3),
            "大爆款率(≥5k)": round((sub["interact"] >= 5000).mean(), 3),
        })
    return pd.DataFrame(rows)


def category_lifecycle(df):
    rows = []
    for name, sub in df.groupby("category"):
        if len(sub) < 3:
            continue
        med_age = sub["age_days"].median()
        med_vel = sub["velocity"].median()
        if med_vel >= 100 and med_age < 30:
            life_type = "短命爆发型（吃热度，速成速衰）"
        elif med_vel >= 100:
            life_type = "长红型（持续发酵，高速度长期维持）"
        elif med_vel >= 20:
            life_type = "平衡型（热度+中速长尾）"
        else:
            life_type = "长青长尾型（靠搜索持续进流量）"
        rows.append({
            "品类": name,
            "笔记数": len(sub),
            "中位年龄(天)": round(med_age),
            "中位日均互动": round(med_vel),
            "生命周期类型": life_type,
        })
    out = pd.DataFrame(rows)
    return out.sort_values("中位日均互动", ascending=False)


def make_charts(df, slope_by_cat, half_life, out_dir: Path):
    # 1) 散点：log年龄 vs log互动（分品类配色）+ 总体拟合线
    fig, ax = plt.subplots(figsize=(10, 5.6))
    for name, sub in df.groupby("category"):
        ax.scatter(sub["log_age"], sub["log_interact"], s=14, alpha=0.55,
                   color=CATEGORY_COLORS.get(name, "#666"), label=name)
    b0, b1, r2 = ols_slope(df["log_age"].values, df["log_interact"].values)
    xs = np.linspace(df["log_age"].min(), df["log_age"].max(), 50)
    ax.plot(xs, b0 + b1 * xs, color="#ff2e4d", lw=2,
            label="总体拟合 斜率=%.2f (R²=%.0f%%)" % (b1, r2 * 100))
    ax.set_xlabel("log10(发布后天数)")
    ax.set_ylabel("log10(总互动+1)")
    ax.set_title("互动 × 年龄（横截面，热排序幸存样本）")
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1))
    ax.tick_params(colors="white")
    plt.tight_layout()
    plt.savefig(out_dir / "chart_life_scatter.png", dpi=110, facecolor="#1e1e28")
    plt.close()

    # 2) 速率衰减曲线 + 半衰期
    mids, vels = [], []
    for lo, hi, label in AGE_BINS:
        sub = df[(df["age_days"] >= lo) & (df["age_days"] < hi)]
        if len(sub) < 3:
            continue
        mid = (lo + hi) / 2
        mids.append(mid)
        vels.append(sub["velocity"].median())
    mids = np.array(mids, dtype=float)
    vels = np.array(vels, dtype=float)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(mids, vels, "o-", color="#4d9fff")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("发布后天数（对数）")
    ax.set_ylabel("中位日均互动（对数）")
    ax.set_title("互动速率衰减曲线（速度=累计互动/年龄）")
    ax.tick_params(colors="white")
    ax.grid(True, color="#32323f", lw=0.5, which="both")
    if len(mids) >= 3:
        logv = np.log(vels + 1e-9)
        a, b_, r2v = ols_slope(mids, logv)
        xs = np.linspace(mids.min(), mids.max(), 50)
        ax.plot(xs, np.exp(a + b_ * xs), "--", color="#ffb84d",
                label="指数衰减拟合 半衰期≈%.1f 天" % half_life)
        ax.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "chart_life_decay.png", dpi=110, facecolor="#1e1e28")
    plt.close()

    # 3) 各品类生命周期斜率对比
    fig, ax = plt.subplots(figsize=(10, 4.8))
    names = list(slope_by_cat.keys())
    vals = [slope_by_cat[n][0] for n in names]
    colors = [CATEGORY_COLORS.get(n, "#666") for n in names]
    ypos = np.arange(len(names))
    ax.barh(ypos, vals, color=colors)
    ax.set_yticks(ypos)
    ax.set_yticklabels(names)
    ax.axvline(0, color="#666", lw=0.8)
    ax.set_xlabel("log互动~log年龄 斜率（正=越老越涨/负=新爆款速度效应主导）")
    ax.set_title("各品类生命周期斜率")
    ax.tick_params(colors="white")
    plt.tight_layout()
    plt.savefig(out_dir / "chart_life_slope.png", dpi=110, facecolor="#1e1e28")
    plt.close()


_CSS = """
body{background:#131318;color:#e8e8ee;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:24px;margin:0}
h1{color:#ff2e4d;font-size:22px} h2{color:#ffb84d;font-size:16px;margin:22px 0 8px}
section{background:#1e1e28;border:1px solid #32323f;border-radius:12px;padding:16px;margin-bottom:16px}
.tbl{width:100%;border-collapse:collapse;font-size:12px}
.tbl th,.tbl td{padding:6px 10px;border-bottom:1px solid #32323f;text-align:left}
.tbl th{color:#9a9aa8}
.summary{display:flex;flex-wrap:wrap;gap:14px;padding:12px 0}
.summary div{background:#242430;border-radius:10px;padding:10px 16px;text-align:center;min-width:120px}
.summary b{display:block;font-size:19px;color:#ff2e4d}
.summary span{font-size:11px;color:#9a9aa8}
.hint{color:#9a9aa8;font-size:11px;margin:8px 0}
"""


def build_html(df, bucket, cat_life, slope_by_cat, half_life, fast_ratio, tail_ratio, out_dir: Path):
    bucket_tbl = bucket.to_html(classes="tbl", index=False, escape=False)
    cat_tbl = cat_life.to_html(classes="tbl", index=False, escape=False)

    slope_rows = "".join(
        "<tr><td>{}</td><td>{:+.2f}</td><td>{:.0f}%</td><td>{} 篇</td></tr>".format(
            n, v[0], v[1] * 100, v[2])
        for n, v in slope_by_cat.items()
    )
    slope_tbl = ("<table class='tbl'><thead><tr><th>品类</th><th>斜率</th>"
                 "<th>R²</th><th>样本</th></tr></thead><tbody>" + slope_rows + "</tbody></table>")

    import base64
    def img(p):
        return '<img src="data:image/png;base64,{}" style="max-width:100%">'.format(
            base64.b64encode((out_dir / p).read_bytes()).decode())

    body = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>帖子生命周期分析报告</title>
<style>{css}</style></head><body>
<h1>帖子生命周期分析报告</h1>
<p class="hint">生成时间 {ts} · 横截面样本 · 互动为采样时点的累计值</p>
<div class="summary">
  <div><b>{hl:.1f} 天</b><span>热度半衰期（估算）</span></div>
  <div><b>{fr:.0f}%</b><span>7天内速成爆款占比</span></div>
  <div><b>{tr:.0f}%</b><span>90天+长青爆款占比</span></div>
</div>
<section><h2>互动 × 年龄 散点与总体拟合</h2>{img_scatter}
<p class="hint">斜率&gt;0：互动随年龄累积（长青）；斜率&lt;0：新爆款的速度效应主导（热排序下新上榜笔记互动极大）。</p></section>
<section><h2>各年龄段表现</h2>{bucket_tbl}</section>
<section><h2>互动速率衰减曲线</h2>{img_decay}
<p class="hint">半衰期≈热度（日均互动）衰减一半所需的天数。横截面估计，非单帖追踪。</p></section>
<section><h2>各品类生命周期斜率</h2>{img_slope}{slope_tbl}</section>
<section><h2>品类生命周期类型</h2>{cat_tbl}</section>
<section><h2>方法与局限</h2>
<p class="hint">
1. 横截面：每篇笔记只有一个采样时点，速率为「累计互动/年龄」估计。<br>
2. 幸存者偏差：样本取自关键词热排序前 N 条，早期夭折或互动低的笔记不可见，实际衰减会比图中更陡。<br>
3. 年龄与关键词池混杂：不同关键词采集批次不同，解释斜率时结合品类表看。<br>
4. 结论用于理解结构，不构成精确预测。
</p></section>
</body></html>""".format(
        css=_CSS,
        ts=datetime.now().strftime("%Y-%m-%d %H:%M"),
        hl=half_life if half_life != float("inf") else 999.0,
        fr=fast_ratio * 100, tr=tail_ratio * 100,
        img_scatter=img("chart_life_scatter.png"),
        img_decay=img("chart_life_decay.png"),
        img_slope=img("chart_life_slope.png"),
        bucket_tbl=bucket_tbl, slope_tbl=slope_tbl, cat_tbl=cat_tbl,
    )
    return body


def compute_metrics(df_raw, now_ts):
    """核心指标计算，供本脚本与助手 analysis_runner 复用"""
    df = build(df_raw, now_ts)
    bucket = age_bucket_stats(df)
    cat_life = category_lifecycle(df)

    slope_by_cat = {}
    for name, sub in df.groupby("category"):
        if len(sub) >= 6:
            _, slope, r2v = ols_slope(sub["log_age"].values, sub["log_interact"].values)
            slope_by_cat[name] = (slope, r2v, len(sub))
    slope_by_cat = {k: slope_by_cat[k] for k in sorted(slope_by_cat, key=lambda x: -slope_by_cat[x][0])}

    mids, vels = [], []
    for lo, hi, label in AGE_BINS:
        sub = df[(df["age_days"] >= lo) & (df["age_days"] < hi)]
        if len(sub) >= 3:
            mids.append((lo + min(hi, 730)) / 2)
            vels.append(sub["velocity"].median())
    mids, vels = np.array(mids), np.array(vels)
    half_life = float("inf")
    if len(mids) >= 3:
        logv = np.log(vels + 1e-9)
        a, b_, _ = ols_slope(mids, logv)
        if b_ < 0:
            half_life = float(np.log(2) / -b_)

    fast = df[(df["age_days"] <= 7) & (df["interact"] >= 1000)]
    tail = df[(df["age_days"] >= 90) & (df["interact"] >= 1000)]
    fast_ratio = len(fast) / max(len(df[df["age_days"] <= 7]), 1)
    tail_ratio = len(tail) / max(len(df[df["age_days"] >= 90]), 1)

    _, overall_slope, overall_r2 = ols_slope(df["log_age"].values, df["log_interact"].values)

    return {
        "df": df,
        "bucket": bucket,
        "cat_life": cat_life,
        "slope_by_cat": slope_by_cat,
        "half_life": half_life,
        "fast_ratio": fast_ratio,
        "tail_ratio": tail_ratio,
        "overall_slope": overall_slope,
        "overall_r2": overall_r2,
        "mids": mids,
        "vels": vels,
    }


def main():
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "MediaCrawler" / "data" / "xhs" / "jsonl"
    if not data_dir.exists():
        data_dir = Path("E:/数据分析/MediaCrawler/data/xhs/jsonl")
    out_dir = HERE / "report"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_notes(str(data_dir))
    now_ts = max(int(df["publish_ts"].max()), int(datetime.now().timestamp() * 1000))
    m = compute_metrics(df, now_ts)
    df, bucket, cat_life, slope_by_cat = m["df"], m["bucket"], m["cat_life"], m["slope_by_cat"]
    half_life, fast_ratio, tail_ratio = m["half_life"], m["fast_ratio"], m["tail_ratio"]

    make_charts(df, slope_by_cat, half_life, out_dir)
    html = build_html(df, bucket, cat_life, slope_by_cat, half_life, fast_ratio, tail_ratio, out_dir)
    report_path = out_dir / "report_lifecycle.html"
    report_path.write_text(html, encoding="utf-8")

    # 控制台
    print("=" * 64)
    print("帖子生命周期分析 | 样本 n=%d | 热度半衰期≈%.1f 天" % (len(df), half_life))
    print("=" * 64)
    print("年龄分桶：")
    print(bucket.to_string(index=False))
    print("-" * 64)
    print("品类生命周期类型（按中位年龄降序）：")
    print(cat_life.to_string(index=False))
    print("-" * 64)
    print("分品类 log互动~log年龄 斜率（正=长青累积 / 负=新爆款速度效应）：")
    for n, v in slope_by_cat.items():
        print("  %-12s 斜率 %+.2f  R²=%.0f%%  (n=%d)" % (n, v[0], v[1] * 100, v[2]))
    print("-" * 64)
    print("7天内速成爆款占比: %.0f%% | 90天+长青爆款占比: %.0f%%" % (fast_ratio * 100, tail_ratio * 100))
    print("HTML 报告:", report_path)


if __name__ == "__main__":
    main()
