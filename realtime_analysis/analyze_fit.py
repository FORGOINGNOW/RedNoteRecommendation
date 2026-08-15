# -*- coding: utf-8 -*-
"""
analyze_fit.py — 算法契合度分析：玩法（标题/标签/时段）vs 内容干货 vs 其他，谁决定真实互动？

方法：
  1. 对每条真实笔记提取三组特征：
     - 算法玩法层：标题分/情绪词/标题长度/标签数/图数/视频/高峰时段/周末（算法精排能直接看到的信息）
     - 内容干货层：正文长度/数字密度/干货词数（内容实质的代理指标）
     - 账号与品类层：作者出镜次数（账号权重代理）/ 内容品类
  2. 结果变量：log10(总互动+1)（累计值，用笔记年龄控制时效混杂）
  3. OLS 回归 + 分组增量 R²：哪组特征解释力更强 = 什么更重要
  4. 互动分桶（对应流量池）特征画像对比
  5. 全自动输出 HTML 报告 + 控制台结论

局限（报告中也会说明）：
  - 样本来自关键词搜索按热度排序的前 N 条 → 幸存者偏差，只能对比"胜出者内部差异"
  - 互动为累计值，年龄虽被控制，但推荐放大的随机性会使 R² 存在天花板
  - 相关不等于因果
"""
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analyze_xhs import CATEGORY_COLORS, classify_note, load_notes

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 标题分启发式（与推荐算法引擎 algorithms.py 同源）
def title_score(t):
    if not t:
        return 0.0
    s = 0.25
    if 8 <= len(t) <= 26:
        s += 0.15
    if re.search(r"\d", t):
        s += 0.15
    if re.search(r"公式|教程|攻略|清单|避坑|合集|测评|干货|模板", t):
        s += 0.2
    if re.search(r"救命|绝了|宝藏|天花板|平替|后悔|亲测|避雷|翻倍", t):
        s += 0.1
    if re.search(r"[！!？?]", t):
        s += 0.05
    return max(0.0, min(1.0, s))


EMO_WORDS = re.compile(r"救命|绝了|宝藏|天花板|平替|后悔|亲测|避雷|翻倍|震惊|离谱|没想到|超|巨|无敌|最强")
DRY_WORDS = re.compile(r"公式|教程|攻略|清单|避坑|合集|测评|干货|模板|方法|步骤|建议|总结|盘点|整理|指南")


def build_features(df: pd.DataFrame, now_ts: int):
    df = df.copy()
    df["category"] = df.apply(classify_note, axis=1)
    df["image_count"] = df["images"]
    df["age_days"] = (now_ts - df["publish_ts"]) / 86400e3
    df["title_score"] = df["title"].apply(title_score)
    df["title_emo"] = df["title"].apply(lambda t: len(EMO_WORDS.findall(t or "")))
    df["title_len"] = df["title"].str.len()
    df["tag_count"] = df["tags"].apply(lambda t: len(t.split(",")) if isinstance(t, str) and t else 0)
    df["is_video"] = (df["type"] == "视频").astype(int)
    df["is_peak"] = df["hour"].apply(lambda h: 1 if (11 <= h <= 13) or (17 <= h <= 22) else 0)
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)
    desc = df["desc"].fillna("")
    df["desc_len"] = np.log10(desc.str.len() + 1)
    digits = desc.str.count(r"\d")
    df["digit_density"] = digits / (desc.str.len() + 1)
    df["dry_count"] = desc.apply(lambda t: len(DRY_WORDS.findall(t or "")))
    author_cnt = df["nickname"].value_counts()
    df["author_repeat"] = np.log1p(df["nickname"].map(author_cnt) - 1)
    df["log_interact"] = np.log10(df["interact"] + 1)
    df["collect_like"] = df["collected"] / df["liked"].replace(0, np.nan)
    return df


FEATURE_GROUPS = {
    "时效控制": ["age_days"],
    "算法玩法": ["title_score", "title_emo", "title_len", "tag_count", "image_count",
                 "is_video", "is_peak", "is_weekend"],
    "内容干货": ["desc_len", "digit_density", "dry_count"],
    "账号": ["author_repeat"],
}


