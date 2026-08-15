# 小红书推荐系统 Pipeline 模拟器

交互式教学模拟器，直观展示小红书类内容平台的推荐机制。前端零依赖，后端算法层由 **Python + numpy** 实现。

## 让别人也能用：部署指南

### 前置条件（对方机器）

- Windows 10/11
- Python 3.10+（安装时勾选 Add to PATH）
- git（可选，setup 脚本需要它自动下载采集器；没有则手动下载 MediaCrawler 解压）
- 一个小红书账号（采集时手机扫码登录）

### 三步启动

1. 把整个项目文件夹（RedNoteRecommendation）拷给对方，或让对方 clone 本仓库
2. **双击 `setup.bat`**：自动完成 下载 MediaCrawler → 建虚拟环境 → 装依赖（首次约 5-10 分钟），然后自动打开助手页面
3. 页面里按五步走：填赛道词 → 启动采集 → 扫码登录 → 一键分析 → 生成建议和方案

### 各步骤不用装、不用配

- MediaCrawler 路径自动探测（项目同级/项目内/常见路径），找不到时在页面「高级设置」里手动填一次即可
- 大模型 API Key 可选：不填用内置规则引擎生成建议，填了 DeepSeek Key 则 AI 润色
- 日常使用只需双击 `assistant/start_assistant.bat`（已装过环境之后）

### 方式三：让 AI Agent 帮你装

仓库根目录的 `AGENT_SETUP.md` 是写给 AI Agent 的安装指令：把它粘贴给任意 AI Agent（opencode/Claude 等），agent 会自动完成 克隆 → 装环境 → 启动 → 配置 → 采集 → 分析 全流程，唯一需要人工的一步是扫码登录（agent 无法代扫）。Agent 也可以通过助手内置的 REST API 全程驱动（见该文件末尾的 API 速查表）。

### 注意事项

- setup 脚本与采集功能目前只支持 Windows
- 采集请控制频率（默认每 5 秒一条），数据仅用于个人学习分析，遵守平台条款

## 反爬应对经验（实战总结）

小红书风控是分级递进的，本项目采集时遇到过的完整处置流程：

| 现象 | 含义 | 处置 |
|---|---|---|
| 详情页 JSONDecodeError / RetryError | 详情接口被限（第一级） | 自动兜底用搜索列表数据，不影响采集 |
| 搜索接口 RetryError + 日志出现 `461 CAPTCHA`（verifytype 216） | 会话被标记（第二级） | 停止采集 → 删除 `MediaCrawler/browser_data` 目录 → 重新启动并扫码登录（新会话即解封）|
| 连续触发 | 频率太高 | 放宽 `CRAWLER_MAX_SLEEP_SEC` 到 5 秒，单日采集总量控制在 500 条内 |

经验要点：
1. **重登解封有效**：461 绑定的是会话指纹，删 browser_data 重扫码即可，不必换 IP
2. **避免固定时间采集**：每日定时任务内置 0-45 分钟随机延迟 + 采集量/间隔随机抖动（见下节）
3. **详情接口先封**：详情页接口比搜索接口敏感，能靠搜索列表数据就不用详情接口

## 每日自动更新数据

1. 双击 `assistant/setup_schedule.bat` 注册 Windows 计划任务（每天 20:30 触发）
2. 任务内部先随机延迟 0-45 分钟再开跑，并随机抖动采集量与间隔（模拟真人行为，降低风控）
3. 自动完成：采集 → 全部分析（流量/契合度/生命周期/选题对比）→ 刷新报告
4. 若遇 461 风控：自动清理会话并标记「需重新扫码」，下次运行前手动扫码登录即可
5. 日志：`assistant/logs/daily.log`；手动立即跑一次：`assistant/daily_update.bat`

## 三个入口

| 入口 | 说明 |
|---|---|
| **赛道筛选 AI 助手（推荐新手）** | 双击 `assistant/start_assistant.bat` → 五步向导：赛道分析 → 数据采集 → 标签数据分析 → 入场建议 → 运营方案，全程可视化操作 |
| 推荐链路模拟器 | 双击 `start.bat`（或 `index.html`），可视化「召回→粗排→精排→重排」与流量池晋级 |
| 真实数据分析 | `realtime_analysis/run_analysis.bat` 生成流量分布 + 算法契合度报告 |

## 赛道筛选 AI 助手（assistant/）

面向零基础用户的五步向导：

1. **赛道分析**：填写想做的赛道关键词，配置采集规模（可选填 DeepSeek API Key 让建议更个性化）
2. **数据采集**：一键启动开源采集器 MediaCrawler，扫码登录后自动采集，实时进度条
3. **标签数据分析**：自动完成 9 类内容打标、流量分布统计、算法契合度回归、流量池画像
4. **入场建议**：规则引擎给每个品类打分（蓝海/红海判断）+ 推荐定位 + 对标笔记（可选大模型润色）
5. **运营方案**：30 天三阶段计划、发布节奏、标题公式、KPI 与风险提示

