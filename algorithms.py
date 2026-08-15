# -*- coding: utf-8 -*-
"""
algorithms.py — 小红书类推荐系统底层算法实现（numpy 版）
教学模拟，非官方算法。所有算法均为真实计算：
  召回层：双塔向量余弦相似度 / Item-CF 标签共现 / 关键词倒排 / 热度时效
  粗排层：轻量线性加权
  精排层：多任务模型（CTR/完读率/互动率/关注率）+ 加权融合
  重排层：多样性打散 + 新鲜度 + 质量兜底
  可视化：PCA 降维（协方差矩阵特征分解）
  分发层：多级流量池晋级（CES 门槛）
"""
import math
import random
import re

import numpy as np

# ---------------- 常量 ----------------
DIMS = ['美妆护肤', '穿搭时尚', '职场成长', '美食家居', '旅行', '健身', '数码科技', '情感学习']
DIM_COLORS = ['#ff6b9d', '#ffb84d', '#4d9fff', '#5ad1a1', '#4dd0e1', '#c085ff', '#8ea6ff', '#ff8a65']

# 五级流量池：曝光量递增，晋级门槛逐渐变严（CES = 每千次曝光的加权互动分）
POOLS = [
    {'imp': 500, 'ctrTh': 0.080, 'cesTh': 45, 'name': '初始流量池'},
    {'imp': 3000, 'ctrTh': 0.075, 'cesTh': 60, 'name': '二级流量池'},
    {'imp': 15000, 'ctrTh': 0.070, 'cesTh': 75, 'name': '三级流量池'},
    {'imp': 80000, 'ctrTh': 0.065, 'cesTh': 90, 'name': '四级流量池'},
    {'imp': 400000, 'ctrTh': 0.060, 'cesTh': 105, 'name': '爆发流量池'},
]


def clamp(x, a, b):
    return max(a, min(b, x))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


# ---------------- 工具函数 ----------------
def title_score(t):
    """标题质量启发式：长度适中 / 含数字 / 干货词 / 情绪词"""
    if not t:
        return 0.0
    s = 0.25
    if 8 <= len(t) <= 26:
        s += 0.15
    if re.search(r'\d', t):
        s += 0.15
    if re.search(r'公式|教程|攻略|清单|避坑|合集|测评|干货|模板', t):
        s += 0.2
    if re.search(r'救命|绝了|宝藏|天花板|平替|后悔|亲测|避雷|翻倍', t):
        s += 0.1
    if re.search(r'[！!？?]', t):
        s += 0.05
    return clamp(s, 0.0, 1.0)


def recency_boost(hours_ago):
    return 0.5 ** (hours_ago / 72.0)


def author_power(followers):
    return clamp(0.4 + 0.25 * math.log10(followers / 100.0 + 1.0), 0.35, 0.98)


def cosine_sim_matrix(vec, matrix):
    """向量与矩阵逐行余弦相似度"""
    den = np.linalg.norm(vec) * np.linalg.norm(matrix, axis=1) + 1e-12
    return matrix @ vec / den


