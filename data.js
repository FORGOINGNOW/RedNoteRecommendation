'use strict';
// ============================================================
// data.js — 模拟数据集：笔记库 / 用户画像 / 公共工具函数
// 教学模拟，非小红书官方数据
// ============================================================

function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
const RNG = mulberry32(20240815);

// 8 维隐向量空间，每一维代表一个内容方向
const DIMS = ['美妆护肤', '穿搭时尚', '职场成长', '美食家居', '旅行', '健身', '数码科技', '情感学习'];
const DIM_COLORS = ['#ff6b9d', '#ffb84d', '#4d9fff', '#5ad1a1', '#4dd0e1', '#c085ff', '#8ea6ff', '#ff8a65'];

function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
function sigmoid(x) { return 1 / (1 + Math.exp(-x)); }

// 标题质量启发式：长度适中 / 含数字 / 干货词 / 情绪词
function titleScore(t) {
  if (!t) return 0;
  let s = 0.25;
  if (t.length >= 8 && t.length <= 26) s += 0.15;
  if (/\d/.test(t)) s += 0.15;
  if (/公式|教程|攻略|清单|避坑|合集|测评|干货|模板/.test(t)) s += 0.2;
  if (/救命|绝了|宝藏|天花板|平替|后悔|亲测|避雷|翻倍/.test(t)) s += 0.1;
  if (/[！!？?]/.test(t)) s += 0.05;
  return clamp(s, 0, 1);
}

// 由主/次方向生成 8 维笔记向量
function noteEmb(primary, secondary) {
  const e = [0.06, 0.06, 0.06, 0.06, 0.06, 0.06, 0.06, 0.06];
  e[primary] = 0.72 + RNG() * 0.28;
  if (secondary !== undefined) e[secondary] = 0.3 + RNG() * 0.25;
  for (let i = 0; i < 8; i++) {
    if (i !== primary && i !== secondary) e[i] = 0.03 + RNG() * 0.12;
  }
  return e;
}

let _nid = 0;
function makeNote(o) {
  _nid++;
  const n = {
    id: o.id || ('N' + _nid),
    title: o.title,
    tags: o.tags,
    primary: o.primary,
    coverScore: o.cover != null ? o.cover : 0.55,
    coverStyle: o.coverStyle || '实拍',
    quality: o.q != null ? o.q : 0.5,
    pop: o.pop != null ? o.pop : 0.15 + Math.pow(RNG(), 1.5) * 0.8,
    hoursAgo: o.hours != null ? o.hours : Math.floor(RNG() * 480),
    author: o.author || { name: '博主' + _nid, followers: 800 },
  };
  n.emb = noteEmb(o.primary, o.secondary);
  n.titleScore = o.ts != null ? o.ts : titleScore(n.title);
  // 作者权重由粉丝量推导（对数压缩）
  n.author.power = clamp(0.4 + 0.25 * Math.log10(n.author.followers / 100 + 1), 0.35, 0.98);
  return n;
}

