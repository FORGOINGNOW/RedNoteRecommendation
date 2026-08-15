# -*- coding: utf-8 -*-
"""
analyze_xhs.py — 小红书真实采集数据分析（基于 MediaCrawler 导出的 jsonl）

输入：MediaCrawler 采集的 search_contents_*.jsonl / search_comments_*.jsonl
输出：
  1. 控制台数据报告
  2. report/ 目录：图表 PNG + 自包含 HTML 报告 + 清洗后的 notes.csv

用法（使用 MediaCrawler 的 venv，已含 pandas/matplotlib/jieba）：
  python analyze_xhs.py [--data-dir 采集jsonl目录] [--out-dir 输出目录]
"""
import argparse
import base64
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import jieba
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# ---------------- 配置 ----------------
STOPWORDS = set("""
的 了 是 我 你 他 她 它 们 在 有 和 就 不 人 都 一 个 上 也 很 到 说 要 去 会 着 没有 看 好 自己 这 那 吗 呢 啊 呀 哦 哈 啦 吧 但 被 让 给 把 还 又 再 最 与 或 及 从 对 为 以 之 其 而 于 得 地 可以 现在 什么 怎么 为什么 一下 就是 不是 应该 可能 如果 因为 所以 但是 然后 还有 已经 比较 特别 非常 太 多 少 今天 昨天 明天 笔记 小红书 谢谢 博主 真的 感觉 喜欢 大家 这个 那个 这个 我们 你们 他们 自己 起来 出来 就是 这个 各种 里面 一个 一起 真的 有点 每天 这样 那样 觉得 东西 时候 知道 发现 看到 看到 一下 一些 好多 不少 完全 直接 根本 其实 哈哈 哈哈哈 呜呜 分享 收藏 关注 评论 转发 点赞
""".split())

FONT_PATH_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def pick_font():
    for f in FONT_PATH_CANDIDATES:
        if os.path.isfile(f):
            return f
    return None


# ---------------- 数据加载 ----------------
def safe_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def parse_json_str(v):
    if not v or not isinstance(v, str):
        return None
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return None


def load_notes(data_dir):
    frames = []
    for path in sorted(glob.glob(str(Path(data_dir) / "search_contents_*.jsonl"))):
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                tags = parse_json_str(d.get("tag_list")) or []
                imgs = parse_json_str(d.get("image_list")) or []
                rows.append({
                    "note_id": d.get("note_id"),
                    "title": d.get("title", ""),
                    "desc": d.get("desc", ""),
                    "type": "视频" if d.get("type") == "video" else "图文",
                    "nickname": d.get("nickname", ""),
                    "liked": safe_int(d.get("liked_count")),
                    "collected": safe_int(d.get("collected_count")),
                    "comment": safe_int(d.get("comment_count")),
                    "shared": safe_int(d.get("share_count")),
                    "images": len(imgs),
                    "tags": ",".join(t.get("name", "") for t in tags),
                    "keyword": d.get("source_keyword", ""),
                    "publish_ts": safe_int(d.get("time")),
                    "note_url": d.get("note_url", ""),
                })
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        print("未找到 search_contents_*.jsonl，请先运行 MediaCrawler 采集")
        sys.exit(1)
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset="note_id", keep="first")
    df["publish_dt"] = pd.to_datetime(df["publish_ts"], unit="ms", errors="coerce")
    df["interact"] = df["liked"] + df["collected"] + df["comment"] + df["shared"]
    df["title_len"] = df["title"].str.len()
    df["collect_like"] = df["collected"] / df["liked"].replace(0, pd.NA)
    df["hour"] = df["publish_dt"].dt.hour
    df["weekday"] = df["publish_dt"].dt.dayofweek  # 0=周一
    return df


def load_comments(data_dir):
    comments = []
    for path in sorted(glob.glob(str(Path(data_dir) / "search_comments_*.jsonl"))):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                comments.append({
                    "note_id": d.get("note_id"),
                    "content": d.get("content", ""),
                    "like_count": safe_int(d.get("like_count")),
                })
    return pd.DataFrame(comments)