# ---------------- 数据集：40 条模拟笔记 ----------------
# (id, title, tags, primary, secondary, quality, cover_score, cover_style, pop, hours_ago, author, followers)
NOTE_SPECS = [
    ('n01', '早八伪素颜妆，5分钟出门公式', ['美妆', '通勤', '妆容'], 0, 1, 0.70, 0.90, '对比图', 0.80, 12, '早八化妆间', 32000),
    ('n02', '油皮痘肌护肤全流程，真的不闷痘', ['护肤', '油皮', '痘肌'], 0, None, 0.75, 0.70, '实拍', 0.55, 40, '皮肤科小张', 18000),
    ('n03', '38块钱的平替口红，试色太顶了', ['口红', '试色', '平替'], 0, None, 0.60, 0.62, '拼贴', 0.85, 6, '口红收藏家', 9000),
    ('n04', '敏感肌一年空瓶总结（全是回购）', ['护肤', '敏感肌', '空瓶'], 0, None, 0.80, 0.72, '实拍', 0.40, 200, '敏肌自救指南', 5000),
    ('n05', '新手化妆刷怎么选？一张图讲清楚', ['美妆', '化妆刷', '教程'], 0, None, 0.65, 0.86, '大字', 0.30, 300, '化妆课代表', 12000),
    ('n06', '妆前打底到底要不要用隔离？', ['美妆', '隔离', '科普'], 0, None, 0.55, 0.42, '纯文字', 0.20, 150, '成分党小绿', 3000),
    ('n07', '小个子通勤穿搭公式，显高10cm', ['穿搭', '通勤', '显高'], 1, 2, 0.70, 0.90, '对比图', 0.75, 20, '153穿搭日记', 50000),
    ('n08', '梨形身材牛仔裤避坑清单', ['穿搭', '梨形', '牛仔裤'], 1, None, 0.68, 0.86, '大字', 0.50, 90, '梨形自救所', 20000),
    ('n09', '优衣库新品试穿报告（附尺码）', ['穿搭', '优衣库', '试穿'], 1, None, 0.60, 0.70, '实拍', 0.62, 30, '试衣间女孩', 8000),
    ('n10', '秋冬叠穿万能公式，衣柜不用大换血', ['穿搭', '秋冬', '叠穿'], 1, None, 0.72, 0.60, '拼贴', 0.45, 400, '慢时尚笔记', 10000),
    ('n11', '面试穿搭避雷：HR视角说真话', ['职场', '穿搭', '面试'], 1, 2, 0.78, 0.74, '实拍', 0.88, 8, 'HR老张', 120000),
    ('n12', '跳槽涨薪50%的谈判话术（亲测）', ['职场', '跳槽', '涨薪'], 2, None, 0.80, 0.42, '纯文字', 0.90, 15, '职场修罗场', 80000),
    ('n13', '大厂实习三个月，我总结的避坑清单', ['职场', '实习', '大厂'], 2, None, 0.70, 0.86, '大字', 0.70, 26, '实习日记本', 30000),
    ('n14', '简历这样写，面试邀约翻倍', ['职场', '简历', '面试'], 2, None, 0.75, 0.86, '大字', 0.60, 60, '简历优化师', 40000),
    ('n15', '00后整顿职场生存指南（别学我）', ['职场', '00后', '生存'], 2, 7, 0.60, 0.88, '对比图', 0.82, 4, '不想上班的小王', 60000),
    ('n16', '副业月入3000的真实经历', ['副业', '赚钱'], 2, None, 0.50, 0.40, '纯文字', 0.55, 50, '下班搞钱日记', 15000),
    ('n17', '职场沟通：怎么拒绝加班不背锅', ['职场', '沟通', '情商'], 2, 7, 0.72, 0.84, '大字', 0.48, 130, '职场显微镜', 25000),
    ('n18', '宿舍党10分钟快手早餐合集', ['美食', '宿舍', '快手菜'], 3, 7, 0.65, 0.60, '拼贴', 0.60, 100, '宿舍厨房', 40000),
    ('n19', '空气炸锅万能公式：万物皆可炸', ['美食', '空气炸锅'], 3, None, 0.68, 0.72, '实拍', 0.78, 10, '炸锅实验室', 70000),
    ('n20', '打工人一周便当备餐记录', ['美食', '便当', '备餐'], 3, 2, 0.60, 0.70, '实拍', 0.40, 220, '便当小姐', 20000),
    ('n21', '出租屋改造前后对比，只花了600', ['家居', '出租屋', '改造'], 3, None, 0.70, 0.92, '对比图', 0.72, 18, '出租屋美学', 60000),
    ('n22', '厨房收纳神器红黑榜', ['家居', '收纳', '厨房'], 3, None, 0.60, 0.84, '大字', 0.35, 350, '收纳强迫症', 8000),
    ('n23', '一人食也要好好吃饭：5道快手菜', ['美食', '一人食'], 3, None, 0.62, 0.70, '实拍', 0.30, 150, '一个人的餐桌', 3000),
    ('n24', '人均500玩转大理3天2晚攻略', ['旅行', '大理', '攻略'], 4, None, 0.72, 0.74, '实拍', 0.80, 5, '背包看世界', 90000),
    ('n25', '酒店开盲盒式踩坑实录', ['旅行', '酒店', '避坑'], 4, None, 0.55, 0.58, '拼贴', 0.50, 200, '出差狂魔', 10000),
    ('n26', '一个人旅行安全清单（女生必看）', ['旅行', '安全', '女生'], 4, 7, 0.70, 0.85, '大字', 0.68, 45, '独自出发', 30000),
    ('n27', '周末48小时短途游路线规划模板', ['旅行', '周末', '路线'], 4, None, 0.62, 0.84, '大字', 0.35, 300, '周末出走', 5000),
    ('n28', '帕梅拉跟练一个月，身体变化记录', ['健身', '帕梅拉'], 5, None, 0.70, 0.90, '对比图', 0.75, 15, '练出马甲线', 70000),
    ('n29', '减肥平台期怎么办？三个科学方法', ['减肥', '平台期'], 5, None, 0.72, 0.42, '纯文字', 0.55, 80, '减脂教练阿伦', 40000),
    ('n30', '办公室久坐党5分钟拉伸', ['健身', '拉伸', '久坐'], 5, 2, 0.60, 0.68, '实拍', 0.40, 160, '打工人健康局', 20000),
    ('n31', '新手健身房器械扫盲', ['健身', '器械', '新手'], 5, None, 0.62, 0.85, '大字', 0.30, 260, '铁馆小助手', 6000),
    ('n32', 'iPhone隐藏功能大合集（第3期）', ['数码', 'iPhone'], 6, None, 0.68, 0.86, '大字', 0.85, 3, '数码锦鲤', 150000),
    ('n33', '学生党手机选购避坑指南', ['数码', '手机', '学生党'], 6, 7, 0.65, 0.84, '大字', 0.50, 120, '参数党阿凯', 30000),
    ('n34', '让工作效率翻倍的5个App', ['数码', '效率工具', '职场'], 6, 2, 0.72, 0.44, '纯文字', 0.78, 9, '效率研究所', 100000),
    ('n35', '相机新手：参数到底怎么调', ['数码', '相机', '摄影'], 6, None, 0.70, 0.74, '实拍', 0.35, 400, '快门手记', 20000),
    ('n36', '恋爱脑自救手册：三个清醒信号', ['情感', '恋爱'], 7, None, 0.70, 0.44, '纯文字', 0.70, 30, '清醒恋爱脑', 60000),
    ('n37', '考研英语80分复习计划（完整版）', ['学习', '考研', '英语'], 7, 2, 0.80, 0.87, '大字', 0.65, 70, '考研上岸姐', 50000),
    ('n38', '每天5分钟背单词的野路子', ['学习', '背单词'], 7, None, 0.60, 0.84, '大字', 0.40, 240, '英语小野', 15000),
    ('n39', '新手爸妈囤货红黑榜（避雷版）', ['母婴', '囤货'], 7, None, 0.66, 0.60, '拼贴', 0.50, 90, '新手奶爸', 25000),
    ('n40', '独居女生安全感改造清单', ['情感', '独居', '安全'], 7, 3, 0.64, 0.88, '对比图', 0.58, 55, '独居研究所', 35000),
]

