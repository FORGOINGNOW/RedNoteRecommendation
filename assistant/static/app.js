'use strict';
// ============================================================
// app.js — 小红书赛道筛选 AI 助手 前端交互
// ============================================================

let env = null;
let results = null;
let advice = null;
let crawlPoll = null;

const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtInt = n => n >= 10000 ? (n/10000).toFixed(1)+'w' : Math.round(n);

async function api(path, opts) {
  const res = await fetch('/api' + path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {}));
  return res.json();
}
async function post(path, body) {
  return api(path, { method: 'POST', body: JSON.stringify(body || {}) });
}

// ---------- 步骤切换 ----------
function showStep(n) {
  document.querySelectorAll('.sec').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
  $('sec' + n).classList.add('active');
  document.querySelector('.step[data-step="' + n + '"]').classList.add('active');
  window.scrollTo(0, 0);
}
document.querySelectorAll('.step').forEach(b => b.addEventListener('click', () => showStep(b.dataset.step)));
$('toStep2Btn').addEventListener('click', () => showStep(2));
$('toStep3Btn').addEventListener('click', () => showStep(3));
$('toStep4Btn').addEventListener('click', () => showStep(4));
$('toStep5Btn').addEventListener('click', () => showStep(5));

// ---------- 环境检测 ----------
async function loadEnv() {
  env = await api('/env');
  const chips = [];
  chips.push(['采集器环境', env.venv_ok ? 'ok' : 'bad', env.venv_ok ? '采集器就绪' : '未找到（运行 setup.bat 自动安装）']);
  chips.push(['已有数据', env.notes > 0 ? 'ok' : 'warn', env.notes + ' 条笔记']);
  chips.push(['分析报告', env.results_exists ? 'ok' : 'warn', env.results_exists ? '已生成' : '未生成']);
  if (env.media_dir) chips.push(['采集器目录', 'warn', env.media_dir]);
  $('envChips').innerHTML = chips.map(c =>
    '<span class="chip-' + c[1] + '">' + c[0] + '：' + c[2] + '</span>').join('');
  $('kwInput').value = env.config.keywords;
  $('maxNotes').value = env.config.max_notes;
  $('maxNotesVal').textContent = env.config.max_notes;
  $('myKeywords').value = env.config.my_keywords || '英文学习,AI';
  $('llmKey').value = '';
  if (env.config.llm_key_set) $('llmKey').placeholder = '已配置（留空则保持不变）';
  if (env.media_dir) $('mediaDir').value = env.media_dir;
}
loadEnv();

$('maxNotes').addEventListener('input', () => {
  $('maxNotesVal').textContent = $('maxNotes').value;
  const eta = Math.ceil($('maxNotes').value * 0.9 / 60);
  $('etaText').textContent = '约 ' + eta + ' 小时（可中断续跑）';
});

// ---------- Step 1 保存配置 ----------
$('saveCfgBtn').addEventListener('click', async () => {
  const body = {
    keywords: $('kwInput').value.trim(),
    my_keywords: $('myKeywords').value.trim(),
    max_notes: +$('maxNotes').value,
    media_dir: $('mediaDir').value.trim(),
    llm: { api_key: $('llmKey').value, base_url: $('llmUrl').value, model: $('llmModel').value },
  };
  if (!body.keywords) { $('cfgMsg').textContent = '请填写至少 1 个关键词'; return; }
  const r = await post('/config', body);
  $('cfgMsg').textContent = r.ok ? '配置已保存，' + r.patched : '保存失败：' + (r.error || '');
  await loadEnv();
});

// ---------- Step 2 采集 ----------
async function refreshCrawl() {
  const s = await api('/crawl/status');
  $('csState').textContent = s.running ? '采集中…' : (s.started_at ? '已停止/结束' : '未启动');
  $('csNotes').textContent = s.notes;
  $('csComments').textContent = s.comments;
  $('csStarted').textContent = s.started_at || '—';
  const target = env ? env.config.max_notes * env.config.keywords.split(',').filter(k=>k.trim()).length : 100;
  const pct = Math.min(100, Math.round(s.notes / Math.max(target, 1) * 100));
  $('csBar').style.width = pct + '%';
  if (s.log_tail) $('csLog').textContent = s.log_tail;
  if (!s.running && crawlPoll) { clearInterval(crawlPoll); crawlPoll = null; }
  return s;
}

