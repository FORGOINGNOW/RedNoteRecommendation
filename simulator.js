'use strict';
// ============================================================
// simulator.js — 流量池晋级模拟器
// 计算与渲染分离：result 可由 Python 后端返回，也可由本地 JS 计算
// result 结构: {audit, pools, totalImp, totalFol, interTotal, verdict}
// ============================================================

const COVER_STYLES = [
  { name: 'Before/After 对比图', score: 0.92 },
  { name: '大字标题+高饱和色块', score: 0.86 },
  { name: 'ins风高清实拍', score: 0.72 },
  { name: '九宫格拼贴', score: 0.60 },
  { name: '纯文字白底', score: 0.42 },
  { name: '随手拍原图', score: 0.32 },
];

const AUTHOR_TYPES = [
  { name: '新号（<1000粉）', power: 0.5 },
  { name: '千粉博主', power: 1.0 },
  { name: '万粉博主', power: 1.4 },
];

const TRACKS = [
  { name: '美妆护肤', fav: 0 },
  { name: '穿搭时尚', fav: 0 },
  { name: '职场成长', fav: 0.006 },
  { name: '美食家居', fav: 0.002 },
  { name: '旅行攻略', fav: 0.004 },
  { name: '健身塑形', fav: 0.002 },
  { name: '数码科技', fav: 0.003 },
  { name: '情感/学习/母婴', fav: 0.007 },
];

// 五级流量池：曝光量递增，晋级门槛逐渐变严（CES = 每千次曝光的加权互动分）
const POOLS = [
  { imp: 500, ctrTh: 0.080, cesTh: 45, name: '初始流量池' },
  { imp: 3000, ctrTh: 0.075, cesTh: 60, name: '二级流量池' },
  { imp: 15000, ctrTh: 0.070, cesTh: 75, name: '三级流量池' },
  { imp: 80000, ctrTh: 0.065, cesTh: 90, name: '四级流量池' },
  { imp: 400000, ctrTh: 0.060, cesTh: 105, name: '爆发流量池' },
];

function sleep(ms) { return new Promise(res => setTimeout(res, ms)); }

// ---------- 本地 JS 计算引擎（后端不可用时的降级实现） ----------
function checkAudit(title) {
  if (/微信|加v|加V|代购|刷单/.test(title)) {
    return { pass: false, reason: '检测到疑似导流/违规词（微信、加V、代购、刷单等），被机审拦截' };
  }
  return { pass: true, reason: null };
}

function computeRates(cfg, poolIdx) {
  const rnd = () => 0.85 + Math.random() * 0.3;
  const rndWide = () => 0.7 + Math.random() * 0.6;
  const decay = Math.pow(0.88, poolIdx) * (poolIdx === 0 ? 1 : rndWide());
  const q = cfg.quality;
  const ctr = clamp((0.018 + cfg.coverScore * 0.065 + cfg.titleScore * 0.03) * rnd() * (1 - poolIdx * 0.03), 0.005, 0.5);
  return {
    ctr,
    likeR: (0.018 + q * 0.05) * decay * rnd(),
    favR: (0.01 + q * 0.045 + cfg.trackFav) * decay * rnd(),
    cmtR: (0.002 + q * 0.009) * decay * rnd(),
    fwdR: (0.001 + q * 0.005) * decay * rnd(),
    folR: (0.0004 + cfg.authorPower * 0.0008 + q * 0.0008) * decay * rnd(),
  };
}

function simulateOnce(cfg) {
  const pools = [];
  let totalImp = 0, totalFol = 0;
  for (let i = 0; i < POOLS.length; i++) {
    const p = POOLS[i];
    const r = computeRates(cfg, i);
    const ces = (r.likeR + r.favR) * 1000 + r.cmtR * 1000 * 4 + r.fwdR * 1000 * 4 + r.folR * 1000 * 8;
    const pass = r.ctr >= p.ctrTh && ces >= p.cesTh;
    pools.push({ idx: i, imp: p.imp, ctr: r.ctr, ces, pass, rates: r });
    totalImp += p.imp;
    totalFol += r.folR * p.imp;
    if (!pass) break;
  }
  return { pools, totalImp, totalFol };
}

