'use strict';
// ============================================================
// app.js — 界面交互与渲染编排
// 双引擎：优先调用 Python·numpy 后端，后端不可用时降级为本地 JS 算法
// ============================================================

const API_BASE = location.protocol === 'file:' ? 'http://localhost:8765' : '';

const state = {
  persona: PERSONAS[0],
  weights: { ctr: 2, comp: 2, inter: 3, follow: 3 },
  seed: Math.floor(Math.random() * 1e9),
  noise: {},
  pipe: null,
  backend: false,
  backendInfo: null,
};

const COVER_GRAD = {
  '对比图': 'linear-gradient(135deg,#ff2e4d,#ff8a2e)',
  '大字': 'linear-gradient(135deg,#7a5cff,#4d9fff)',
  '实拍': 'linear-gradient(135deg,#2e8b57,#4db6ac)',
  '拼贴': 'linear-gradient(135deg,#b8860b,#ffb84d)',
  '纯文字': 'linear-gradient(135deg,#3a3a48,#55556a)',
  '随手拍': 'linear-gradient(135deg,#555,#777)',
};

function genNoise() {
  const m = {};
  NOTES.forEach(n => { m[n.id] = Math.random() * 2 - 1; });
  return m;
}

function normWeights(w) {
  const s = w.ctr + w.comp + w.inter + w.follow || 1;
  return { ctr: w.ctr / s, comp: w.comp / s, inter: w.inter / s, follow: w.follow / s };
}

function $(id) { return document.getElementById(id); }

async function fetchJSON(url, options) {
  const res = await fetch(API_BASE + url, options);
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

// 后端响应 → 本地 pipe 结构
function applyRecommend(d) {
  const P = {};
  P.recalled = d.recall.items;
  P.rough = d.rough.items;
  P.roughOut = d.rough.items.slice(0, 12);
  P.fine = d.fine.items;
  P.fineOut = d.fine.items.slice(0, 8);
  P.rerank = d.rerank.items;
  P.final = d.rerank.items.slice(0, 6);
  P.scatter = d.scatter;
  state.pipe = P;
}

async function runAll(reseed) {
  if (reseed) {
    state.seed = Math.floor(Math.random() * 1e9);
    state.noise = genNoise();
  }
  if (state.backend) {
    try {
      const d = await fetchJSON('/api/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona: state.persona.id, weights: state.weights, seed: state.seed }),
      });
      applyRecommend(d);
      renderAll();
      return;
    } catch (e) {
      console.warn('Python 后端调用失败，降级为本地 JS 引擎:', e);
      state.backend = false;
      updateBadge();
    }
  }
  state.pipe = runPipeline(state.persona, normWeights(state.weights), state.noise);
  renderAll();
}

// ---------------- 渲染 ----------------
function renderAll() {
  renderPersona();
  renderFlow();
  renderRecall();
  renderRough();
  renderFine();
  renderRerank();
  renderScatterBox();
  renderFeed();
}

function tbl(headers, rows, moreText) {
  const body = rows.map(r =>
    '<tr class="' + (r.cls || '') + '">' + r.cells.map(c => '<td' + (c.cls ? ' class="' + c.cls + '"' : '') + '>' + c.html + '</td>').join('') + '</tr>'
  ).join('');
  return '<div class="tbl-wrap"><table><thead><tr>'
    + headers.map(h => '<th>' + h + '</th>').join('')
    + '</tr></thead><tbody>' + body + '</tbody></table></div>'
    + (moreText ? '<div class="more">' + moreText + '</div>' : '');
}

function stagePanel(el, title, desc, inCount, outCount, content) {
  el.innerHTML =
    '<div class="stage-head"><div><span class="stage-name">' + title + '</span>'
    + '<div class="stage-desc">' + desc + '</div></div>'
    + '<div class="stage-count">输入 <b>' + inCount + '</b> → 输出 <b>' + outCount + '</b></div></div>'
    + content;
}

function renderPersona() {
  const p = state.persona;
  $('personaPicker').innerHTML = PERSONAS.map(x =>
    '<button class="persona-btn' + (x.id === p.id ? ' active' : '') + '" data-pid="' + x.id + '">' + x.name + '</button>'
  ).join('');
  Array.prototype.forEach.call($('personaPicker').children, btn => {
    btn.addEventListener('click', () => {
      state.persona = PERSONAS.find(x => x.id === btn.dataset.pid);
      runAll(true);
    });
  });
  $('userVecBars').innerHTML = hBars(DIMS.map((d, i) => ({ label: d, value: p.vec[i], color: DIM_COLORS[i] })));
  $('userHistory').innerHTML = p.history.map(id => {
    const n = byId(id);
    return '<span title="' + n.title + '">' + n.title.slice(0, 8) + '…</span>';
  }).join('');
}