$('startCrawlBtn').addEventListener('click', async () => {
  const r = await post('/crawl/start');
  if (!r.ok) { alert(r.error || '启动失败'); return; }
  if (!r.already_running) alert('已启动！浏览器将自动打开，请用手机小红书 App 扫码登录，随后自动开始采集。');
  if (!crawlPoll) crawlPoll = setInterval(refreshCrawl, 5000);
  refreshCrawl();
});

$('stopCrawlBtn').addEventListener('click', async () => {
  await post('/crawl/stop');
  refreshCrawl();
});

// ---------- Step 3 分析 ----------
$('analyzeBtn').addEventListener('click', async () => {
  $('analyzeMsg').textContent = '分析中，约需 30-60 秒（分类+图表+回归）…';
  $('analyzeBtn').disabled = true;
  try {
    const r = await post('/analyze');
    if (!r.ok) { $('analyzeMsg').textContent = '分析失败：' + (r.error || '') + (r.log ? '\n' + r.log.slice(-300) : ''); return; }
    results = r.results;
    renderAnalysis(results);
    $('analyzeMsg').textContent = '分析完成！' + results.meta.n + ' 条笔记 · ' + results.meta.comments + ' 条评论';
    $('analyzeResult').classList.remove('hidden');
  } finally {
    $('analyzeBtn').disabled = false;
  }
});