PERSONA_SPECS = [
    ('beauty', '美妆爱好者', [0.85, 0.50, 0.10, 0.15, 0.10, 0.10, 0.05, 0.10], ['n01', 'n02', 'n03'],
     ['美妆', '护肤', '口红', '妆容', '化妆', '素颜']),
    ('work', '职场新人', [0.10, 0.25, 0.90, 0.10, 0.05, 0.10, 0.15, 0.30], ['n12', 'n13', 'n14'],
     ['职场', '简历', '跳槽', '面试', '实习', '副业']),
    ('food', '美食控', [0.10, 0.10, 0.15, 0.90, 0.20, 0.10, 0.05, 0.20], ['n18', 'n19', 'n20'],
     ['美食', '快手菜', '空气炸锅', '食谱', '便当']),
    ('travel', '旅行爱好者', [0.15, 0.30, 0.10, 0.25, 0.85, 0.20, 0.10, 0.15], ['n24', 'n26', 'n27'],
     ['旅行', '攻略', '大理', '路线', '民宿']),
    ('fit', '健身自律党', [0.10, 0.20, 0.15, 0.20, 0.10, 0.85, 0.05, 0.10], ['n28', 'n29', 'n30'],
     ['健身', '减肥', '拉伸', '训练', '马甲线', '帕梅拉']),
    ('tech', '数码科技宅', [0.05, 0.10, 0.30, 0.10, 0.05, 0.05, 0.90, 0.20], ['n32', 'n33', 'n34'],
     ['数码', '手机', 'App', '效率', '相机', 'iPhone']),
    ('student', '备考学生党', [0.15, 0.20, 0.35, 0.25, 0.10, 0.10, 0.25, 0.80], ['n37', 'n38', 'n17'],
     ['考研', '学习', '背单词', '复习', '效率']),
]