function verdictFor(totalImp) {
  if (totalImp < 3000) return { label: '普通笔记', cls: 'v-plain', tip: '主要靠搜索页长尾流量。封面点击率是当前最大短板，目标 CTR > 8%（对比图/大字标题封面）' };
  if (totalImp < 30000) return { label: '小热笔记', cls: 'v-warm', tip: '稳定跑完 2-3 级池。立即复刻同结构选题出系列笔记，靠量叠加涨粉' };
  if (totalImp < 150000) return { label: '小爆款', cls: 'v-hot', tip: '冲击更高池的关键是互动率：评论区置顶提问、抛争议点（评论权重 ×4）' };
  return { label: '大爆款', cls: 'v-boom', tip: '爆发池全通！当天立刻发 1-2 篇同选题续作，承接爆款流量，涨粉效率最高' };
}

// 本地完整模拟（与后端 /api/simulate 返回结构一致）
function localFullSimulate(cfg) {
  const res = simulateOnce(cfg);
  let interTotal = 0;
  for (const p of res.pools) interTotal += p.imp * (p.rates.likeR + p.rates.favR + p.rates.cmtR + p.rates.fwdR);
  return {
    audit: checkAudit(cfg.title),
    pools: res.pools,
    totalImp: res.totalImp,
    totalFol: res.totalFol,
    interTotal,
    verdict: verdictFor(res.totalImp),
  };
}

// 本地批量模拟（与后端 /api/simulate_batch 返回结构一致）
function localBatch(cfg) {
  const results = [];
  for (let i = 0; i < 10; i++) results.push(simulateOnce(cfg));
  const bins = [[0, 3000], [3000, 30000], [30000, 150000], [150000, Infinity]];
  const hist = bins.map(b => results.filter(r => r.totalImp >= b[0] && r.totalImp < b[1]).length);
  return {
    hist,
    avgImp: results.reduce((s, r) => s + r.totalImp, 0) / 10,
    avgFol: results.reduce((s, r) => s + r.totalFol, 0) / 10,
    boomRate: results.filter(r => r.totalImp >= 30000).length / 10,
  };
}

function fmtPct(x) { return (x * 100).toFixed(1) + '%'; }
function fmtInt(n) {
  if (n >= 10000) return (n / 10000).toFixed(1) + 'w';
  return Math.round(n).toString();
}

