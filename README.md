# 小红书推荐系统 Pipeline 模拟器

交互式教学模拟器，直观展示小红书类内容平台的推荐机制。前端零依赖，后端算法层由 **Python + numpy** 实现。

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
```

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
