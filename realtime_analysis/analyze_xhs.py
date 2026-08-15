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

# ---------------- AI 内容分类（规则优先级从高到低，先命中者胜） ----------------
# 用户 7 类：学习/探索/具体应用/吃瓜/科普/前沿学术/教程·买课
# 数据驱动补充 2 类：AI生成内容（动漫短剧绘画娱乐）、观点讨论（行业观点/焦虑/趋势）
CATEGORY_RULES = [
    ("教程·买课", ["教程", "课程", "教你", "手把手", "保姆级", "网课", "训练营", "陪跑", "私教",
                   "知识付费", "全套", "从入门到精通", "报名", "领取", "免费资料", "1对1", "打卡群", "社群"], 1),
    ("吃瓜", ["爆料", "裁员", "降薪", "翻车", "争议", "道歉", "内幕", "八卦", "大瓜", "震惊", "反转",
              "离职", "暴雷", "崩了", "股价", "融资", "收购", "上市", "重磅", "官宣", "起诉", "打脸",
              "撕逼", "离谱", "没想到", "发布", "推出", "上新", "升级", "涨价", "降价", "大战", "针对",
              "封锁", "制裁", "退出", "停更", "不更新", "破解", "被裁", "裁掉", "裁", "大厂", "机构",
              "月薪", "支出", "创始人", "副总裁", "马斯克", "奥特曼", "扎克伯格", "黄仁勋", "沸沸扬扬",
              "对抗", "打不过", "看不懂", "复刻", "扒"], 2),
    ("前沿学术", ["论文", "arxiv", "学术", "模型架构", "架构", "算法", "顶会", "benchmark", "评测", "开源模型",
                  "训练", "推理", "强化学习", "技术解读", "论文解读", "research", "infra", "rl", "参数",
                  "token", "多模态", "向量", "微调", "rag", "上下文"], 3),
    ("具体应用", ["工作流", "效率", "副业", "提效", "摸鱼", "办公", "ppt", "写论文", "写代码", "画画",
                  "做视频", "简历", "面试", "赚钱", "变现", "落地", "实操", "工具推荐", "组合", "用ai",
                  "ai做", "帮我", "搞定", "效率工具", "打工", "上班", "生产力", "助手", "搭建", "部署",
                  "开发", "编程", "代码", "翻译", "写作", "剪辑", "文案", "运营", "自媒体", "账号", "自动化"], 4),
    ("AI生成内容", ["短剧", "动漫", "漫画", "ai绘画", "ai作图", "画风", "meme", "ai音乐", "ai唱歌",
                    "ai视频", "创意", "生成", "数字人"], 5),
    ("探索体验", ["体验", "实测", "试用", "尝试", "测评", "上手", "亲测", "折腾", "试了", "用了",
                  "玩了", "感受", "好玩", "新发现", "解锁", "隐藏功能", "玩法", "试玩", "内测", "抢先"], 6),
    ("观点讨论", ["恐吓", "痛恨", "焦虑", "替代", "失业", "出路", "看不下去了", "凭啥", "死掉", "获利",
                  "观点", "感悟", "思考", "建议", "形容", "讨论", "取代", "淘汰", "危机", "趋势", "未来"], 7),
    ("科普", ["科普", "什么是", "一文看懂", "一图读懂", "原理", "区别", "概念", "白话", "通俗", "图解",
              "扫盲", "盘点", "解释", "干货", "讲讲", "聊聊", "说清楚", "读懂", "定义"], 8),
    ("学习", ["学习", "入门", "小白", "从零", "零基础", "自学", "学习路线", "学习计划", "复习", "备考",
              "自我提升", "成长", "学生党", "考研", "英语"], 9),
]

CATEGORY_COLORS = {
    "教程·买课": "#ff2e4d", "吃瓜": "#ffb84d", "前沿学术": "#4d9fff", "具体应用": "#5ad1a1",
    "AI生成内容": "#ff6b9d", "探索体验": "#c085ff", "观点讨论": "#8ea6ff", "科普": "#4dd0e1",
    "学习": "#ff8a65", "未分类": "#666",
}


def classify_note(row):
    """基于标题+正文+标签的关键词规则分类（可按 CATEGORY_RULES 自行调参）"""
    text = ("%s %s %s" % (row.get("title", ""), row.get("desc", ""), row.get("tags", ""))).lower()
    for name, kws, _ in sorted(CATEGORY_RULES, key=lambda x: x[2]):
        for kw in kws:
            if kw in text:
                return name
    return "未分类"


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

    # 0. AI 内容七分类结构
    df, cat_stats, cat_sections = analyze_categories(df, out_dir)
    report.extend(cat_sections)

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
    return summary, report, df