// ------------------- 笔记库（40 条） -------------------
const NOTES = [
  makeNote({ id: 'n01', title: '早八伪素颜妆，5分钟出门公式', primary: 0, secondary: 1, tags: ['美妆', '通勤', '妆容'], q: 0.70, cover: 0.90, coverStyle: '对比图', pop: 0.80, hours: 12, author: { name: '早八化妆间', followers: 32000 } }),
  makeNote({ id: 'n02', title: '油皮痘肌护肤全流程，真的不闷痘', primary: 0, tags: ['护肤', '油皮', '痘肌'], q: 0.75, cover: 0.70, coverStyle: '实拍', pop: 0.55, hours: 40, author: { name: '皮肤科小张', followers: 18000 } }),
  makeNote({ id: 'n03', title: '38块钱的平替口红，试色太顶了', primary: 0, tags: ['口红', '试色', '平替'], q: 0.60, cover: 0.62, coverStyle: '拼贴', pop: 0.85, hours: 6, author: { name: '口红收藏家', followers: 9000 } }),
  makeNote({ id: 'n04', title: '敏感肌一年空瓶总结（全是回购）', primary: 0, tags: ['护肤', '敏感肌', '空瓶'], q: 0.80, cover: 0.72, coverStyle: '实拍', pop: 0.40, hours: 200, author: { name: '敏肌自救指南', followers: 5000 } }),
  makeNote({ id: 'n05', title: '新手化妆刷怎么选？一张图讲清楚', primary: 0, tags: ['美妆', '化妆刷', '教程'], q: 0.65, cover: 0.86, coverStyle: '大字', pop: 0.30, hours: 300, author: { name: '化妆课代表', followers: 12000 } }),
  makeNote({ id: 'n06', title: '妆前打底到底要不要用隔离？', primary: 0, tags: ['美妆', '隔离', '科普'], q: 0.55, cover: 0.42, coverStyle: '纯文字', pop: 0.20, hours: 150, author: { name: '成分党小绿', followers: 3000 } }),
  makeNote({ id: 'n07', title: '小个子通勤穿搭公式，显高10cm', primary: 1, secondary: 2, tags: ['穿搭', '通勤', '显高'], q: 0.70, cover: 0.90, coverStyle: '对比图', pop: 0.75, hours: 20, author: { name: '153穿搭日记', followers: 50000 } }),
  makeNote({ id: 'n08', title: '梨形身材牛仔裤避坑清单', primary: 1, tags: ['穿搭', '梨形', '牛仔裤'], q: 0.68, cover: 0.86, coverStyle: '大字', pop: 0.50, hours: 90, author: { name: '梨形自救所', followers: 20000 } }),
  makeNote({ id: 'n09', title: '优衣库新品试穿报告（附尺码）', primary: 1, tags: ['穿搭', '优衣库', '试穿'], q: 0.60, cover: 0.70, coverStyle: '实拍', pop: 0.62, hours: 30, author: { name: '试衣间女孩', followers: 8000 } }),
  makeNote({ id: 'n10', title: '秋冬叠穿万能公式，衣柜不用大换血', primary: 1, tags: ['穿搭', '秋冬', '叠穿'], q: 0.72, cover: 0.60, coverStyle: '拼贴', pop: 0.45, hours: 400, author: { name: '慢时尚笔记', followers: 10000 } }),
  makeNote({ id: 'n11', title: '面试穿搭避雷：HR视角说真话', primary: 1, secondary: 2, tags: ['职场', '穿搭', '面试'], q: 0.78, cover: 0.74, coverStyle: '实拍', pop: 0.88, hours: 8, author: { name: 'HR老张', followers: 120000 } }),
  makeNote({ id: 'n12', title: '跳槽涨薪50%的谈判话术（亲测）', primary: 2, tags: ['职场', '跳槽', '涨薪'], q: 0.80, cover: 0.42, coverStyle: '纯文字', pop: 0.90, hours: 15, author: { name: '职场修罗场', followers: 80000 } }),
  makeNote({ id: 'n13', title: '大厂实习三个月，我总结的避坑清单', primary: 2, tags: ['职场', '实习', '大厂'], q: 0.70, cover: 0.86, coverStyle: '大字', pop: 0.70, hours: 26, author: { name: '实习日记本', followers: 30000 } }),
  makeNote({ id: 'n14', title: '简历这样写，面试邀约翻倍', primary: 2, tags: ['职场', '简历', '面试'], q: 0.75, cover: 0.86, coverStyle: '大字', pop: 0.60, hours: 60, author: { name: '简历优化师', followers: 40000 } }),
  makeNote({ id: 'n15', title: '00后整顿职场生存指南（别学我）', primary: 2, secondary: 7, tags: ['职场', '00后', '生存'], q: 0.60, cover: 0.88, coverStyle: '对比图', pop: 0.82, hours: 4, author: { name: '不想上班的小王', followers: 60000 } }),
  makeNote({ id: 'n16', title: '副业月入3000的真实经历', primary: 2, tags: ['副业', '赚钱'], q: 0.50, cover: 0.40, coverStyle: '纯文字', pop: 0.55, hours: 50, author: { name: '下班搞钱日记', followers: 15000 } }),
  makeNote({ id: 'n17', title: '职场沟通：怎么拒绝加班不背锅', primary: 2, secondary: 7, tags: ['职场', '沟通', '情商'], q: 0.72, cover: 0.84, coverStyle: '大字', pop: 0.48, hours: 130, author: { name: '职场显微镜', followers: 25000 } }),
  makeNote({ id: 'n18', title: '宿舍党10分钟快手早餐合集', primary: 3, secondary: 7, tags: ['美食', '宿舍', '快手菜'], q: 0.65, cover: 0.60, coverStyle: '拼贴', pop: 0.60, hours: 100, author: { name: '宿舍厨房', followers: 40000 } }),
  makeNote({ id: 'n19', title: '空气炸锅万能公式：万物皆可炸', primary: 3, tags: ['美食', '空气炸锅'], q: 0.68, cover: 0.72, coverStyle: '实拍', pop: 0.78, hours: 10, author: { name: '炸锅实验室', followers: 70000 } }),
  makeNote({ id: 'n20', title: '打工人一周便当备餐记录', primary: 3, secondary: 2, tags: ['美食', '便当', '备餐'], q: 0.60, cover: 0.70, coverStyle: '实拍', pop: 0.40, hours: 220, author: { name: '便当小姐', followers: 20000 } }),
  makeNote({ id: 'n21', title: '出租屋改造前后对比，只花了600', primary: 3, tags: ['家居', '出租屋', '改造'], q: 0.70, cover: 0.92, coverStyle: '对比图', pop: 0.72, hours: 18, author: { name: '出租屋美学', followers: 60000 } }),
  makeNote({ id: 'n22', title: '厨房收纳神器红黑榜', primary: 3, tags: ['家居', '收纳', '厨房'], q: 0.60, cover: 0.84, coverStyle: '大字', pop: 0.35, hours: 350, author: { name: '收纳强迫症', followers: 8000 } }),
  makeNote({ id: 'n23', title: '一人食也要好好吃饭：5道快手菜', primary: 3, tags: ['美食', '一人食'], q: 0.62, cover: 0.70, coverStyle: '实拍', pop: 0.30, hours: 150, author: { name: '一个人的餐桌', followers: 3000 } }),
  makeNote({ id: 'n24', title: '人均500玩转大理3天2晚攻略', primary: 4, tags: ['旅行', '大理', '攻略'], q: 0.72, cover: 0.74, coverStyle: '实拍', pop: 0.80, hours: 5, author: { name: '背包看世界', followers: 90000 } }),
  makeNote({ id: 'n25', title: '酒店开盲盒式踩坑实录', primary: 4, tags: ['旅行', '酒店', '避坑'], q: 0.55, cover: 0.58, coverStyle: '拼贴', pop: 0.50, hours: 200, author: { name: '出差狂魔', followers: 10000 } }),
  makeNote({ id: 'n26', title: '一个人旅行安全清单（女生必看）', primary: 4, secondary: 7, tags: ['旅行', '安全', '女生'], q: 0.70, cover: 0.85, coverStyle: '大字', pop: 0.68, hours: 45, author: { name: '独自出发', followers: 30000 } }),
  makeNote({ id: 'n27', title: '周末48小时短途游路线规划模板', primary: 4, tags: ['旅行', '周末', '路线'], q: 0.62, cover: 0.84, coverStyle: '大字', pop: 0.35, hours: 300, author: { name: '周末出走', followers: 5000 } }),
  makeNote({ id: 'n28', title: '帕梅拉跟练一个月，身体变化记录', primary: 5, tags: ['健身', '帕梅拉'], q: 0.70, cover: 0.90, coverStyle: '对比图', pop: 0.75, hours: 15, author: { name: '练出马甲线', followers: 70000 } }),
  makeNote({ id: 'n29', title: '减肥平台期怎么办？三个科学方法', primary: 5, tags: ['减肥', '平台期'], q: 0.72, cover: 0.42, coverStyle: '纯文字', pop: 0.55, hours: 80, author: { name: '减脂教练阿伦', followers: 40000 } }),
  makeNote({ id: 'n30', title: '办公室久坐党5分钟拉伸', primary: 5, secondary: 2, tags: ['健身', '拉伸', '久坐'], q: 0.60, cover: 0.68, coverStyle: '实拍', pop: 0.40, hours: 160, author: { name: '打工人健康局', followers: 20000 } }),
  makeNote({ id: 'n31', title: '新手健身房器械扫盲', primary: 5, tags: ['健身', '器械', '新手'], q: 0.62, cover: 0.85, coverStyle: '大字', pop: 0.30, hours: 260, author: { name: '铁馆小助手', followers: 6000 } }),
  makeNote({ id: 'n32', title: 'iPhone隐藏功能大合集（第3期）', primary: 6, tags: ['数码', 'iPhone'], q: 0.68, cover: 0.86, coverStyle: '大字', pop: 0.85, hours: 3, author: { name: '数码锦鲤', followers: 150000 } }),
  makeNote({ id: 'n33', title: '学生党手机选购避坑指南', primary: 6, secondary: 7, tags: ['数码', '手机', '学生党'], q: 0.65, cover: 0.84, coverStyle: '大字', pop: 0.50, hours: 120, author: { name: '参数党阿凯', followers: 30000 } }),
  makeNote({ id: 'n34', title: '让工作效率翻倍的5个App', primary: 6, secondary: 2, tags: ['数码', '效率工具', '职场'], q: 0.72, cover: 0.44, coverStyle: '纯文字', pop: 0.78, hours: 9, author: { name: '效率研究所', followers: 100000 } }),
  makeNote({ id: 'n35', title: '相机新手：参数到底怎么调', primary: 6, tags: ['数码', '相机', '摄影'], q: 0.70, cover: 0.74, coverStyle: '实拍', pop: 0.35, hours: 400, author: { name: '快门手记', followers: 20000 } }),
  makeNote({ id: 'n36', title: '恋爱脑自救手册：三个清醒信号', primary: 7, tags: ['情感', '恋爱'], q: 0.70, cover: 0.44, coverStyle: '纯文字', pop: 0.70, hours: 30, author: { name: '清醒恋爱脑', followers: 60000 } }),
  makeNote({ id: 'n37', title: '考研英语80分复习计划（完整版）', primary: 7, secondary: 2, tags: ['学习', '考研', '英语'], q: 0.80, cover: 0.87, coverStyle: '大字', pop: 0.65, hours: 70, author: { name: '考研上岸姐', followers: 50000 } }),
  makeNote({ id: 'n38', title: '每天5分钟背单词的野路子', primary: 7, tags: ['学习', '背单词'], q: 0.60, cover: 0.84, coverStyle: '大字', pop: 0.40, hours: 240, author: { name: '英语小野', followers: 15000 } }),
  makeNote({ id: 'n39', title: '新手爸妈囤货红黑榜（避雷版）', primary: 7, tags: ['母婴', '囤货'], q: 0.66, cover: 0.60, coverStyle: '拼贴', pop: 0.50, hours: 90, author: { name: '新手奶爸', followers: 25000 } }),
  makeNote({ id: 'n40', title: '独居女生安全感改造清单', primary: 7, secondary: 3, tags: ['情感', '独居', '安全'], q: 0.64, cover: 0.88, coverStyle: '对比图', pop: 0.58, hours: 55, author: { name: '独居研究所', followers: 35000 } }),
];

