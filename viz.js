'use strict';
// ============================================================
// viz.js — 可视化工具：PCA 降维散点图 / 横向条形图
// ============================================================

function dotP(a, b) { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; }

function powerIter(C, d) {
  let v = new Array(d).fill(1 / Math.sqrt(d));
  for (let it = 0; it < 200; it++) {
    const nv = new Array(d).fill(0);
    for (let i = 0; i < d; i++) for (let j = 0; j < d; j++) nv[i] += C[i][j] * v[j];
    const nm = Math.sqrt(nv.reduce((s, x) => s + x * x, 0));
    if (nm < 1e-14) break;
    const v2 = nv.map(x => x / nm);
    let delta = 0;
    for (let i = 0; i < d; i++) delta += Math.abs(v2[i] - v[i]);
    v = v2;
    if (delta < 1e-10) break;
  }
  return v;
}

function rayleigh(C, v) {
  const Cv = new Array(C.length).fill(0);
  for (let i = 0; i < C.length; i++) for (let j = 0; j < C.length; j++) Cv[i] += C[i][j] * v[j];
  let s = 0;
  for (let i = 0; i < v.length; i++) s += v[i] * Cv[i];
  return s;
}

// 在 vectors 上拟合 PCA，返回投影函数
function fitPCA(vectors) {
  const n = vectors.length, d = vectors[0].length;
  const mean = new Array(d).fill(0);
  for (const v of vectors) for (let i = 0; i < d; i++) mean[i] += v[i];
  for (let i = 0; i < d; i++) mean[i] /= n;
  const C = Array.from({ length: d }, () => new Array(d).fill(0));
  for (const v of vectors) {
    for (let i = 0; i < d; i++) {
      for (let j = 0; j <= i; j++) C[i][j] += (v[i] - mean[i]) * (v[j] - mean[j]);
    }
  }
  for (let i = 0; i < d; i++) for (let j = i + 1; j < d; j++) C[i][j] = C[j][i];
  const e1 = powerIter(C, d);
  const l1 = rayleigh(C, e1);
  const C2 = C.map((row, i) => row.map((c, j) => c - l1 * e1[i] * e1[j]));
  const e2 = powerIter(C2, d);
  return v => ({ x: dotP(v, e1), y: dotP(v, e2) });
}

// 散点图。points: [{x, y, color, r, ring, ringW, title, shape, label}]
function renderScatter(points, opts) {
  const W = (opts && opts.W) || 430;
  const H = (opts && opts.H) || 300;
  const pad = 18;
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  let x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
  let y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
  if (x1 - x0 < 1e-9) { x0 -= 0.5; x1 += 0.5; }
  if (y1 - y0 < 1e-9) { y0 -= 0.5; y1 += 0.5; }
  const sx = x => pad + (x - x0) / (x1 - x0) * (W - 2 * pad);
  const sy = y => H - pad - (y - y0) / (y1 - y0) * (H - 2 * pad);
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" style="background:#16161d;border-radius:10px">';
  for (const p of points) {
    const cx = sx(p.x).toFixed(1), cy = sy(p.y).toFixed(1);
    if (p.shape === 'star') {
      const pts = [];
      for (let k = 0; k < 10; k++) {
        const ang = Math.PI / 2 + k * Math.PI / 5;
        const rr = k % 2 === 0 ? p.r : p.r * 0.45;
        pts.push((+cx + rr * Math.cos(ang)).toFixed(1) + ',' + (+cy - rr * Math.sin(ang)).toFixed(1));
      }
      s += '<polygon points="' + pts.join(' ') + '" fill="' + p.color + '" stroke="#fff" stroke-width="1.5"><title>' + p.title + '</title></polygon>';
    } else {
      s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + p.r + '" fill="' + p.color + '" opacity="0.88"'
        + (p.ring ? ' stroke="' + p.ring + '" stroke-width="' + (p.ringW || 2) + '"' : '')
        + '><title>' + p.title + '</title></circle>';
      if (p.label) {
        s += '<text x="' + cx + '" y="' + (+cy - p.r - 3).toFixed(1) + '" text-anchor="middle" fill="#ccc" font-size="10">' + p.label + '</text>';
      }
    }
  }
  s += '</svg>';
  return s;
}

// 横向条形图。items: [{label, value, color}]
function hBars(items, max) {
  const m = max || Math.max.apply(null, items.map(i => i.value).concat([1e-9]));
  return items.map(i => {
    const w = (i.value / m * 100).toFixed(1);
    return '<div class="hbar-row">'
      + '<span class="hbar-label">' + i.label + '</span>'
      + '<div class="hbar-track"><div class="hbar-fill" style="width:' + w + '%;background:' + (i.color || '#4d9fff') + '"></div></div>'
      + '<span class="hbar-val">' + (typeof i.value === 'number' ? i.value.toFixed(2) : i.value) + '</span>'
      + '</div>';
  }).join('');
}