function renderFlow() {
  const P = state.pipe;
  const steps = [
    ['全量笔记库', NOTES.length],
    ['多路召回', P.recalled.length],
    ['粗排', P.roughOut.length],
    ['精排', P.fineOut.length],
    ['重排', P.final.length],
  ];
  $('flowStrip').innerHTML = steps.map((s, i) =>
    '<span class="flow-chip">' + s[0] + '<b>' + s[1] + '</b></span>'
    + (i < steps.length - 1 ? '<span class="flow-arrow">→</span>' : '')
  ).join('');
}

function renderRecall() {
  const P = state.pipe;
  const rows = P.recalled.map((r, i) => {
    const n = byId(r.id);
    return {
      cells: [
        { html: '<span class="num">' + (i + 1) + '</span>' },
        { html: '<span title="' + n.title + '">' + n.title + '</span>' },
        { html: r.sources.map(s => '<span class="chip">' + s + '</span>').join('') },
        { html: '<span class="num">' + r.score.toFixed(2) + '</span>' },
      ],
    };
  });
  const dropped = NOTES.length - P.recalled.length;
  stagePanel($('stageRecall'), '召回层', '4 路召回并行取回候选，加权合并去重（向量1.0 / Item-CF 0.7 / 关键词0.55 / 热度0.4）',
    NOTES.length, P.recalled.length,
    tbl(['排名', '笔记', '召回来源', '综合分'], rows, '其余 ' + dropped + ' 条笔记未被任何通道召回'));
}

function renderRough() {
  const P = state.pipe;
  const rows = P.rough.map((r, i) => {
    const n = byId(r.id);
    const kept = i < P.roughOut.length;
    return {
      cls: kept ? '' : 'dropped',
      cells: [
        { html: '<span class="num">' + (i + 1) + '</span>' },
        { html: '<span title="' + n.title + '">' + n.title + '</span>', cls: kept ? '' : 'title-cell' },
        { html: '<span class="num">' + r.score.toFixed(3) + '</span>' },
        { html: kept ? '<span class="tag-ok">通过</span>' : '<span class="tag-no">淘汰</span>' },
      ],
    };
  });
  stagePanel($('stageRough'), '粗排层', '轻量模型快速过滤：0.45×相关性 + 0.35×热度 + 0.20×时效',
    P.recalled.length, P.roughOut.length,
    tbl(['排名', '笔记', '粗排分', '结果'], rows));
}

function renderFine() {
  const P = state.pipe;
  const w = normWeights(state.weights);
  const keptSet = new Set(P.fineOut.map(r => r.id));
  const rows = P.fine.map((r, i) => {
    const n = byId(r.id);
    const kept = keptSet.has(r.id);
    return {
      cls: kept ? '' : 'dropped',
      cells: [
        { html: '<span class="num">' + (i + 1) + '</span>' },
        { html: '<span title="' + n.title + '">' + n.title + '</span>', cls: kept ? '' : 'title-cell' },
        { html: '<span class="num">' + (r.ctr * 100).toFixed(1) + '%</span>' },
        { html: '<span class="num">' + (r.comp * 100).toFixed(1) + '%</span>' },
        { html: '<span class="num">' + (r.inter * 100).toFixed(1) + '%</span>' },
        { html: '<span class="num">' + (r.follow * 100).toFixed(1) + '%</span>' },
        { html: '<span class="num"><b>' + r.fusion.toFixed(4) + '</b></span>' },
        { html: kept ? '<span class="tag-ok">通过</span>' : '<span class="tag-no">淘汰</span>' },
      ],
    };
  });
  const chips = '<span class="w-chip">CTR×' + w.ctr.toFixed(2) + '</span>'
    + '<span class="w-chip">完读×' + w.comp.toFixed(2) + '</span>'
    + '<span class="w-chip">互动×' + w.inter.toFixed(2) + '</span>'
    + '<span class="w-chip">关注×' + w.follow.toFixed(2) + '</span>';
  stagePanel($('stageFine'), '精排层', '多任务模型（MMoE）同时预估 4 个目标，加权融合排序 ' + chips,
    P.roughOut.length, P.fineOut.length,
    tbl(['排名', '笔记', 'pCTR', '完读率', '互动率', '关注率', '融合分', '结果'], rows));
}