function renderAnalysis(r) {
  const m = r.meta;
  $('metaCards').innerHTML = [
    ['样本笔记', m.n + ' 条'], ['采集评论', m.comments + ' 条'],
    ['全模型解释力 R²', (m.r2_full * 100).toFixed(1) + '%'],
    ['生成时间', m.generated_at],
  ].map(c => '<div class="m-card"><b>' + esc(c[0]) + '</b><span>' + esc(c[1]) + '</span></div>').join('');

  const kwMax = Math.max.apply(null, r.keywords.map(k => k.median_interact).concat([1]));
  $('kwBars').innerHTML = r.keywords.map(k => {
    const w = k.median_interact / kwMax * 100;
    return '<div class="bar-row"><span class="bar-label">' + esc(k.keyword) + '</span>'
      + '<div class="bar-track"><div class="bar-fill c-blue" style="width:' + w + '%"></div></div>'
      + '<span class="bar-val">中位 ' + fmtInt(k.median_interact) + ' · ' + k.notes + '篇</span></div>';
  }).join('') || '<p class="hint">无数据</p>';

  const catRows = r.categories.map(c =>
    '<tr><td>' + esc(c.name) + '</td><td>' + c.notes + '</td><td>' + (c.share * 100).toFixed(1) + '%</td>'
    + '<td>' + fmtInt(c.median) + '</td><td>' + (c.boom_rate * 100).toFixed(0) + '%</td>'
    + '<td>' + c.collect_like.toFixed(2) + '</td><td>' + esc(c.position) + '</td></tr>').join('');
  $('catTable').innerHTML = '<table><thead><tr><th>品类</th><th>笔记数</th><th>供给占比</th><th>中位互动</th><th>爆款率</th><th>收藏赞比</th><th>定位</th></tr></thead><tbody>' + catRows + '</tbody></table>';

  const fitItems = Object.entries(r.fit_groups).filter(x => !x[0].startsWith('剔除'));
  const fitMax = Math.max.apply(null, fitItems.map(x => Math.abs(x[1])).concat([0.001]));
  $('fitBars').innerHTML = fitItems.map(x =>
    '<div class="bar-row"><span class="bar-label">' + esc(x[0]) + '</span>'
    + '<div class="bar-track"><div class="bar-fill c-red" style="width:' + Math.abs(x[1]) / fitMax * 100 + '%"></div></div>'
    + '<span class="bar-val">' + (x[1] * 100).toFixed(1) + '%</span></div>').join('');

  if (r.buckets.length) {
    const cols = Object.keys(r.buckets[0]).filter(c => c !== 'pool');
    const head = '<tr><th>流量池</th>' + cols.map(c => '<th>' + esc(c) + '</th>').join('') + '</tr>';
    const body = r.buckets.map(b =>
      '<tr><td>' + esc(b.pool) + '</td>' + cols.map(c => '<td>' + b[c] + '</td>').join('') + '</tr>').join('');
    $('bucketTable').innerHTML = '<table><thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
  } else {
    $('bucketTable').innerHTML = '<p class="hint">样本不足，暂无分桶画像</p>';
  }

  const lc = r.lifecycle;
  if (lc && lc.age_buckets && lc.age_buckets.length) {
    $('lifeCards').innerHTML = [
      ['热度半衰期', (lc.half_life_days ? lc.half_life_days + ' 天' : '—')],
      ['7天内速成爆款率', (lc.fast_boom_ratio * 100).toFixed(0) + '%'],
      ['90天+长青爆款率', (lc.tail_boom_ratio * 100).toFixed(0) + '%'],
    ].map(c => '<div class="m-card"><b>' + esc(c[0]) + '</b><span>' + esc(c[1]) + '</span></div>').join('');
    const rows = lc.age_buckets.map(b =>
      '<tr><td>' + esc(b.age) + '</td><td>' + b.notes + '</td><td>' + fmtInt(b.median_interact)
      + '</td><td>' + b.median_velocity + '/天</td><td>' + (b.boom_rate * 100).toFixed(0) + '%</td></tr>').join('');
    $('lifeTable').innerHTML = '<table><thead><tr><th>发布后</th><th>笔记数</th><th>中位互动</th><th>中位日均互动</th><th>爆款率</th></tr></thead><tbody>' + rows + '</tbody></table>';
  } else {
    $('lifeTable').innerHTML = '<p class="hint">样本不足，暂无生命周期数据</p>';
  }

  const sd = r.search_demand;
  if (sd && sd.top && sd.top.length) {
    const rows = sd.top.slice(0, 15).map(x =>
      '<tr><td>' + esc(x.term) + '</td><td>' + x.demand.toFixed(2) + '</td><td>' + x.raw + '</td>'
      + '<td>' + x.supply + '</td><td>' + x.gap.toFixed(2) + '</td></tr>').join('');
    $('searchBox').innerHTML = '<table><thead><tr><th>搜索词</th><th>需求强度</th><th>被联想次数</th><th>笔记供给</th><th>缺口指数</th></tr></thead><tbody>'
      + rows + '</tbody></table><p class="hint">来自 ' + sd.n_records + ' 条联想词采集记录 · 需求高+供给少的词 = 蓝海选题入口（详情见搜索需求报告）</p>';
  } else {
    $('searchBox').innerHTML = '<p class="hint">暂无搜索联想词数据：运行一次采集后自动生成（每日更新已内置该采集）。</p>';
  }

  const cmp = r.compare;
  if (cmp && cmp.rows && cmp.rows.length) {
    const sig = pct => pct >= 0.975 ? '显著偏高' : (pct <= 0.025 ? '显著偏低' : '与整体一致');
    const rows = cmp.rows.map(x =>
      '<tr><td>' + esc(x.label) + '</td><td>' + x.mine + '</td><td>' + x.overall + '</td>'
      + '<td>' + x.mean.toFixed(0) + '±' + x.std.toFixed(0) + '</td><td>' + x.z + '</td>'
      + '<td>' + (x.pct * 100).toFixed(0) + '%</td><td>' + sig(x.pct) + '</td></tr>').join('');
    $('compareBox').innerHTML = '<table><thead><tr><th>指标</th><th>我的选题</th><th>全体</th><th>随机样本均值±σ</th><th>z值</th><th>百分位</th><th>判断</th></tr></thead><tbody>'
      + rows + '</tbody></table><p class="hint">我的选题：' + esc(cmp.my_keywords) + '（' + cmp.n_mine + ' 条）· 随机抽样 300 次</p>';
  } else {
    $('compareBox').innerHTML = '<p class="hint">我的选题样本不足（&lt;5 条），无法对比。可在高级设置中调整「我的选题关键词」后重新分析。</p>';
  }
}

// ---------- Step 4 入场建议 ----------
$('adviceBtn').addEventListener('click', async () => {
  $('adviceBtn').disabled = true;
  try {
    const r = await post('/advice', { use_llm: $('useLlm').checked });
    if (!r.ok) { alert(r.error || '生成失败'); return; }
    advice = r.advice;
    renderAdvice(advice);
    $('adviceEngine').textContent = '生成引擎：' + advice.engine + (advice.llm_error ? '（' + advice.llm_error + '）' : '');
    $('adviceResult').classList.remove('hidden');
  } finally {
    $('adviceBtn').disabled = false;
  }
});