const NOTE_BY_ID = {};
NOTES.forEach(n => { NOTE_BY_ID[n.id] = n; });

function makeUserVec(w) {
  const s = Math.sqrt(w.reduce((a, b) => a + b * b, 0)) || 1;
  return w.map(x => x / s);
}

// ------------------- 用户画像 -------------------
const PERSONAS = [
  {
    id: 'beauty', name: '美妆爱好者',
    vec: makeUserVec([0.85, 0.50, 0.10, 0.15, 0.10, 0.10, 0.05, 0.10]),
    history: ['n01', 'n02', 'n03'],
    keywords: ['美妆', '护肤', '口红', '妆容', '化妆', '素颜'],
  },
  {
    id: 'work', name: '职场新人',
    vec: makeUserVec([0.10, 0.25, 0.90, 0.10, 0.05, 0.10, 0.15, 0.30]),
    history: ['n12', 'n13', 'n14'],
    keywords: ['职场', '简历', '跳槽', '面试', '实习', '副业'],
  },
  {
    id: 'food', name: '美食控',
    vec: makeUserVec([0.10, 0.10, 0.15, 0.90, 0.20, 0.10, 0.05, 0.20]),
    history: ['n18', 'n19', 'n20'],
    keywords: ['美食', '快手菜', '空气炸锅', '食谱', '便当'],
  },
  {
    id: 'travel', name: '旅行爱好者',
    vec: makeUserVec([0.15, 0.30, 0.10, 0.25, 0.85, 0.20, 0.10, 0.15]),
    history: ['n24', 'n26', 'n27'],
    keywords: ['旅行', '攻略', '大理', '路线', '民宿'],
  },
  {
    id: 'fit', name: '健身自律党',
    vec: makeUserVec([0.10, 0.20, 0.15, 0.20, 0.10, 0.85, 0.05, 0.10]),
    history: ['n28', 'n29', 'n30'],
    keywords: ['健身', '减肥', '拉伸', '训练', '马甲线', '帕梅拉'],
  },
  {
    id: 'tech', name: '数码科技宅',
    vec: makeUserVec([0.05, 0.10, 0.30, 0.10, 0.05, 0.05, 0.90, 0.20]),
    history: ['n32', 'n33', 'n34'],
    keywords: ['数码', '手机', 'App', '效率', '相机', 'iPhone'],
  },
  {
    id: 'student', name: '备考学生党',
    vec: makeUserVec([0.15, 0.20, 0.35, 0.25, 0.10, 0.10, 0.25, 0.80]),
    history: ['n37', 'n38', 'n17'],
    keywords: ['考研', '学习', '背单词', '复习', '效率'],
  },
];

// 万粉显示
function fmtW(n) {
  if (n >= 10000) return (n / 10000).toFixed(1) + 'w';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(Math.round(n));
}