function renderRerank() {
  const P = state.pipe;
  const rows = P.rerank.map((r, i) => {
    const n = byId(r.id);
    const kept = i < 6;
    return {
      cls: kept ? '' : 'dropped',
      cells: [
        { html: '<span class="num">' + (i + 1) + '</span>' },
        { html: '<span title="' + n.title + '">' + n.title + '</span>', cls: kept ? '' : 'title-cell' },
        { html: '<span class="num">' + r.score.toFixed(4) + '</span>' },
        { html: '<span class="chip">' + r.reason + '</span>' },
        { html: kept ? '<span class="tag-ok">展示</span>' : '<span class="tag-no">后移</span>' },
      ],
    };
  });
  stagePanel($('stageRerank'), '重排层', '多样性打散（同话题连续≤2条）+ 新鲜度加分 + 质量兜底',
    P.fineOut.length, P.final.length,
    tbl(['排名', '笔记', '重排分', '规则', '结果'], rows));
}

function renderScatterBox() {
  const P = state.pipe;
  const recalledSet = new Set(P.recalled.map(r => r.id));
  const finalSet = new Set(P.final.map(r => r.id));
  let points, uv;
  if (P.scatter) {
    // 后端已计算 PCA 投影
    points = P.scatter.points.map(p => {
      const n = byId(p.id);
      const isFinal = finalSet.has(p.id);
      const isRec = recalledSet.has(p.id);
      return {
        x: p.x, y: p.y,
        color: DIM_COLORS[n.primary],
        r: isFinal ? 9 : 6,
        ring: isFinal ? '#ff2e4d' : (isRec ? '#4d9fff' : null),
        ringW: isFinal ? 2.5 : 2,
        title: n.title + ' | ' + n.tags.join('/'),
        label: isFinal ? 'TOP' + (P.final.findIndex(f => f.id === p.id) + 1) : null,
      };
    });
    uv = { x: P.scatter.user.x, y: P.scatter.user.y };
  } else {
    // 本地 JS 计算 PCA
    const project = fitPCA(NOTES.map(n => n.emb));
    points = NOTES.map(n => {
      const xy = project(n.emb);
      const isFinal = finalSet.has(n.id);
      const isRec = recalledSet.has(n.id);
      return {
        x: xy.x, y: xy.y,
        color: DIM_COLORS[n.primary],
        r: isFinal ? 9 : 6,
        ring: isFinal ? '#ff2e4d' : (isRec ? '#4d9fff' : null),
        ringW: isFinal ? 2.5 : 2,
        title: n.title + ' | ' + n.tags.join('/'),
        label: isFinal ? 'TOP' + (P.final.findIndex(f => f.id === n.id) + 1) : null,
      };
    });
    uv = project(state.persona.vec);
  }
  points.push({
    x: uv.x, y: uv.y, color: '#ffd54d', r: 11, shape: 'star',
    title: '用户向量：' + state.persona.name,
  });
  $('scatter').innerHTML = renderScatter(points, { W: 430, H: 280 });

  const legend = DIMS.map((d, i) =>
    '<span class="legend-item"><span class="legend-dot" style="background:' + DIM_COLORS[i] + '"></span>' + d + '</span>'
  ).join('');
  $('legend').innerHTML = legend
    + '<div class="legend-note">★ 用户向量 · 蓝圈=被召回 · 红圈=最终推荐（TOP排序）· 悬停看笔记名</div>';
}

function renderFeed() {
  const P = state.pipe;
  $('feed').innerHTML = P.final.map((f, i) => {
    const n = byId(f.id);
    const grad = COVER_GRAD[n.coverStyle] || COVER_GRAD['实拍'];
    return '<div class="feed-card">'
      + '<span class="rank-badge">#' + (i + 1) + '</span>'
      + '<div class="cover" style="background:' + grad + '">' + n.coverStyle + '</div>'
      + '<div class="fc-title" title="' + n.title + '">' + n.title + '</div>'
      + '<div class="fc-meta">' + n.author.name + ' · ' + fmtW(n.author.followers) + '粉 · ' + n.tags.join(' / ') + '</div>'
      + '</div>';
  }).join('');
}

// ---------------- 引擎探测与徽章 ----------------
function updateBadge() {
  const b = $('engineBadge');
  if (state.backend) {
    b.className = 'engine-badge on';
    b.textContent = '引擎：Python·numpy 后端（' + (state.backendInfo ? state.backendInfo.engine : 'numpy') + '）';
    b.title = '点击重新检测';
  } else {
    b.className = 'engine-badge off';
    b.textContent = '引擎：JS 本地降级 · 运行 python server.py 启用 Python 引擎（点击重试）';
    b.title = '点击重新检测后端';
  }
}