function renderAdvice(a) {
  if (a.llm) {
    $('llmAdvice').classList.remove('hidden');
    $('llmAdvice').innerHTML =
      '<h3>AI 入场建议</h3><p>' + esc(a.llm.entry_advice).replace(/\n/g, '<br>') + '</p>'
      + (a.llm.operation_advice ? '<h3>AI 运营要点</h3><p>' + esc(a.llm.operation_advice).replace(/\n/g, '<br>') + '</p>' : '');
  }
  const vColor = { '蓝海机会': 'v-blue', '值得入场': 'v-green', '谨慎尝试': 'v-orange', '红海观望': 'v-red' };
  $('nicheCards').innerHTML = a.niche_scores.map(s =>
    '<div class="niche-card ' + (vColor[s.verdict] || '') + '"><div class="nc-head"><b>' + esc(s.name) + '</b>'
    + '<span class="nc-score">' + s.score + '</span></div>'
    + '<div class="nc-verdict">' + esc(s.verdict) + '</div>'
    + '<p class="nc-reason">' + esc(s.reason) + '</p>'
    + '<p class="nc-meta">中位互动 ' + fmtInt(s.median) + ' · 收藏赞比 ' + s.collect_like.toFixed(2) + ' · ' + s.notes + ' 篇样本</p></div>'
  ).join('');

  $('recommended').innerHTML = a.recommended.map(r =>
    '<div class="rec-card"><b>' + esc(r.position) + '</b>'
    + '<p class="rec-why">' + esc(r.why) + '</p>'
    + '<ul>' + r.angles.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul></div>'
  ).join('');

  $('benchmarks').innerHTML = a.benchmarks.map(b =>
    '<div class="bench-item"><a href="' + esc(b.url) + '" target="_blank">' + esc(b.title) + '</a>'
    + '<span>' + fmtInt(b.interact) + ' 互动 · ' + esc(b.category) + '</span></div>'
  ).join('');

  renderPlan(a);
}

// ---------- Step 5 运营方案 ----------
function renderPlan(a) {
  const phases = ['phase1', 'phase2', 'phase3'].map(k => {
    const p = a.plan[k];
    return '<div class="phase"><h3>' + esc(p.name) + '</h3><p class="phase-goal">目标：' + esc(p.goal) + '</p>'
      + '<ol>' + p.tasks.map(t => '<li>' + esc(t) + '</li>').join('') + '</ol></div>';
  }).join('');

  const sched = '<table><thead><tr><th>时间</th><th>做什么</th></tr></thead><tbody>'
    + a.publish_schedule.map(s => '<tr><td>' + esc(s.time) + '</td><td>' + esc(s.what) + '</td></tr>').join('')
    + '</tbody></table>';

  const kpis = '<table><thead><tr><th>指标</th><th>目标</th><th>时间点</th></tr></thead><tbody>'
    + a.kpis.map(k => '<tr><td>' + esc(k.metric) + '</td><td>' + esc(k.target) + '</td><td>' + esc(k.when) + '</td></tr>').join('')
    + '</tbody></table>';

  const risks = '<ul class="risk-list">' + a.risks.map(r => '<li>' + esc(r) + '</li>').join('') + '</ul>';

  $('planBox').innerHTML =
    '<h3>30 天三阶段计划</h3>' + phases
    + '<h3>发布节奏</h3>' + sched
    + '<h3>标题公式（结合真实数据总结）</h3><ul>' + a.title_formulas.map(f => '<li>' + esc(f) + '</li>').join('') + '</ul>'
    + '<h3>封面建议</h3><ul>' + a.cover_tips.map(f => '<li>' + esc(f) + '</li>').join('') + '</ul>'
    + '<h3>KPI 目标</h3>' + kpis
    + '<h3>风险提示</h3>' + risks;
}

$('copyPlanBtn').addEventListener('click', () => {
  if (!advice) { alert('请先生成入场建议'); return; }
  const text = ['【小红书赛道筛选 AI 助手 - 运营方案】',
    '', '== 推荐定位 ==',
    ...advice.recommended.map(r => r.position + '：' + r.why),
    '', '== 30天计划 ==',
    ...['phase1', 'phase2', 'phase3'].map(k => {
      const p = advice.plan[k];
      return [p.name + '（' + p.goal + '）', ...p.tasks.map(t => '- ' + t)].join('\n');
    }),
    '', '== 发布节奏 ==',
    ...advice.publish_schedule.map(s => s.time + '：' + s.what),
    '', '== 标题公式 ==',
    ...advice.title_formulas.map(f => '- ' + f),
    '', '== KPI ==',
    ...advice.kpis.map(k => '- ' + k.metric + '：' + k.target + '（' + k.when + '）'),
    '', '== 风险 ==',
    ...advice.risks.map(r => '- ' + r),
  ].join('\n');
  navigator.clipboard.writeText(text).then(() => alert('方案已复制到剪贴板'));
});