def ols(df, feats, y="log_interact"):
    """OLS：非哑变量特征做 z-score 标准化（β 可横向比较），lstsq 稳健求解"""
    cols = []
    for f in feats:
        v = df[f].values.astype(float)
        if f.startswith("cat_"):
            cols.append(v)
        else:
            std = v.std()
            if std < 1e-12:
                cols.append(np.zeros_like(v))  # 常量特征（如作者全不重复）
            else:
                cols.append((v - v.mean()) / std)
    X = np.column_stack([np.ones(len(df))] + cols)
    yv = df[y].values.astype(float)
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    yhat = X @ beta
    ss_res = float(((yv - yhat) ** 2).sum())
    ss_tot = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return r2, beta


def zscore(df, cols):
    out = {}
    for c in cols:
        v = df[c].values.astype(float)
        out[c] = (v - v.mean()) / (v.std() + 1e-12)
    return out


def incremental_r2(df):
    """全模型 R² 与各特征组增量解释力"""
    base = FEATURE_GROUPS["时效控制"]
    cat_dummies = [c for c in df.columns if c.startswith("cat_")]
    mech = FEATURE_GROUPS["算法玩法"]
    content = FEATURE_GROUPS["内容干货"]
    acct = FEATURE_GROUPS["账号"]

    all_feats = base + mech + content + acct + cat_dummies
    r2_full, beta_full = ols(df, all_feats)

    results = {}
    results["时效控制(单独)"] = ols(df, base)[0]
    results["算法玩法(单独)"] = ols(df, base + mech)[0] - results["时效控制(单独)"]
    results["内容干货(单独)"] = ols(df, base + content)[0] - results["时效控制(单独)"]
    results["账号(单独)"] = ols(df, base + acct)[0] - results["时效控制(单独)"]
    results["品类(单独)"] = ols(df, base + cat_dummies)[0] - results["时效控制(单独)"]

    # 逐个剔除组看损失
    for name, feats in [("算法玩法", mech), ("内容干货", content), ("账号", acct), ("品类", cat_dummies)]:
        rest = [f for f in all_feats if f not in feats]
        results["剔除" + name + "损失"] = r2_full - ols(df, rest)[0]

    coefs = pd.Series(beta_full[1:], index=all_feats)
    return r2_full, results, coefs


def pool_bucket(v):
    if v < 1000:
        return "初始池 <1k"
    if v < 5000:
        return "二三级池 1k~5k"
    if v < 50000:
        return "四五级池 5k~50k"
    return "爆发池 >50k"


def bucket_analysis(df):
    df = df.copy()
    df["pool"] = df["interact"].apply(pool_bucket)
    feats = ["title_score", "title_emo", "title_len", "tag_count", "image_count", "is_video",
             "is_peak", "is_weekend", "desc_len", "digit_density", "dry_count",
             "author_repeat", "collect_like"]
    g = df.groupby("pool")[feats].mean()
    order = ["初始池 <1k", "二三级池 1k~5k", "四五级池 5k~50k", "爆发池 >50k"]
    g = g.reindex([o for o in order if o in g.index])
    return g


def build_html(df, r2_full, inc, coefs, bucket, out_dir: Path):
    inc_df = pd.DataFrame([inc]).T.rename(columns={0: "R² 贡献"})
    inc_df = inc_df.sort_values("R² 贡献", ascending=False)

    coef_abs = coefs.abs().sort_values(ascending=False)
    coef_table = pd.DataFrame({
        "特征": coef_abs.index,
        "标准化系数(β)": [f"{coefs[c]:+.3f}" for c in coef_abs.index],
    })

    corr_rows = []
    for c in ["title_score", "title_emo", "title_len", "tag_count", "image_count", "is_video",
              "is_peak", "is_weekend", "desc_len", "digit_density", "dry_count",
              "author_repeat", "age_days"]:
        corr = df[c].corr(df["log_interact"])
        corr_rows.append({"特征": c, "与log互动相关系数": f"{corr:+.3f}"})
    corr_df = pd.DataFrame(corr_rows)

    bucket_tbl = bucket.round(3).to_html(classes="tbl", escape=False)

    n = len(df)
    top_mech = inc.get("算法玩法(单独)", 0)
    top_content = inc.get("内容干货(单独)", 0)
    verdict = ("玩法层(标题/标签/时段)解释力更强 → 精排模型可见信息对流量影响更大"
               if top_mech > top_content else
               "内容干货层解释力更强 → 内容实质比表面玩法更重要")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>算法契合度分析报告</title>