// ---------- 带动画的单次发布渲染（result 为预计算结果） ----------
async function renderRun(containers, result) {
  containers.flow.innerHTML = '';
  containers.table.innerHTML = '';
  containers.verdict.innerHTML = '';
  containers.hist.innerHTML = '';

  let cards = '<div class="pool-card pc-audit" id="pcAudit"><div class="pc-name">机器审核</div><div class="pc-sub">违禁词 / 敏感词 / 搬运检测</div><div class="pc-status pc-pend">等待</div></div>';
  POOLS.forEach((p, i) => {
    cards += '<div class="pool-card" id="pc' + i + '"><div class="pc-name">' + p.name + '</div>'
      + '<div class="pc-sub">曝光 ' + fmtInt(p.imp) + ' · 门槛 CTR≥' + fmtPct(p.ctrTh) + ' · CES≥' + p.cesTh + '</div>'
      + '<div class="pc-status pc-pend" id="pcStatus' + i + '">待分发</div></div>';
  });
  containers.flow.innerHTML = cards;

  const setStatus = (i, cls, text) => {
    const el = document.getElementById('pcStatus' + i);
    if (el) { el.className = 'pc-status ' + cls; el.textContent = text; }
  };

  // 审核
  const auditStatus = document.getElementById('pcAudit').querySelector('.pc-status');
  await sleep(600);
  if (!result.audit.pass) {
    auditStatus.className = 'pc-status pc-fail';
    auditStatus.textContent = '拦截';
    containers.verdict.innerHTML = '<div class="verdict v-plain"><span class="v-label">审核不通过</span><p>' + result.audit.reason + '</p></div>';
    return;
  }
  auditStatus.className = 'pc-status pc-pass';
  auditStatus.textContent = '通过';

  const passCount = result.pools.length;
  const tblHeader = '<table><thead><tr><th>流量池</th><th>曝光</th><th>点击率</th><th>CES/千曝</th><th>门槛</th><th>结果</th></tr></thead><tbody>';
  let tblBody = '';

  for (let i = 0; i < POOLS.length; i++) {
    const p = POOLS[i];
    if (i < passCount) {
      const r = result.pools[i];
      setStatus(i, 'pc-run', '分发中');
      await sleep(650);
      const ok = r.pass;
      setStatus(i, ok ? 'pc-pass' : 'pc-fail', ok ? '晋级' : '停止');
      tblBody += '<tr><td>' + p.name + '</td><td>' + fmtInt(p.imp) + '</td><td>' + fmtPct(r.ctr)
        + '</td><td>' + r.ces.toFixed(1) + '</td><td>CTR≥' + fmtPct(p.ctrTh) + ' / CES≥' + p.cesTh
        + '</td><td>' + (ok ? '<span class="tag-ok">晋级</span>' : '<span class="tag-no">未达标</span>') + '</td></tr>';
      containers.table.innerHTML = tblHeader + tblBody + '</tbody></table>';
      await sleep(450);
    } else {
      setStatus(i, 'pc-skip', '未分发');
    }
  }

  let bars = '<div class="pool-bars">';
  POOLS.forEach((p, i) => {
    const done = i < passCount;
    const w = Math.sqrt(p.imp) / Math.sqrt(POOLS[4].imp) * 100;
    bars += '<div class="pbar-row"><span class="pbar-label">' + p.name + '</span>'
      + '<div class="pbar-track"><div class="pbar-fill ' + (done ? (result.pools[i].pass ? 'ok' : 'fail') : 'dim')
      + '" style="width:' + w.toFixed(1) + '%"></div></div>'
      + '<span class="pbar-val">' + (done ? fmtInt(p.imp) : '—') + '</span></div>';
  });
  bars += '</div>';

  const v = result.verdict;
  containers.verdict.innerHTML =
    '<div class="verdict ' + v.cls + '">'
    + '<div class="v-head"><span class="v-label">' + v.label + '</span>'
    + '<span class="v-nums">总曝光 <b>' + fmtInt(result.totalImp) + '</b> · 预估互动 <b>' + fmtInt(result.interTotal) + '</b> · 预估涨粉 <b>+' + Math.round(result.totalFol) + '</b></span></div>'
    + '<p>' + v.tip + '</p>'
    + '<h3>曝光瀑布（对数刻度宽度）</h3>' + bars
    + '</div>';
}

// ---------- 批量模拟渲染 ----------
function renderBatch(containers, result) {
  const bins = [
    { label: '普通\n<3000' },
    { label: '小热\n3k~3w' },
    { label: '小爆款\n3w~15w' },
    { label: '大爆款\n>15w' },
  ];
  let html = '<h3>同质量笔记连发 10 篇的分布</h3><div class="hist">';
  result.hist.forEach((c, i) => {
    html += '<div class="hist-col"><div class="hist-bar" style="height:' + (c / 10 * 130) + 'px"></div>'
      + '<div class="hist-num">' + c + '</div><div class="hist-label">' + bins[i].label.replace('\n', '<br>') + '</div></div>';
  });
  html += '</div><p class="hist-sum">平均曝光 <b>' + fmtInt(result.avgImp) + '</b> · 平均涨粉 <b>+' + Math.round(result.avgFol)
    + '</b> · 爆款率（≥3w曝光）<b>' + (result.boomRate * 100).toFixed(0) + '%</b></p>';
  containers.hist.innerHTML = html;
}