# ---------------- 分析 ----------------
def analyze(df, cm, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    report = []  # (section_title, html_block)

    total = len(df)
    n_video = int((df["type"] == "视频").sum())
    total_interact = int(df["interact"].sum())

    # 1. 关键词分布
    kw = df.groupby("keyword").agg(
        笔记数=("note_id", "count"),
        总互动=("interact", "sum"),
        中位互动=("interact", "median"),
        爆款数=("interact", lambda s: int((s >= 1000).sum())),
    ).sort_values("笔记数", ascending=False)
    report.append(("关键词流量分布", kw.to_html(classes="tbl")))

    # 2. 互动率分布（幂律/长尾）
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    sorted_interact = df["interact"].sort_values(ascending=False).reset_index(drop=True)
    ax.plot(sorted_interact.values, marker="o", ms=2, lw=0.8)
    ax.set_yscale("log")
    ax.set_title("笔记互动量排序（对数坐标）— 幂律长尾")
    ax.set_xlabel("排名")
    ax.set_ylabel("总互动（对数）")
    ax = axes[1]
    top10 = int(len(df) * 0.1) or 1
    head_share = float(df.nlargest(top10, "interact")["interact"].sum() / max(total_interact, 1))
    ax.pie([head_share, 1 - head_share], labels=[f"Top10% 笔记\n{head_share:.0%}", f"其余90%\n{1-head_share:.0%}"],
           autopct="%1.0f%%", startangle=90, colors=["#ff2e4d", "#3a3a48"],
           textprops={"color": "white"})
    ax.set_title("头部集中度：Top10% 笔记占总互动比")
    plt.tight_layout()
    chart_pie_path = out_dir / "chart_interact.png"
    plt.savefig(chart_pie_path, dpi=110, facecolor="#1e1e28")
    plt.close()
    report.append(("互动分布与头部集中度", img_html(chart_pie_path)))

    # 3. 图文 vs 视频
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    ax.pie([n_video, total - n_video], labels=["视频", "图文"], autopct="%1.1f%%", startangle=90,
           colors=["#4d9fff", "#ff2e4d"], textprops={"color": "white"})
    ax.set_title("笔记类型分布")
    ax = axes[1]
    df.groupby("type")["interact"].median().plot.bar(ax=ax, color=["#ff2e4d", "#4d9fff"])
    ax.set_title("各类型笔记互动中位数")
    ax.set_ylabel("中位互动")
    ax.tick_params(colors="white")
    plt.tight_layout()
    chart_type_path = out_dir / "chart_type.png"
    plt.savefig(chart_type_path, dpi=110, facecolor="#1e1e28")
    plt.close()
    report.append(("图文 vs 视频", img_html(chart_type_path)))

    # 4. 发布时间分布
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    hour_cnt = df["hour"].value_counts().sort_index()
    axes[0].bar(hour_cnt.index, hour_cnt.values, color="#4d9fff")
    axes[0].set_title("发布时段分布")
    axes[0].set_xlabel("小时")
    wk = df["weekday"].value_counts().sort_index()
    axes[1].bar(wk.index, wk.values, color="#ffb84d", tick_label=["周一", "周二", "周三", "周四", "周五", "周六", "周日"])
    axes[1].set_title("发布星期分布")
    axes[0].tick_params(colors="white")
    axes[1].tick_params(colors="white")
    plt.tight_layout()
    chart_time_path = out_dir / "chart_time.png"
    plt.savefig(chart_time_path, dpi=110, facecolor="#1e1e28")
    plt.close()
    report.append(("发布时间分布（24小时 × 星期）", img_html(chart_time_path)))

    # 5. 收藏赞比（干货指标）
    fig, ax = plt.subplots(figsize=(11, 3.6))
    cl = df["collect_like"].dropna()
    cl = cl[cl.between(0, 2.5)]
    ax.hist(cl, bins=40, color="#5ad1a1")
    ax.axvline(1.0, color="#ff2e4d", ls="--", label="收藏=点赞")
    ax.set_title("收藏/点赞比分布（>1 说明干货收藏价值高）")
    ax.legend()
    ax.tick_params(colors="white")
    plt.tight_layout()
    chart_cl_path = out_dir / "chart_collect_like.png"
    plt.savefig(chart_cl_path, dpi=110, facecolor="#1e1e28")
    plt.close()
    report.append(("收藏赞比", img_html(chart_cl_path)))

    # 6. 评论热词
    if not cm.empty:
        texts = cm["content"].dropna().astype(str)
        texts = texts[texts.str.len() > 1]
        all_text = "\n".join(texts.tolist())
        words = []
        for w in jieba.cut(all_text):
            w = w.strip()
            if len(w) >= 2 and re.fullmatch(r"[\u4e00-\u9fa5a-zA-Z0-9]+", w) and w.lower() not in STOPWORDS:
                words.append(w.lower())
        word_cnt = Counter(words).most_common(30)
        if word_cnt:
            try:
                from wordcloud import WordCloud
                font = pick_font()
                wc = WordCloud(width=900, height=360, background_color="#1e1e28",
                               font_path=font, max_font_size=90, colormap="Reds")
                wc.generate_from_frequencies(dict(word_cnt))
                wc_path = out_dir / "chart_wordcloud.png"
                wc.to_file(str(wc_path))
                word_cloud_html = img_html(wc_path)
            except Exception as e:
                word_cloud_html = "<p>词云生成失败: %s</p>" % e
            top_words = "<div class='kw'>" + " ".join(
                "<span>%s(%d)</span>" % (w, c) for w, c in word_cnt) + "</div>"
            report.append(("评论热词 Top30", word_cloud_html + top_words))

    # 7. 爆款榜
    top = df.nlargest(20, "interact")[
        ["title", "nickname", "keyword", "type", "liked", "collected", "comment", "shared", "interact", "publish_dt", "note_url"]
    ].copy()
    top["publish_dt"] = top["publish_dt"].dt.strftime("%Y-%m-%d")
    top = top.rename(columns={
        "title": "标题", "nickname": "作者", "keyword": "关键词", "type": "类型",
        "liked": "点赞", "collected": "收藏", "comment": "评论", "shared": "转发",
        "interact": "总互动", "publish_dt": "发布日期", "note_url": "链接",
    })
    top_html = "<table class='tbl'><thead><tr>" + "".join(f"<th>{c}</th>" for c in top.columns) + "</tr></thead><tbody>"
    for _, row in top.iterrows():
        cells = []
        for c in top.columns:
            v = row[c]
            if c == "标题":
                v = f"<a href='{row['链接']}' target='_blank'>{v[:40]}</a>" if row["链接"] else v[:40]
            elif c == "链接":
                continue
            cells.append(f"<td>{v}</td>")
        top_html += "<tr>" + "".join(cells) + "</tr>"
    top_html += "</tbody></table>"
    report.append(("互动量爆款榜 Top20", top_html))

    # 8. 总体指标
    summary = f"""
    <div class="summary">
      <div><b>{total}</b><span>采集笔记数</span></div>
      <div><b>{len(cm)}</b><span>采集评论数</span></div>
      <div><b>{n_video}/{total-n_video}</b><span>视频/图文</span></div>
      <div><b>{total_interact:,}</b><span>总互动量</span></div>
      <div><b>{int(df['interact'].median())}</b><span>互动中位数</span></div>
      <div><b>{int((df['interact']>=1000).sum())}</b><span>爆款数(≥1k)</span></div>
      <div><b>{float(df['collect_like'].median()):.2f}</b><span>收藏赞比中位数</span></div>
    </div>"""
    return summary, report


def img_html(path: Path):
    if not path.exists():
        return "<p>图表缺失</p>"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b64}" style="max-width:100%">'