def build_dataset():
    """构建笔记库与用户画像（与前端 data.js 同构，嵌入向量确定性生成）"""
    rng = np.random.default_rng(42)
    notes = []
    for (nid, title, tags, primary, secondary, q, cover, style, pop, hours, aname, followers) in NOTE_SPECS:
        emb = np.full(8, 0.06)
        emb[primary] = 0.72 + rng.random() * 0.28
        if secondary is not None:
            emb[secondary] = 0.30 + rng.random() * 0.25
        for i in range(8):
            if i != primary and i != secondary:
                emb[i] = 0.03 + rng.random() * 0.12
        notes.append({
            'id': nid, 'title': title, 'tags': tags, 'primary': primary,
            'emb': emb, 'quality': q, 'coverScore': cover, 'coverStyle': style,
            'pop': pop, 'hoursAgo': hours, 'titleScore': title_score(title),
            'author': {'name': aname, 'followers': followers, 'power': author_power(followers)},
        })
    personas = []
    for (pid, name, raw_vec, history, keywords) in PERSONA_SPECS:
        vec = np.array(raw_vec, dtype=float)
        personas.append({
            'id': pid, 'name': name, 'vec': vec / np.linalg.norm(vec),
            'history': history, 'keywords': keywords,
        })
    return notes, personas


NOTES, PERSONAS = build_dataset()
NOTE_BY_ID = {n['id']: n for n in NOTES}
PERSONA_BY_ID = {p['id']: p for p in PERSONAS}


# ============================================================
# 召回层
# ============================================================
def recall_embedding(persona, notes, top=10):
    """双塔向量召回：用户向量 × 笔记向量，余弦相似度 TopN"""
    M = np.array([n['emb'] for n in notes])
    sims = cosine_sim_matrix(persona['vec'], M)
    items = []
    for n, s in zip(notes, sims):
        if s > 0.05:
            items.append({'id': n['id'], 'score': float(s), 'source': '双塔向量'})
    items.sort(key=lambda x: -x['score'])
    return items[:top]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    return inter / max(len(sa | sb), 1)


def recall_item_cf(persona, notes, top=10):
    """Item-CF：历史笔记与候选笔记的标签共现（近似共现矩阵）"""
    history = set(persona['history'])
    items = []
    for n in notes:
        if n['id'] in history:
            continue
        s = 0.0
        for hid in persona['history']:
            h = NOTE_BY_ID.get(hid)
            if h:
                s += jaccard(h['tags'], n['tags'])
        if s > 0:
            items.append({'id': n['id'], 'score': s, 'source': 'Item-CF'})
    items.sort(key=lambda x: -x['score'])
    return items[:top]


def recall_content(persona, notes, top=10):
    """关键词召回：标签倒排 + 标题关键词命中"""
    items = []
    for n in notes:
        s = 0.0
        for t in n['tags']:
            if t in persona['keywords']:
                s += 0.5
        for kw in persona['keywords']:
            if kw in n['title']:
                s += 0.6
        if s > 0:
            items.append({'id': n['id'], 'score': s, 'source': '关键词'})
    items.sort(key=lambda x: -x['score'])
    return items[:top]


def recall_hot(notes, top=10):
    """热度召回：热度 × 时效衰减"""
    items = [{'id': n['id'], 'score': n['pop'] * recency_boost(n['hoursAgo']), 'source': '热度'} for n in notes]
    items.sort(key=lambda x: -x['score'])
    return items[:top]


