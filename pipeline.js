'use strict';
// ============================================================
// pipeline.js — 推荐链路：召回 → 粗排 → 精排 → 重排
// ============================================================

function byId(id) { return NOTE_BY_ID[id]; }

function cosine(a, b) {
  let d = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { d += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
  const den = Math.sqrt(na) * Math.sqrt(nb);
  return den === 0 ? 0 : d / den;
}

function jaccard(a, b) {
  const s = new Set(a);
  let inter = 0;
  for (const x of b) if (s.has(x)) inter++;
  return inter / (a.length + b.length - inter);
}

function recencyBoost(hoursAgo) { return Math.pow(0.5, hoursAgo / 72); }

// ---------- 召回通道 1：双塔向量召回（用户塔 × 笔记塔，余弦相似度） ----------
function recallEmbedding(userVec, notes) {
  return notes
    .map(n => ({ id: n.id, score: cosine(userVec, n.emb), source: '双塔向量' }))
    .filter(r => r.score > 0.05)
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

// ---------- 召回通道 2：Item-CF 协同过滤（历史笔记 × 候选笔记的标签共现） ----------
function recallItemCF(historyIds, notes) {
  return notes
    .filter(n => !historyIds.includes(n.id))
    .map(n => {
      let s = 0;
      for (const hid of historyIds) {
        const h = byId(hid);
        if (h) s += jaccard(h.tags, n.tags);
      }
      return { id: n.id, score: s, source: 'Item-CF' };
    })
    .filter(r => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

// ---------- 召回通道 3：内容/关键词召回（标签倒排 + 标题关键词命中） ----------
function recallContent(persona, notes) {
  return notes
    .map(n => {
      let s = 0;
      for (const t of n.tags) if (persona.keywords.includes(t)) s += 0.5;
      for (const kw of persona.keywords) if (n.title.includes(kw)) s += 0.6;
      return { id: n.id, score: s, source: '关键词' };
    })
    .filter(r => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

// ---------- 召回通道 4：热度/新鲜度兜底 ----------
function recallHot(notes) {
  return notes
    .map(n => ({ id: n.id, score: n.pop * recencyBoost(n.hoursAgo), source: '热度' }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

// ---------- 主入口 ----------
// weights: {ctr, comp, inter, follow} 已归一化
// noiseMap: 每篇笔记在本轮运行中的固定噪声（保证调权重时排序稳定可比）
function runPipeline(persona, weights, noiseMap) {
  const notes = NOTES;

  // 1) 召回：四路并行 + 加权合并去重
  const emb = recallEmbedding(persona.vec, notes);
  const cf = recallItemCF(persona.history, notes);
  const cnt = recallContent(persona, notes);
  const hot = recallHot(notes);

  const merged = {};
  const add = (r, w) => {
    if (!merged[r.id]) merged[r.id] = { id: r.id, score: 0, sources: [] };
    merged[r.id].score += r.score * w;
    if (!merged[r.id].sources.includes(r.source)) merged[r.id].sources.push(r.source);
  };
  emb.forEach(r => add(r, 1.0));
  cf.forEach(r => add(r, 0.7));
  cnt.forEach(r => add(r, 0.55));
  hot.forEach(r => add(r, 0.4));
  const recalled = Object.values(merged)
    .map(r => {
      const n = byId(r.id);
      r.match = cosine(persona.vec, n.emb);
      return r;
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 24);

  // 2) 粗排：轻量模型，相关性 + 热度 + 时效
  const rough = recalled.map(r => {
    const n = byId(r.id);
    const score = 0.45 * clamp(r.match, 0, 1) + 0.35 * n.pop + 0.2 * clamp(recencyBoost(n.hoursAgo) * 2, 0, 1);
    return { id: r.id, score, match: r.match };
  }).sort((a, b) => b.score - a.score);
  const roughOut = rough.slice(0, 12);

  // 3) 精排：多任务模型（CTR / 完读率 / 互动率 / 关注率）+ 加权融合
  const fine = roughOut.map(r => {
    const n = byId(r.id);
    const match = r.match;
    const noise = noiseMap[n.id] != null ? noiseMap[n.id] : 0;
    const ctr = sigmoid((n.coverScore - 0.55) * 2.4 + (n.titleScore - 0.5) * 1.6 + (n.pop - 0.5) * 0.7 + match * 0.7 + noise * 0.25);
    const comp = sigmoid((n.quality - 0.5) * 2.2 + (n.titleScore - 0.5) * 0.8 + match * 0.5 + noise * 0.2);
    const inter = sigmoid((n.quality - 0.55) * 2.8 + match * 0.9 + (n.pop - 0.5) * 0.5 + noise * 0.3);
    const follow = sigmoid((n.author.power - 0.4) * 2.1 + (n.quality - 0.5) * 1.1 + match * 0.5 + noise * 0.25);
    const fusion = weights.ctr * ctr + weights.comp * comp + weights.inter * inter + weights.follow * follow;
    return { id: r.id, ctr, comp, inter, follow, fusion };
  }).sort((a, b) => b.fusion - a.fusion);
  const fineOut = fine.slice(0, 8);

  // 4) 重排：多样性打散 + 新鲜度 + 质量兜底
  const seq = [];
  const tail = [];
  for (const f of fineOut) {
    const n = byId(f.id);
    let s = f.fusion;
    const recent = seq.slice(-2).map(x => byId(x.id).primary);
    const dup = recent.filter(t => t === n.primary).length >= 2;
    if (n.quality < 0.3) s -= 0.5;
    if (n.hoursAgo < 24) s += 0.03;
    const item = { id: f.id, score: s, reason: dup ? '多样性打散' : (n.hoursAgo < 24 ? '新鲜度加分' : '正常') };
    if (dup) tail.push(item);
    else seq.push(item);
  }
  const rerank = seq.concat(tail).sort((a, b) => b.score - a.score);
  const final = rerank.slice(0, 6);

  return { emb, cf, cnt, hot, recalled, rough, roughOut, fine, fineOut, rerank, final };
}