def build_html(summary, report, df):
    sections = "".join(
        f"<section><h2>{t}</h2>{b}</section>" for t, b in report
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>小红书真实流量分析报告</title>
<style>
body{{background:#131318;color:#e8e8ee;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:24px;margin:0}}
h1{{color:#ff2e4d;font-size:22px}} h2{{color:#ffb84d;font-size:16px;margin:22px 0 8px}}
section{{background:#1e1e28;border:1px solid #32323f;border-radius:12px;padding:16px;margin-bottom:16px}}
.tbl{{width:100%;border-collapse:collapse;font-size:12px}}
.tbl th,.tbl td{{padding:6px 10px;border-bottom:1px solid #32323f;text-align:left}}
.tbl th{{color:#9a9aa8}} .tbl a{{color:#4d9fff;text-decoration:none}}
.summary{{display:flex;flex-wrap:wrap;gap:14px;padding:16px}}
.summary div{{background:#242430;border-radius:10px;padding:12px 18px;text-align:center;min-width:100px}}
.summary b{{display:block;font-size:20px;color:#ff2e4d}}
.summary span{{font-size:11px;color:#9a9aa8}}
.kw span{{display:inline-block;background:#242430;border:1px solid #32323f;border-radius:12px;padding:3px 10px;margin:3px;font-size:12px}}
.foot{{color:#5c5c6a;font-size:11px;text-align:center;margin-top:14px}}
</style></head><body>
<h1>小红书真实流量分析报告</h1>
<p style="color:#9a9aa8;font-size:12px">生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据来源 MediaCrawler 采集 · 仅供个人学习分析</p>
{summary}
{sections}
<p class="foot">互动=点赞+收藏+评论+转发 · 爆款定义：总互动≥1000 · 本报告不构成任何运营建议</p>
</body></html>"""


def print_console(summary_text, df):
    print("=" * 60)
    print("小红书真实流量分布分析")
    print("=" * 60)
    print(f"笔记总数: {len(df)} | 视频: {(df['type']=='视频').sum()} | 图文: {(df['type']=='图文').sum()}")
    print(f"总互动: {df['interact'].sum():,} | 互动中位数: {df['interact'].median():.0f}")
    print(f"爆款笔记(≥1k互动): {(df['interact']>=1000).sum()} 条, 占比 {(df['interact']>=1000).mean():.1%}")
    print(f"Top10% 头部集中度: {df.nlargest(max(len(df)//10,1),'interact')['interact'].sum()/max(df['interact'].sum(),1):.1%}")
    print(f"收藏赞比中位数: {df['collect_like'].median():.2f} (均值 {df['collect_like'].mean():.2f})")
    print("-" * 60)
    print("各关键词统计:")
    kw = df.groupby("keyword").agg(笔记数=("note_id", "count"), 中位互动=("interact", "median"), 总互动=("interact", "sum"))
    print(kw.to_string())
    print("-" * 60)
    top3 = df.nlargest(5, "interact")[["title", "interact", "keyword"]]
    for _, r in top3.iterrows():
        print(f"  TOP {r['title'][:38]}... 互动 {r['interact']:,} [{r['keyword']}]")


def main():
    ap = argparse.ArgumentParser()
    # realtime_analysis 在 RedNoteRecommendation/ 下，向上 4 级到达 E:\数据分析
    default_data = Path(__file__).resolve().parent.parent.parent.parent / "MediaCrawler" / "data" / "xhs" / "jsonl"
    if not default_data.exists():
        for cand in (Path("E:/数据分析/MediaCrawler/data/xhs/jsonl"),
                     Path("E:/MediaCrawler/data/xhs/jsonl")):
            if cand.exists():
                default_data = cand
                break
    ap.add_argument("--data-dir", default=str(default_data))
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "report"))
    args = ap.parse_args()

    df = load_notes(args.data_dir)
    cm = load_comments(args.data_dir)
    out_dir = Path(args.out_dir)
    summary, report = analyze(df, cm, out_dir)
    html = build_html(summary, report, df)
    html_path = out_dir / "report.html"
    html_path.write_text(html, encoding="utf-8")
    df.to_csv(out_dir / "notes.csv", index=False, encoding="utf-8-sig")

    print_console("", df)
    print("-" * 60)
    print(f"HTML 报告: {html_path}")
    print(f"CSV 数据: {out_dir / 'notes.csv'}")
    print(f"图表目录: {out_dir}")


if __name__ == "__main__":
    main()