依赖：Python（标准库即可运行助手服务）+ MediaCrawler 及其 venv（pandas/matplotlib/jieba，仅分析时使用）。

## 运行方式

### 方式一：完整模式（推荐，Python 算法引擎）

双击 `start.bat`（或命令行运行 `python server.py`），浏览器将自动打开 <http://localhost:8765>。

- 仅依赖 numpy：`pip install numpy`（已安装则无需任何操作）
- 页面顶部徽章显示「引擎：Python·numpy 后端」

### 方式二：纯前端模式（降级）

直接双击 `index.html`。页面会自动尝试连接后端；连不上时自动降级为浏览器内 JS 算法（算法逻辑与 Python 版一致），徽章会提示「JS 本地降级」。

## 三个 Tab

| Tab | 功能 |
|---|---|
| 推荐链路 | 完整走一遍「召回 → 粗排 → 精排 → 重排」，每层可展开看哪条笔记晋级/淘汰；可切换用户画像、拖动精排多目标权重观察排序变化；右侧是 PCA 降维后的 Embedding 空间散点图 |
| 流量池模拟 | 自己「创作」一篇笔记（标题/封面/质量/账号权重/赛道），观看它从审核 → 初始池 → 爆发池逐级分发或中途停止；支持连发 10 篇看爆款概率分布 |
| 机制速查 | 各算法模块与模拟器对应关系 |

## 架构

```
index.html ──fetch──► server.py (HTTP, 零依赖 stdlib)
                          │
                          ▼
                     algorithms.py (numpy 实现)
                       ├─ 召回：双塔余弦 / Item-CF / 关键词 / 热度
                       ├─ 粗排：线性加权
                       ├─ 精排：多任务模型（向量化 sigmoid）
                       ├─ 重排：多样性打散 / 新鲜度
                       ├─ PCA：协方差矩阵特征分解 (np.linalg.eigh)
                       └─ 分发：五级流量池晋级（CES 门槛）
```

后端不可用时，前端自动降级到 `pipeline.js` / `simulator.js` / `viz.js` 中的本地 JS 实现。

## API

| 端点 | 说明 |
|---|---|
| `GET /api/ping` | 引擎探测 |
| `GET /api/notes` | 笔记库元数据（40 条） |
| `GET /api/personas` | 7 个用户画像 |
| `POST /api/recommend` | `{persona, weights:{ctr,comp,inter,follow}, seed}` → 完整链路结果 + PCA 投影 |
| `POST /api/simulate` | `{title, titleScore, coverScore, quality, authorPower, trackFav}` → 审核+逐池分发结果 |
| `POST /api/simulate_batch` | 同上 → 连发 10 篇分布 |

## 文件结构

```
index.html     界面结构（三个 Tab）
style.css      样式
data.js        前端元数据与 JS 降级引擎的数据集
pipeline.js    本地 JS 降级：推荐链路算法
viz.js         JS 降级：PCA + SVG 散点图
simulator.js   流量池模拟（渲染层 + JS 降级计算层）
app.js         界面渲染与交互编排（双引擎调度）
algorithms.py  Python 底层算法（numpy，核心）
server.py      HTTP 服务与 API 路由
start.bat      一键启动
realtime_analysis/   真实数据采集分析模块（依赖 MediaCrawler）
assistant/           赛道筛选 AI 助手（五步向导，新手入口）
```

## 真实流量分析（realtime_analysis）

配合开源爬虫 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 采集小红书真实笔记数据，一键生成流量分布报告：

1. 在 MediaCrawler 的 `config/base_config.py` 配置 `KEYWORDS`
2. 运行 MediaCrawler 采集（输出 jsonl）
3. 双击 `realtime_analysis/run_analysis.bat` 生成报告

输出：关键词流量分布 / 互动幂律分布与头部集中度 / 图文vs视频 / 发布时间 / 收藏赞比 / 评论热词词云 / 爆款榜 Top20（详见 realtime_analysis/README.md）。数据仅用于个人学习分析，请控制采集频率。

## 与真实系统的对应

| 模拟器 | 真实系统 |
|---|---|
| 双塔向量召回（余弦相似度） | DSSM 双塔 + Faiss/HNSW 向量检索 |
| Item-CF（标签共现） | 协同过滤召回 |
| 关键词召回 | 标签倒排索引 + 搜索页 SEO |
| 精排多任务（CTR/完读/互动/关注 加权） | MMoE / PLE 多目标模型 |
| 重排多样性打散 | MMR 重排规则 |
| 流量池晋级（CES 门槛） | 多级流量池 + 实时特征反馈 |

## 免责声明

本项目的算法流程与参数均为教学性质简化模拟，非小红书官方算法实现。
