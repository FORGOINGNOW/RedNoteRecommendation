# -*- coding: utf-8 -*-
"""
report_common.py — 报告公共组件：统一导航头 + 报告中心索引页
"""
import base64
from datetime import datetime
from pathlib import Path

REPORTS = [
    ("index", "报告中心", "report_index.html"),
    ("flow", "流量分布", "report.html"),
    ("fit", "算法契合度", "report_fit.html"),
    ("life", "帖子生命周期", "report_lifecycle.html"),
    ("search", "搜索需求", "report_search.html"),
    ("compare", "选题对比", "report_compare.html"),
]

NAV_CSS = """
.nav{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0;justify-content:center}
.nav a{color:#9a9aa8;text-decoration:none;border:1px solid #32323f;background:#1e1e28;border-radius:16px;padding:5px 14px;font-size:12px}
.nav a.active{color:#fff;background:#ff2e4d;border-color:#ff2e4d}
.nav a:hover{color:#fff}
"""


def nav_html(active_key):
    items = []
    for key, name, fname in REPORTS:
        if key == active_key:
            items.append('<a class="active">%s</a>' % name)
        else:
            items.append('<a href="%s">%s</a>' % (fname, name))
    return '<div class="nav">%s</div>' % "".join(items)


def apply_nav(html, active_key):
    """把导航注入已有报告的 </style></head><body> 之后"""
    injection = "</style>" + NAV_CSS + "</head><body>" + nav_html(active_key)
    return html.replace("</style></head><body>", injection, 1)


def img_b64(path: Path):
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


def build_index(results, out_dir: Path):
    """报告中心索引页：链接全部报告 + 核心指标卡片"""
    out_dir = Path(out_dir)
    meta = results.get("meta", {})
    kw_top = sorted(results.get("keywords", []), key=lambda x: -x.get("median_interact", 0))
    kw_line = " · ".join("%s %s" % (k["keyword"], f"{k['median_interact']:,}") for k in kw_top[:6])
    lc = results.get("lifecycle", {})
    fit = results.get("fit_groups", {})
    cat_top = sorted(results.get("categories", []), key=lambda x: -x.get("median", 0))

    cards = ""
    for cat in cat_top[:3]:
        cards += ("<div class='m-card'><b>品类TOP: %s</b><span>中位互动 %s · %s</span></div>"
                  % (cat["name"], f"{cat['median']:,}", cat.get("position", "")))

    stats = [
        ("样本笔记", "%s 条" % meta.get("n", "-")),
        ("评论", "%s 条" % meta.get("comments", "-")),
        ("全模型R²", "%.0f%%" % (meta.get("r2_full", 0) * 100)),
        ("热度半衰期", ("%s 天" % lc.get("half_life_days")) if lc.get("half_life_days") else "-"),
        ("赛道池解释力", "%.0f%%" % (fit.get("采样控制(年龄+关键词)", 0) * 100)),
    ]
    stat_cards = "".join("<div class='m-card'><b>%s</b><span>%s</span></div>" % (k, v) for k, v in stats)

    links = "".join(
        "<a class='r-card' href='%s'><b>%s</b><span>%s</span></a>" % (fname, name, desc)
        for name, fname, desc in [
            ("流量分布报告", "report.html", "关键词赛道/品类结构/时段/词云/爆款榜"),
            ("算法契合度报告", "report_fit.html", "玩法vs内容vs赛道的解释力回归"),
            ("帖子生命周期报告", "report_lifecycle.html", "互动速率衰减/半衰期/品类生命周期"),
            ("搜索需求报告", "report_search.html", "用户主动搜索 × 内容供给缺口（蓝海词）"),
            ("选题对比报告", "report_compare.html", "你的选题 vs 全体 vs 随机抽样的行为一致性"),
        ]
    )

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>小红书数据分析 · 报告中心</title>
<style>
body{background:#131318;color:#e8e8ee;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:24px;margin:0;max-width:1000px;margin:0 auto}
h1{color:#ff2e4d;font-size:22px;text-align:center}
.sub{color:#9a9aa8;font-size:12px;text-align:center;margin-top:4px}
%(nav_css)s
.m-cards{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin:18px 0}
.m-card{background:#1e1e28;border:1px solid #32323f;border-radius:12px;padding:12px 18px;text-align:center;min-width:130px}
.m-card b{display:block;font-size:11px;color:#9a9aa8;font-weight:400}
.m-card span{font-size:16px;color:#ff2e4d;font-weight:700}
.links{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}
.r-card{background:#1e1e28;border:1px solid #32323f;border-radius:12px;padding:18px;text-decoration:none;display:block}
.r-card:hover{border-color:#ff2e4d}
.r-card b{color:#e8e8ee;font-size:15px;display:block}
.r-card span{color:#9a9aa8;font-size:12px;display:block;margin-top:6px}
.hint{color:#5c5c6a;font-size:11px;text-align:center;margin-top:16px}
</style></head><body>
%(nav)s
<h1>小红书数据分析 · 报告中心</h1>
<p class="sub">生成时间 %(ts)s · 最高效赛道：%(kw_line)s</p>
<div class="m-cards">%(stat_cards)s</div>
<div class="m-cards">%(cards)s</div>
<div class="links">%(links)s</div>
<p class="hint">数据仅供个人学习分析 · 报告由「小红书赛道筛选 AI 助手」自动生成</p>
</body></html>""" % {
        "nav_css": NAV_CSS, "nav": nav_html("index"),
        "ts": meta.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M")),
        "kw_line": kw_line or "-",
        "stat_cards": stat_cards, "cards": cards, "links": links,
    }
