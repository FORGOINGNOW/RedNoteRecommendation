# -*- coding: utf-8 -*-
"""
advisor.py — 入场建议 + 运营方案生成
  规则引擎（基于真实分析数据，无需任何外部依赖）为主；
  可选接入 DeepSeek 等 OpenAI 兼容大模型对文案进行润色增强。
"""
import json
import re
import urllib.request

# ---------------- 规则引擎：赛道评分 ----------------
def score_category(c):
    s = 0.0
    s += min(c.get("median", 0) / 5000.0, 1.0) * 35          # 互动效率（中位互动）
    s += min(c.get("boom_rate", 0), 1.0) * 25                 # 爆款率
    s += min(max(c.get("collect_like", 0.0), 0.0), 1.5) / 1.5 * 20  # 干货度（收藏赞比）
    s += (1.0 - min(c.get("share", 0), 1.0)) * 20             # 供给竞争度（越少分越高）
    return round(min(s, 100.0))


def verdict(score):
    if score >= 75:
        return "蓝海机会"
    if score >= 60:
        return "值得入场"
    if score >= 45:
        return "谨慎尝试"
    return "红海观望"


def niche_reason(c):
    parts = []
    if c["median"] >= 4000:
        parts.append("互动效率高")
    if c["boom_rate"] >= 0.8:
        parts.append("爆款率高")
    if c["collect_like"] >= 1.0:
        parts.append("收藏价值高(干货向)")
    if c["share"] <= 0.05:
        parts.append("供给少竞争小")
    if not parts:
        parts.append("供给大、流量一般，竞争激烈")
    return "；".join(parts)


# ---------------- 规则引擎：30 天运营方案 ----------------
def build_plan(results):
    kw = results["keywords"][0]["keyword"] if results["keywords"] else "你的赛道"
    best_cat = max(results["categories"], key=score_category)
    cat_name = best_cat["name"]

    buckets = results.get("buckets", [])
    if buckets:
        high = buckets[-1]
        title_len = str(round(high.get("title_len", 26)))
        tag_n = str(round(high.get("tag_count", 6)))
    else:
        title_len, tag_n = "26-32", "6-7"

    return {
        "phase1": {
            "name": "第 1 周 · 冷启动期（立人设）",
            "goal": "搭好账号地基，让算法认识你",
            "tasks": [
                "账号三件套：头像/昵称/简介全部包含「%s」相关关键词，简介写清楚你能帮谁解决什么问题" % kw,
                "发布 4 篇垂直笔记，全部围绕「%s × %s」一个组合定位，不发无关内容" % (kw, cat_name),
                "每篇结尾引导收藏（清单/模板/步骤结构），把收藏赞比做到 0.8 以上",
                "发完 24 小时内自评+回评，保持评论区活跃（评论权重×4）",
            ],
        },
        "phase2": {
            "name": "第 2-3 周 · 测试期（找爆款结构）",
            "goal": "用 8-10 篇笔记测出你自己的爆款结构",
            "tasks": [
                "每周 4-5 篇，固定 2-3 种结构轮换：清单合集 / 干货教程 / 观点复盘",
                "标题按「人群+痛点+数字+干货词」公式写，长度 %s 字左右，带 1 个情绪词" % title_len,
                "每篇打 %s 个精准标签，首图用大字标题或对比图风格" % tag_n,
                "每 3 天复盘一次：点击率低于 8% 换封面标题，收藏赞比低于 0.5 换选题",
                "记录每个选题的互动数据，找出你自己的 TOP 结构",
            ],
        },
        "phase3": {
            "name": "第 4 周起 · 放大期（复制爆款）",
            "goal": "把验证过的结构批量复制，承接平台推荐",
            "tasks": [
                "把数据最好的结构做成系列（第1期/第2期/第3期），保持日更或隔日更",
                "爆款笔记评论区置顶「下期预告」问题，拉互动接流量",
                "出现爆款当天立刻发 1-2 篇同选题续作，承接爆发流量",
                "粉丝过 1000 开通专业号，过 5000 申请官方合作资质",
                "同一结构连发 10 篇，用爆款率验证选题（目标 ≥30%%）",
            ],
        },
        "publish_schedule": [
            {"time": "周一", "what": "清单/合集型干货（收藏导向）"},
            {"time": "周三", "what": "教程型深度内容（关注导向）"},
            {"time": "周五", "what": "观点/讨论型内容（评论导向）"},
            {"time": "周末", "what": "复盘本周数据，批量准备下周选题"},
        ],
        "kpis": [
            {"metric": "粉丝数", "target": "300-500 粉（30 天）", "when": "第 4 周末"},
            {"metric": "爆款笔记", "target": "2 篇互动 ≥1000", "when": "第 2-3 周"},
            {"metric": "收藏赞比", "target": "稳定 >0.8", "when": "第 1 周末"},
            {"metric": "点击率", "target": "封面标题点击 >8%", "when": "每篇发布后 6 小时"},
        ],
        "risks": [
            "赛道数据为抽样分析，入场后需用自己账号数据二次验证",
            "平台推荐有随机性：同结构连发 10 篇，爆款率 30%% 即算健康",
            "采集注意频率与合规，避免账号风控",
        ],
    }