# ---------------- 品类结构分析 ----------------
def analyze_categories(df, out_dir: Path):
    df = df.copy()
    df["category"] = df.apply(classify_note, axis=1)
    total_interact = max(df["interact"].sum(), 1)

    g = df.groupby("category")
    stats = g.agg(
        笔记数=("note_id", "count"),
        总互动=("interact", "sum"),
        中位互动=("interact", "median"),
        爆款数=("interact", lambda s: int((s >= 1000).sum())),
        收藏赞比=("collect_like", "median"),
        视频占比=("type", lambda s: (s == "视频").mean()),
    )
    stats["笔记占比"] = stats["笔记数"] / len(df)
    stats["互动占比"] = stats["总互动"] / total_interact
    stats["评论占比"] = df.groupby("category").apply(
        lambda x: x["comment"].sum() / max(x["interact"].sum(), 1), include_groups=False)
    stats["爆款率"] = stats["爆款数"] / stats["笔记数"]
    stats = stats.sort_values("笔记数", ascending=False)

    # 供给-效率四象限定位
    med_note_share = stats["笔记占比"].median()
    med_interact = stats["中位互动"].median()

    def position(row):
        hi_supply = row["笔记占比"] >= med_note_share
        hi_eff = row["中位互动"] >= med_interact
        if hi_supply and hi_eff:
            return "成熟赛道（供给大·流量高）"
        if not hi_supply and hi_eff:
            return "蓝海机会（供给小·流量高）"
        if hi_supply and not hi_eff:
            return "红海内卷（供给大·流量低）"
        return "冷门（供给小·流量低）"

    stats["定位"] = stats.apply(position, axis=1)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    # 左：供给 vs 流量占比
    x = range(len(stats))
    w = 0.38
    axes[0].bar([i - w / 2 for i in x], stats["笔记占比"], w, label="笔记占比（供给）", color="#4d9fff")
    axes[0].bar([i + w / 2 for i in x], stats["互动占比"], w, label="互动占比（流量）", color="#ff2e4d")
    axes[0].set_xticks(list(x))
    axes[0].set_xticklabels(stats.index, rotation=30, ha="right", fontsize=9)
    axes[0].set_title("各品类：内容供给 vs 流量需求")
    axes[0].legend()
    axes[0].tick_params(colors="white")
    # 右：供给-效率散点
    colors = [CATEGORY_COLORS.get(c, "#666") for c in stats.index]
    axes[1].scatter(stats["笔记占比"], stats["中位互动"], s=stats["爆款数"] * 30 + 80,
                    c=colors, alpha=0.85, edgecolors="white", linewidths=0.5)
    for name, row in stats.iterrows():
        axes[1].annotate(name, (row["笔记占比"], row["中位互动"]),
                         xytext=(5, 5), textcoords="offset points", fontsize=9, color="#ccc")
    axes[1].axvline(med_note_share, color="#666", ls="--", lw=0.8)
    axes[1].axhline(med_interact, color="#666", ls="--", lw=0.8)
    axes[1].set_xlabel("笔记占比（供给）")
    axes[1].set_ylabel("中位互动（流量效率，对数）")
    axes[1].set_yscale("log")
    axes[1].set_title("供给-效率定位图（气泡大小=爆款数）")
    axes[1].tick_params(colors="white")
    plt.tight_layout()
    chart_path = out_dir / "chart_category.png"
    plt.savefig(chart_path, dpi=110, facecolor="#1e1e28")
    plt.close()

    # 各品类代表笔记
    top_html = "<h3 style='color:#9a9aa8'>各品类互动 Top3 代表笔记</h3>"
    for cat in stats.index:
        sub = df[df["category"] == cat].nlargest(3, "interact")
        items = "".join(
            f"<li>{r['interact']:,} 互动 · <a href='{r['note_url']}' target='_blank'>{r['title'][:42]}</a></li>"
            for _, r in sub.iterrows()
        )
        top_html += f"<div class='cat-block'><b style='color:{CATEGORY_COLORS.get(cat,'#ccc')}'>{cat}</b><ul>{items}</ul></div>"

    disp = stats[["笔记数", "笔记占比", "总互动", "互动占比", "中位互动", "爆款数", "爆款率",
                  "收藏赞比", "评论占比", "视频占比", "定位"]].copy()
    disp = disp.round({
        "笔记占比": 3, "互动占比": 3, "中位互动": 0, "爆款率": 2,
        "收藏赞比": 2, "评论占比": 3, "视频占比": 2,
    })
    table_html = disp.to_html(classes="tbl", escape=False)

    uncl = int((df["category"] == "未分类").sum())
    note = f"<p class='hint'>规则分类（关键词命中，可在 CATEGORY_RULES 中调参）。未分类 {uncl} 条，占比 {uncl/max(len(df),1):.1%}</p>"

    section = [("AI 内容七分类结构", note + table_html + img_html(chart_path) + top_html)]
    return df, stats, section


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
.cat-block{{margin:10px 0}} .cat-block ul{{margin:4px 0 0 18px;font-size:12px;color:#ccc}} .cat-block a{{color:#4d9fff;text-decoration:none}}
.hint{{color:#9a9aa8;font-size:11px;margin:8px 0}}
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
    print("AI 内容七分类现状（按笔记数排序）:")
    if "category" in df.columns:
        cs = df.groupby("category").agg(
            笔记数=("note_id", "count"),
            总互动=("interact", "sum"),
            中位互动=("interact", "median"),
            爆款数=("interact", lambda s: int((s >= 1000).sum())),
            收藏赞比=("collect_like", "median"),
        ).sort_values("笔记数", ascending=False)
        print(cs.round(1).to_string())
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
    summary, report, df = analyze(df, cm, out_dir)
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