# ============================================================
# 主链路：召回 → 粗排 → 精排 → 重排
# ============================================================
def run_pipeline(persona, weights, seed=1):
    """
    weights: {'ctr':.., 'comp':.., 'inter':.., 'follow':..} 归一化后的融合权重
    返回结构与前端 JS 引擎一致，供渲染层直接使用
    """
    rng = np.random.default_rng(seed)

    # 1) 召回：四路并行 + 加权合并去重
    channels = [
        (recall_embedding(persona, NOTES), 1.0),
        (recall_item_cf(persona, NOTES), 0.7),
        (recall_content(persona, NOTES), 0.55),
        (recall_hot(NOTES), 0.4),
    ]
    merged = {}
    for items, w in channels:
        for r in items:
            e = merged.setdefault(r['id'], {'id': r['id'], 'score': 0.0, 'sources': []})
            e['score'] += r['score'] * w
            if r['source'] not in e['sources']:
                e['sources'].append(r['source'])
    recalled = sorted(merged.values(), key=lambda x: -x['score'])[:24]
    for r in recalled:
        n = NOTE_BY_ID[r['id']]
        r['match'] = float(cosine_sim_matrix(persona['vec'], n['emb'].reshape(1, -1))[0])

    # 2) 粗排：轻量模型（相关性 + 热度 + 时效）
    rough = []
    for r in recalled:
        n = NOTE_BY_ID[r['id']]
        score = 0.45 * clamp(r['match'], 0, 1) + 0.35 * n['pop'] + 0.2 * clamp(recency_boost(n['hoursAgo']) * 2, 0, 1)
        rough.append({'id': r['id'], 'score': score, 'match': r['match']})
    rough.sort(key=lambda x: -x['score'])
    rough_out = rough[:12]

    # 3) 精排：多任务模型，向量化计算
    ids = [r['id'] for r in rough_out]
    notes = [NOTE_BY_ID[i] for i in ids]
    cover = np.array([n['coverScore'] for n in notes])
    ts = np.array([n['titleScore'] for n in notes])
    pop = np.array([n['pop'] for n in notes])
    match = np.array([r['match'] for r in rough_out])
    power = np.array([n['author']['power'] for n in notes])
    quality = np.array([n['quality'] for n in notes])
    noise = rng.uniform(-1.0, 1.0, size=len(ids))

    ctr = sigmoid((cover - 0.55) * 2.4 + (ts - 0.5) * 1.6 + (pop - 0.5) * 0.7 + match * 0.7 + noise * 0.25)
    comp = sigmoid((quality - 0.5) * 2.2 + (ts - 0.5) * 0.8 + match * 0.5 + noise * 0.2)
    inter = sigmoid((quality - 0.55) * 2.8 + match * 0.9 + (pop - 0.5) * 0.5 + noise * 0.3)
    follow = sigmoid((power - 0.4) * 2.1 + (quality - 0.5) * 1.1 + match * 0.5 + noise * 0.25)
    fusion = (weights['ctr'] * ctr + weights['comp'] * comp
              + weights['inter'] * inter + weights['follow'] * follow)

    fine = [
        {'id': i, 'ctr': float(a), 'comp': float(b), 'inter': float(c),
         'follow': float(d), 'fusion': float(f)}
        for i, a, b, c, d, f in zip(ids, ctr, comp, inter, follow, fusion)
    ]
    fine.sort(key=lambda x: -x['fusion'])
    fine_out = fine[:8]

    # 4) 重排：多样性打散 + 新鲜度 + 质量兜底
    seq, tail = [], []
    for f in fine_out:
        n = NOTE_BY_ID[f['id']]
        s = f['fusion']
        recent = [NOTE_BY_ID[x['id']]['primary'] for x in seq[-2:]]
        dup = recent.count(n['primary']) >= 2
        if n['quality'] < 0.3:
            s -= 0.5
        if n['hoursAgo'] < 24:
            s += 0.03
        reason = '多样性打散' if dup else ('新鲜度加分' if n['hoursAgo'] < 24 else '正常')
        (tail if dup else seq).append({'id': f['id'], 'score': s, 'reason': reason})
    rerank = seq + tail
    rerank.sort(key=lambda x: -x['score'])

    # 5) PCA 投影（笔记 + 用户）
    scatter = pca_scatter(persona)

    return {
        'recall': {'items': recalled, 'dropped': len(NOTES) - len({r['id'] for r in recalled})},
        'rough': {'items': rough, 'dropped': len(recalled) - len(rough_out)},
        'fine': {'items': fine, 'dropped': len(rough_out) - len(fine_out)},
        'rerank': {'items': rerank, 'dropped': len(fine_out) - min(len(rerank), 6)},
        'scatter': scatter,
    }


# ============================================================
# PCA 降维（协方差矩阵特征分解，取前两个主成分）
# ============================================================
def pca_scatter(persona):
    M = np.array([n['emb'] for n in NOTES])
    mean = M.mean(axis=0)
    X = M - mean
    cov = X.T @ X / len(X)
    eigval, eigvec = np.linalg.eigh(cov)           # 升序特征值
    e1, e2 = eigvec[:, -1], eigvec[:, -2]          # 前两大主成分
    proj = X @ np.stack([e1, e2], axis=1)          # (N, 2)
    points = [{'id': NOTES[i]['id'], 'x': float(proj[i, 0]), 'y': float(proj[i, 1])} for i in range(len(NOTES))]
    uv = (persona['vec'] - mean) @ np.stack([e1, e2], axis=1)
    return {'points': points, 'user': {'x': float(uv[0]), 'y': float(uv[1])}}


