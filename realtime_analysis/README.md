# 小红书真实流量分析模块

用 MediaCrawler 采集真实笔记数据后，一键生成流量分布分析报告。

## 流程

1. 配置采集关键词：`E:\数据分析\MediaCrawler\config\base_config.py` 中的 `KEYWORDS`
2. 运行采集：`E:\数据分析\MediaCrawler\.venv\Scripts\python.exe main.py`（扫码登录后自动采集，输出 jsonl 到 `MediaCrawler\data\xhs\jsonl\`）
3. 运行分析：双击 `run_analysis.bat`（或手动执行 analyze_xhs.py）

## 输出

| 产物 | 说明 |
|---|---|
| `report/report.html` | 自包含 HTML 报告（含图表） |
| `report/notes.csv` | 清洗后的笔记明细（UTF-8 BOM，可直接用 Excel 打开） |
| `report/chart_*.png` | 各分析图表 |

## 分析内容

- 关键词流量分布（笔记数/总互动/中位互动/爆款数）
- 互动量幂律分布与 Top10% 头部集中度
- 图文 vs 视频占比及互动对比
- 发布时间分布（24 小时 × 星期）
- 收藏/点赞比（干货指标）
- 评论热词 Top30 + 词云
- 互动量爆款榜 Top20（含原文链接）

## 说明

- 数据仅用于个人学习分析，请控制采集频率，遵守平台条款
- 依赖 MediaCrawler 的 venv（pandas/matplotlib/jieba/wordcloud）