<style>
body{{background:#131318;color:#e8e8ee;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:24px;margin:0}}
h1{{color:#ff2e4d;font-size:22px}} h2{{color:#ffb84d;font-size:16px;margin:22px 0 8px}}
section{{background:#1e1e28;border:1px solid #32323f;border-radius:12px;padding:16px;margin-bottom:16px}}
.tbl{{width:100%;border-collapse:collapse;font-size:12px}}
.tbl th,.tbl td{{padding:6px 10px;border-bottom:1px solid #32323f;text-align:left}}
.tbl th{{color:#9a9aa8}}
.summary{{display:flex;flex-wrap:wrap;gap:14px;padding:16px}}
.summary div{{background:#242430;border-radius:10px;padding:12px 18px;text-align:center;min-width:110px}}
.summary b{{display:block;font-size:20px;color:#ff2e4d}}
.summary span{{font-size:11px;color:#9a9aa8}}
.verdict{{background:rgba(77,209,111,.08);border:1px solid #4dd16f;border-radius:10px;padding:12px 16px;margin:12px 0}}
.hint{{color:#9a9aa8;font-size:11px;margin:8px 0}}
</style></head><body>
<h1>算法契合度分析报告：玩法 vs 内容 vs 其他</h1>
<p class="hint">生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 样本 {n} 条真实笔记 · 结果变量 log10(总互动+1)</p>
<div class="verdict"><b>初步结论：</b>{verdict}（详见下方分组解释力，注意幸存者偏差等局限）</div>
<div class="summary">
  <div><b>{r2_full:.2%}</b><span>全模型解释力 R²</span></div>
  <div><b>{top_mech:.2%}</b><span>算法玩法层贡献</span></div>
  <div><b>{top_content:.2%}</b><span>内容干货层贡献</span></div>
  <div><b>{inc.get('品类(单独)',0):.2%}</b><span>品类(选题)贡献</span></div>
  <div><b>{inc.get('账号(单独)',0):.2%}</b><span>账号贡献</span></div>
  <div><b>{inc.get('时效控制(单独)',0):.2%}</b><span>笔记年龄贡献</span></div>
</div>
<section><h2>各因素解释力对比</h2>{img_html(out_dir/'chart_inc.png')}{inc_df.to_html(classes='tbl', escape=False)}</section>
<section><h2>全模型标准化系数（对 log 互动的影响方向与大小）</h2>{img_html(out_dir/'chart_coef.png')}{coef_table.to_html(classes='tbl', escape=False, index=False)}
<p class="hint">β>0：该特征增加时互动更高；β<0 反之。系数已标准化，可横向比较重要性。</p></section>
<section><h2>单特征相关性</h2>{corr_df.to_html(classes='tbl', escape=False, index=False)}</section>
<section><h2>互动分桶画像（对应流量池）</h2>{img_html(out_dir/'chart_bucket.png')}{bucket_tbl}
<p class="hint">分桶均值：初始池<1k / 二三级池1k~5k / 四五级池5k~50k / 爆发池>50k。看哪类特征随层级单调变化。</p></section>
<section><h2>方法与局限</h2>
<p class="hint">
1. 样本来自关键词搜索「按热度排序」的前 N 条 → <b>幸存者偏差</b>：只能对比胜出者内部差异，无法观察失败笔记，可能低估玩法层的生死作用。<br>
2. 互动为累计值，年龄已作为控制变量进入所有模型。<br>
3. 推荐放大本身带随机性，同一质量笔记互动方差很大，R² 存在天然天花板。<br>
4. 收藏赞比等结果派生指标未进入回归，仅在分桶画像中展示。<br>
5. 相关 ≠ 因果；标题/时段可能只是「好笔记」的伴生特征。
</p></section>
</body></html>"""


def img_html(path: Path):
    if not path.exists():
        return "<p>图表缺失</p>"
    import base64
    return f'<img src="data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}" style="max-width:100%">'


def make_charts(df, inc, coefs, bucket, out_dir: Path):
    # 1. 解释力对比
    items = {k: v for k, v in inc.items() if not k.startswith("剔除")}
    fig, ax = plt.subplots(figsize=(9, 4))
    names = list(items.keys())
    vals = [items[k] for k in names]
    colors = ["#666", "#4d9fff", "#5ad1a1", "#ffb84d", "#c085ff", "#4dd0e1"][:len(names)]
    ax.barh(names, vals, color=colors)
    for i, v in enumerate(vals):
        ax.text(v + 0.001, i, f"{v:.1%}", va="center", color="#ccc", fontsize=9)
    ax.set_xlabel("R² 增量贡献")
    ax.set_title("各因素组对真实互动的解释力（R² 增量）")
    ax.tick_params(colors="white")
    plt.tight_layout()
    plt.savefig(out_dir / "chart_inc.png", dpi=110, facecolor="#1e1e28")
    plt.close()

    # 2. 系数
    coefs = coefs.abs().sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    bar_colors = ["#4d9fff" if c in FEATURE_GROUPS["算法玩法"] else
                  ("#5ad1a1" if c in FEATURE_GROUPS["内容干货"] else
                   ("#ffb84d" if c.startswith("cat_") else "#666")) for c in coefs.index]
    ax.barh(coefs.index, coefs.values, color=bar_colors)
    ax.set_title("全模型标准化系数绝对值（蓝=玩法 绿=内容 橙=品类）")
    ax.tick_params(colors="white")
    plt.tight_layout()
    plt.savefig(out_dir / "chart_coef.png", dpi=110, facecolor="#1e1e28")
    plt.close()

    # 3. 分桶画像
    feats = bucket.columns.tolist()
    z = bucket.copy()
    for c in feats:
        z[c] = (bucket[c] - bucket[c].mean()) / (bucket[c].std() + 1e-12)
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    x = np.arange(len(feats))
    width = 0.2
    for i, pool in enumerate(z.index):
        ax.bar(x + (i - 1.5) * width, z.loc[pool].values, width, label=pool)
    ax.set_xticks(x)
    ax.set_xticklabels(feats, rotation=35, ha="right", fontsize=9)
    ax.legend(fontsize=9)
    ax.axhline(0, color="#666", lw=0.8)
    ax.set_title("各流量池层级笔记的特征画像（z-score 标准化）")
    ax.tick_params(colors="white")
    plt.tight_layout()
    plt.savefig(out_dir / "chart_bucket.png", dpi=110, facecolor="#1e1e28")
    plt.close()


def main():
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "MediaCrawler" / "data" / "xhs" / "jsonl"
    if not data_dir.exists():
        data_dir = Path("E:/数据分析/MediaCrawler/data/xhs/jsonl")
    out_dir = HERE / "report"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_notes(str(data_dir))
    now_ts = max(df["publish_ts"].max(), int(datetime.now().timestamp() * 1000))
    df = build_features(df, now_ts)

    # 品类哑变量
    cats = pd.get_dummies(df["category"], prefix="cat").astype(int)
    df = pd.concat([df, cats], axis=1)

    r2_full, inc, coefs = incremental_r2(df)
    bucket = bucket_analysis(df)

    print("=" * 64)
    print(f"算法契合度分析 | 样本 n={len(df)} | 全模型 R² = {r2_full:.1%}")
    print("=" * 64)
    print("各因素解释力（R² 增量）:")
    for k, v in sorted(inc.items(), key=lambda x: -x[1]):
        print(f"  {k:<16} {v:+.1%}")
    print("-" * 64)
    print("全模型标准化系数 Top10（|β|）:")
    for c, v in coefs.abs().sort_values(ascending=False).head(10).items():
        print(f"  {c:<18} {coefs[c]:+.3f}")
    print("-" * 64)
    print("分桶画像（互动层级 × 特征均值）:")
    print(bucket.round(3).to_string())

    make_charts(df, inc, coefs, bucket, out_dir)
    html = build_html(df, r2_full, inc, coefs, bucket, out_dir)
    report_path = out_dir / "report_fit.html"
    report_path.write_text(html, encoding="utf-8")
    print("-" * 64)
    print(f"HTML 报告: {report_path}")


if __name__ == "__main__":
    main()
