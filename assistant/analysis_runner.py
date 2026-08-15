# -*- coding: utf-8 -*-
"""
analysis_runner.py — 运行流量分布 + 算法契合度两个分析模块，
并把核心结论序列化为 results.json 供 AI 助手读取展示。

用法（需 MediaCrawler 的 venv，含 pandas/matplotlib/jieba）：
  python analysis_runner.py --data-dir <jsonl目录> --out <results.json> --report-dir <报告目录>
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RT = HERE.parent / "realtime_analysis"
sys.path.insert(0, str(RT))

import matplotlib

matplotlib.use("Agg")
import pandas as pd

import analyze_fit as F
import analyze_lifecycle as L
import analyze_xhs as A


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report-dir", required=True)
    args = ap.parse_args()

    df = A.load_notes(args.data_dir)
    cm = A.load_comments(args.data_dir)
    if len(df) == 0:
        print(json.dumps({"error": "采集目录中还没有数据，请先完成数据采集"}, ensure_ascii=False))
        sys.exit(1)

    out_dir = Path(args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 流量分布分析（生成 report.html 与图表）
    summary_html, report_sections, df = A.analyze(df, cm, out_dir)

    # 2) 关键词赛道统计
    kw_list = []
    for k, g in df.groupby("keyword"):
        kw_list.append({
            "keyword": str(k),
            "notes": int(len(g)),
            "median_interact": round(float(g["interact"].median())),
            "total_interact": int(g["interact"].sum()),
            "boom": int((g["interact"] >= 1000).sum()),
        })
    kw_list.sort(key=lambda x: -x["median_interact"])

    # 3) 品类结构（含四象限定位）
    df, cat_stats, _ = A.analyze_categories(df, out_dir)
    cats = []
    for name, row in cat_stats.iterrows():
        sub = df[df["category"] == name].nlargest(3, "interact")
        top_notes = [
            {"title": r["title"][:44], "interact": int(r["interact"]), "url": r["note_url"]}
            for _, r in sub.iterrows()
        ]
        cats.append({
            "name": str(name),
            "notes": int(row["笔记数"]),
            "share": round(float(row["笔记占比"]), 3),
            "median": round(float(row["中位互动"])),
            "boom_rate": round(float(row["爆款率"]), 3),
            "collect_like": round(float(row["收藏赞比"]), 3),
            "video_share": round(float(row["视频占比"]), 3),
            "position": row["定位"],
            "top_notes": top_notes,
        })
    cats.sort(key=lambda x: -x["notes"])

    # 4) 算法契合度（玩法/内容/品类解释力 + 流量池桶画像）
    now_ts = max(int(df["publish_ts"].max()), int(datetime.now().timestamp() * 1000))
    fdf = F.build_features(df, now_ts)
    cat_d = pd.get_dummies(fdf["category"], prefix="cat").astype(int)
    kw_d = pd.get_dummies(fdf["keyword"], prefix="kw").astype(int)
    fdf = pd.concat([fdf, cat_d, kw_d], axis=1)
    r2_full, inc, coefs = F.incremental_r2(fdf)
    buckets = F.bucket_analysis(fdf)
    bucket_rows = [
        {"pool": str(pool), **{c: round(float(row[c]), 3) for c in row.index}}
        for pool, row in buckets.iterrows()
    ]

    # 生成契合度报告
    F.make_charts(fdf, inc, coefs, buckets, out_dir)
    fit_html = F.build_html(fdf, r2_full, inc, coefs, buckets, out_dir)
    (out_dir / "report_fit.html").write_text(fit_html, encoding="utf-8")

    # 5) 帖子生命周期（互动 × 发布时长）
    lm = L.compute_metrics(df, now_ts)
    life_buckets = [
        {"age": r["年龄"], "notes": int(r["笔记数"]), "median_interact": int(r["中位互动"]),
         "median_velocity": int(r["中位日均互动"]), "boom_rate": round(float(r["爆款率(≥1k)"]), 3)}
        for _, r in lm["bucket"].iterrows()
    ]
    life_cats = [
        {"name": r["品类"], "median_age": int(r["中位年龄(天)"]), "velocity": int(r["中位日均互动"]),
         "type": r["生命周期类型"]}
        for _, r in lm["cat_life"].iterrows()
    ]
    life_slopes = [{"name": k, "slope": round(v[0], 2), "r2": round(v[1], 3)}
                   for k, v in lm["slope_by_cat"].items()]
    lifecycle = {
        "half_life_days": round(lm["half_life"], 1) if lm["half_life"] != float("inf") else None,
        "overall_slope": round(lm["overall_slope"], 3),
        "fast_boom_ratio": round(lm["fast_ratio"], 3),
        "tail_boom_ratio": round(lm["tail_ratio"], 3),
        "age_buckets": life_buckets,
        "category_life": life_cats,
        "category_slopes": life_slopes,
        "report_html": str(out_dir / "report_lifecycle.html"),
    }

    # 生成生命周期报告
    L.make_charts(lm["df"], lm["slope_by_cat"], lm["half_life"], out_dir)
    life_html = L.build_html(lm["df"], lm["bucket"], lm["cat_life"], lm["slope_by_cat"],
                             lm["half_life"], lm["fast_ratio"], lm["tail_ratio"], out_dir)
    (out_dir / "report_lifecycle.html").write_text(life_html, encoding="utf-8")

    # 6) 全样本爆款榜
    top_all = df.nlargest(10, "interact")[["title", "interact", "note_url", "keyword"]]
    top_all_list = [
        {"title": r["title"][:44], "interact": int(r["interact"]),
         "url": r["note_url"], "keyword": str(r["keyword"])}
        for _, r in top_all.iterrows()
    ]

    results = {
        "meta": {
            "n": int(len(df)),
            "comments": int(len(cm)),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "r2_full": round(float(r2_full), 3),
        },
        "keywords": kw_list,
        "categories": cats,
        "fit_groups": {str(k): round(float(v), 4) for k, v in inc.items()},
        "top_coefs": [{"name": str(k), "abs": round(float(v), 3)}
                      for k, v in coefs.abs().sort_values(ascending=False).head(8).items()],
        "buckets": bucket_rows,
        "lifecycle": lifecycle,
        "top_notes": top_all_list,
        "report_html": str(out_dir / "report.html"),
        "fit_report_html": str(out_dir / "report_fit.html"),
    }
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("RESULTS WRITTEN:", args.out)


if __name__ == "__main__":
    main()