async function detectBackend() {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 2000);
    const res = await fetch(API_BASE + '/api/ping', { signal: ctrl.signal });
    clearTimeout(timer);
    if (res.ok) {
      state.backendInfo = await res.json();
      state.backend = true;
    } else {
      state.backend = false;
    }
  } catch (e) {
    state.backend = false;
  }
  updateBadge();
  runAll(true);
}

// ---------------- Tab1 控件 ----------------
function initSliders() {
  const defs = [
    ['ctr', '点击率 CTR'],
    ['comp', '完读率'],
    ['inter', '互动率'],
    ['follow', '关注率'],
  ];
  $('weightSliders').innerHTML = defs.map(d =>
    '<div class="slider-row"><div class="sl-top"><span>' + d[1] + '</span><b id="wv-' + d[0] + '">' + state.weights[d[0]] + '</b></div>'
    + '<input type="range" min="0" max="10" step="1" value="' + state.weights[d[0]] + '" data-w="' + d[0] + '"></div>'
  ).join('');
  Array.prototype.forEach.call($('weightSliders').querySelectorAll('input'), inp => {
    inp.addEventListener('input', () => {
      state.weights[inp.dataset.w] = +inp.value;
      $('wv-' + inp.dataset.w).textContent = inp.value;
      runAll(false);
    });
  });
  $('rerunBtn').addEventListener('click', () => runAll(true));
}

// ---------------- Tab2 ----------------
function initSimulator() {
  $('coverSelect').innerHTML = COVER_STYLES.map((c, i) =>
    '<option value="' + i + '">' + c.name + '</option>').join('');
  $('authorSelect').innerHTML = AUTHOR_TYPES.map((a, i) =>
    '<option value="' + i + '">' + a.name + '</option>').join('');
  $('trackSelect').innerHTML = TRACKS.map((t, i) =>
    '<option value="' + i + '">' + t.name + '</option>').join('');
  $('qualitySlider').addEventListener('input', () => {
    $('qualityVal').textContent = (+$('qualitySlider').value).toFixed(2);
  });

  function readCfg() {
    const cover = COVER_STYLES[+$('coverSelect').value];
    const author = AUTHOR_TYPES[+$('authorSelect').value];
    const track = TRACKS[+$('trackSelect').value];
    return {
      title: $('noteTitle').value.trim(),
      titleScore: titleScore($('noteTitle').value.trim()),
      coverScore: cover.score,
      quality: +$('qualitySlider').value,
      authorPower: author.power,
      trackFav: track.fav,
    };
  }

  const containers = {
    flow: $('poolFlow'),
    table: $('poolTable'),
    verdict: $('verdictBox'),
    hist: $('histBox'),
  };

  async function getSimulate() {
    if (state.backend) {
      try {
        return await fetchJSON('/api/simulate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(readCfg()),
        });
      } catch (e) {
        console.warn('后端调用失败，降级为本地 JS 引擎:', e);
        state.backend = false;
        updateBadge();
      }
    }
    return localFullSimulate(readCfg());
  }

  async function getBatch() {
    if (state.backend) {
      try {
        return await fetchJSON('/api/simulate_batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(readCfg()),
        });
      } catch (e) {
        console.warn('后端调用失败，降级为本地 JS 引擎:', e);
        state.backend = false;
        updateBadge();
      }
    }
    return localBatch(readCfg());
  }

  $('publishBtn').addEventListener('click', async () => {
    $('publishBtn').disabled = true;
    $('batchBtn').disabled = true;
    try {
      const result = await getSimulate();
      await renderRun(containers, result);
    } finally {
      $('publishBtn').disabled = false;
      $('batchBtn').disabled = false;
    }
  });

  $('batchBtn').addEventListener('click', async () => {
    const result = await getBatch();
    renderBatch(containers, result);
  });
}

// ---------------- Tab 切换 ----------------
function initTabs() {
  Array.prototype.forEach.call(document.querySelectorAll('.tab'), btn => {
    btn.addEventListener('click', () => {
      Array.prototype.forEach.call(document.querySelectorAll('.tab'), b => b.classList.remove('active'));
      Array.prototype.forEach.call(document.querySelectorAll('.panel'), p => p.classList.remove('active'));
      btn.classList.add('active');
      $('' + btn.dataset.tab).classList.add('active');
    });
  });
}

// ---------------- 启动 ----------------
initTabs();
initSliders();
initSimulator();
$('engineBadge').addEventListener('click', detectBackend);
detectBackend();