# ---------------- 规则引擎：主入口 ----------------
def rule_based_advice(results):
    scored = []
    for c in results["categories"]:
        s = score_category(c)
        scored.append({
            "name": c["name"],
            "score": s,
            "verdict": verdict(s),
            "reason": niche_reason(c),
            "median": c["median"],
            "notes": c["notes"],
            "collect_like": c["collect_like"],
        })
    scored.sort(key=lambda x: -x["score"])

    # 推荐定位：最高效关键词 × 得分最高的 2 个品类
    kw_rank = results["keywords"][:3]
    top_cats = [s for s in scored if s["name"] != "未分类"][:2]
    recommended = []
    for c in top_cats:
        kw0 = kw_rank[0]["keyword"] if kw_rank else ""
        recommended.append({
            "position": "%s × %s" % (kw0, c["name"]),
            "score": c["score"],
            "why": "%s：中位互动 %s，收藏赞比 %s，%s" % (
                c["verdict"], f"{c['median']:,}", f"{c['collect_like']:.2f}", c["reason"]),
            "angles": [
                "%s 领域的「可收藏清单」：把知识整理成模板/步骤，收藏赞比高" % kw0,
                "%s 领域的「观点复盘」：抛观点引评论，互动权重高" % kw0,
                "系列化：同结构做第1/2/3期，承接爆款流量",
            ],
        })

    # 对标笔记
    benchmarks = []
    for cat in results["categories"]:
        for n in cat.get("top_notes", [])[:1]:
            benchmarks.append({
                "title": n["title"],
                "interact": n["interact"],
                "url": n["url"],
                "category": cat["name"],
            })
    benchmarks.sort(key=lambda x: -x["interact"])
    benchmarks = benchmarks[:6]

    # 标题公式（结合数据）
    formulas = [
        "人群 + 痛点 + 数字 + 干货词（例：职场新人必看：30天AI提效的5个工作流）",
        "反常识观点 + 情绪词（例：AI学英语，90%的人都练错了方向）",
        "结果前置 + 亲测（例：亲测3个月，AI辅助学英语真的有用）",
        "清单合集（例：英文学习+AI工具，这份收藏清单就够了）",
    ]

    cover_tips = [
        "大字标题+高饱和色块：适合教程/清单类",
        "Before/After 对比图：适合学习打卡/效果展示",
        "数据可视化封面：把干货结论做成一张图",
    ]

    plan = build_plan(results)

    return {
        "engine": "规则引擎",
        "niche_scores": scored,
        "recommended": recommended,
        "benchmarks": benchmarks,
        "title_formulas": formulas,
        "cover_tips": cover_tips,
        "publish_schedule": plan["publish_schedule"],
        "plan": {k: plan[k] for k in ("phase1", "phase2", "phase3")},
        "kpis": plan["kpis"],
        "risks": plan["risks"],
    }


# ---------------- 可选：大模型润色（OpenAI 兼容接口，默认 DeepSeek） ----------------
def _summarize_for_llm(results):
    lines = ["以下是小红书香赛道数据分析摘要："]
    lines.append("关键词赛道（中位互动）：" + "；".join(
        "%s %s" % (k["keyword"], f"{k['median_interact']:,}") for k in results["keywords"]))
    lines.append("内容品类（笔记占比/中位互动/收藏赞比）：" + "；".join(
        "%s %s%%/%s/%s" % (c["name"], round(c["share"] * 100), f"{c['median']:,}", f"{c['collect_like']:.2f}")
        for c in results["categories"]))
    lines.append("算法契合度结论：全模型R²=%s，各因素解释力=%s" % (
        results["meta"]["r2_full"],
        json.dumps({k: v for k, v in results["fit_groups"].items() if not k.startswith("剔除")},
                   ensure_ascii=False)))
    return "\n".join(lines)


def call_llm(api_key, base_url, model, system_prompt, user_prompt, timeout=120):
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }).encode("utf-8")
    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def llm_enhance(results, api_key, base_url, model):
    system_prompt = (
        "你是小红书赛道分析专家。根据数据摘要，为小白用户输出两段中文文案："
        "第一段「入场建议」300字内：是否入场、选什么定位、为什么；"
        "第二段「运营要点」300字内：前30天最关键的3-5件事。"
        "只输出 JSON：{\"entry_advice\": \"...\", \"operation_advice\": \"...\"}，不要输出其他内容。"
    )
    user_prompt = _summarize_for_llm(results)
    text = call_llm(api_key, base_url, model, system_prompt, user_prompt)
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except ValueError:
        return {"entry_advice": cleaned, "operation_advice": ""}


def generate(results, api_key=None, base_url="https://api.deepseek.com", model="deepseek-chat", use_llm=False):
    advice = rule_based_advice(results)
    if use_llm and api_key:
        try:
            extra = llm_enhance(results, api_key, base_url, model)
            advice["engine"] = "规则引擎 + 大模型润色(" + model + ")"
            advice["llm"] = {
                "entry_advice": extra.get("entry_advice", ""),
                "operation_advice": extra.get("operation_advice", ""),
            }
        except Exception as e:
            advice["engine"] = "规则引擎（大模型调用失败，已自动降级）"
            advice["llm_error"] = str(e)
    return advice