# ============================================================
# 流量池晋级模拟
# ============================================================
def check_audit(title):
    """机审：违禁词检测"""
    if re.search(r'微信|加[vV]|代购|刷单', title):
        return {'pass': False, 'reason': '检测到疑似导流/违规词（微信、加V、代购、刷单等），被机审拦截'}
    return {'pass': True, 'reason': None}


def compute_rates(cfg, pool_idx):
    """每个池内的行为率模拟：泛人群曝光越多，互动率衰减；衰减幅度带随机性"""
    rnd = lambda: 0.85 + random.random() * 0.3
    rnd_wide = lambda: 0.7 + random.random() * 0.6
    decay = (0.88 ** pool_idx) * (1.0 if pool_idx == 0 else rnd_wide())
    q = cfg['quality']
    ctr = clamp((0.018 + cfg['coverScore'] * 0.065 + cfg['titleScore'] * 0.03) * rnd() * (1 - pool_idx * 0.03), 0.005, 0.5)
    return {
        'ctr': ctr,
        'likeR': (0.018 + q * 0.05) * decay * rnd(),
        'favR': (0.01 + q * 0.045 + cfg['trackFav']) * decay * rnd(),
        'cmtR': (0.002 + q * 0.009) * decay * rnd(),
        'fwdR': (0.001 + q * 0.005) * decay * rnd(),
        'folR': (0.0004 + cfg['authorPower'] * 0.0008 + q * 0.0008) * decay * rnd(),
    }


def simulate_once(cfg):
    """单次完整分发模拟"""
    pools = []
    total_imp, total_fol = 0, 0.0
    for i, p in enumerate(POOLS):
        r = compute_rates(cfg, i)
        ces = ((r['likeR'] + r['favR']) * 1000 + r['cmtR'] * 1000 * 4
               + r['fwdR'] * 1000 * 4 + r['folR'] * 1000 * 8)
        passed = r['ctr'] >= p['ctrTh'] and ces >= p['cesTh']
        pools.append({'idx': i, 'imp': p['imp'], 'ctr': r['ctr'], 'ces': ces, 'pass': passed, 'rates': r})
        total_imp += p['imp']
        total_fol += r['folR'] * p['imp']
        if not passed:
            break
    inter_total = sum(x['imp'] * (x['rates']['likeR'] + x['rates']['favR'] + x['rates']['cmtR'] + x['rates']['fwdR']) for x in pools)
    return {'pools': pools, 'totalImp': total_imp, 'totalFol': total_fol, 'interTotal': inter_total}


def verdict_for(total_imp):
    if total_imp < 3000:
        return {'label': '普通笔记', 'cls': 'v-plain',
                'tip': '主要靠搜索页长尾流量。封面点击率是当前最大短板，目标 CTR > 8%（对比图/大字标题封面）'}
    if total_imp < 30000:
        return {'label': '小热笔记', 'cls': 'v-warm',
                'tip': '稳定跑完 2-3 级池。立即复刻同结构选题出系列笔记，靠量叠加涨粉'}
    if total_imp < 150000:
        return {'label': '小爆款', 'cls': 'v-hot',
                'tip': '冲击更高池的关键是互动率：评论区置顶提问、抛争议点（评论权重 ×4）'}
    return {'label': '大爆款', 'cls': 'v-boom',
            'tip': '爆发池全通！当天立刻发 1-2 篇同选题续作，承接爆款流量，涨粉效率最高'}


def full_simulate(cfg):
    """完整模拟：审核 + 分发 + 结论（对应 /api/simulate）"""
    res = simulate_once(cfg)
    return {
        'audit': check_audit(cfg['title']),
        'pools': res['pools'],
        'totalImp': res['totalImp'],
        'totalFol': res['totalFol'],
        'interTotal': res['interTotal'],
        'verdict': verdict_for(res['totalImp']),
    }


def simulate_batch(cfg, n=10):
    """批量模拟：同质量笔记连发 n 篇的分布"""
    results = [simulate_once(cfg) for _ in range(n)]
    bins = [(0, 3000), (3000, 30000), (30000, 150000), (150000, float('inf'))]
    hist = [sum(1 for r in results if lo <= r['totalImp'] < hi) for lo, hi in bins]
    return {
        'hist': hist,
        'avgImp': sum(r['totalImp'] for r in results) / n,
        'avgFol': sum(r['totalFol'] for r in results) / n,
        'boomRate': sum(1 for r in results if r['totalImp'] >= 30000) / n,
    }
