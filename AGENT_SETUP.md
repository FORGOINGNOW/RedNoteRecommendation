# 给 AI Agent 的安装指令（AI AGENT SETUP INSTRUCTIONS）

> 把本文件内容粘贴给任意 AI Agent（如 opencode / Claude / Gemini CLI），
> 让它在这台 Windows 机器上自动安装并启动「小红书赛道筛选 AI 助手」。

## 任务

在 Windows 上安装并启动本项目（小红书赛道筛选 AI 助手），并跑通完整流程。

## 步骤

1. 克隆仓库：
   ```
   git clone https://github.com/FORGOINGNOW/RedNoteRecommendation.git
   ```
   （若克隆失败或没有 git，改用 `gh repo clone FORGOINGNOW/RedNoteRecommendation`）

2. 检查 Python：运行 `python --version`，需要 3.10+。
   没有则提示用户安装 https://www.python.org/downloads/ （勾选 Add to PATH）。

3. 下载采集器到仓库的同级目录：
   ```
   git clone --depth 1 https://github.com/NanmiCoder/MediaCrawler.git ../MediaCrawler
   ```
   若该目录已存在则跳过。

4. 创建虚拟环境并安装依赖：
   ```
   python -m venv ../MediaCrawler/.venv
   ../MediaCrawler/.venv/Scripts/python.exe -m pip install -r ../MediaCrawler/requirements.txt
   ```

5. 启动助手服务（后台运行）：
   ```
   cd assistant
   python server.py
   ```
   服务地址 http://localhost:8787，浏览器自动打开。

6. 通过 HTTP API 配置关键词并启动采集：
   ```
   POST http://localhost:8787/api/config
   {"keywords": "<用户想要的赛道关键词，逗号分隔>", "max_notes": 100, "media_dir": "<MediaCrawler绝对路径>", "llm": {}}

   POST http://localhost:8787/api/crawl/start
   ```

7. **人工步骤（Agent 无法代做）**：采集启动后会自动打开浏览器并显示二维码，
   必须请用户用手机小红书 App 在 120 秒内扫码登录，如出现滑块验证请用户手动完成。

8. 轮询采集进度直到结束：
   ```
   GET http://localhost:8787/api/crawl/status
   ```
   返回 {running, notes, comments, log_tail}；running=false 即结束。

9. 运行分析并生成建议：
   ```
   POST http://localhost:8787/api/analyze      # 约 30-60 秒，返回全部分析结果
   POST http://localhost:8787/api/advice      # {"use_llm": false}，返回入场建议+运营方案
   ```

10. 向用户汇报：推荐定位、品类评分、KPI 建议，并告知页面地址 http://localhost:8787。

## API 速查

| 端点 | 方法 | 说明 |
|---|---|---|
| /api/env | GET | 环境检测（MediaCrawler 路径/数据量/报告状态） |
| /api/config | POST | 保存配置并同步到 MediaCrawler |
| /api/crawl/start | POST | 启动采集（弹出扫码） |
| /api/crawl/status | GET | 进度（笔记数/评论数/日志） |
| /api/crawl/stop | POST | 停止采集 |
| /api/analyze | POST | 一键分析 → results.json + HTML 报告 |
| /api/results | GET | 已缓存的分析结果 |
| /api/advice | POST | 生成入场建议+运营方案 |
| /reports/report.html | GET | 流量分布报告 |
| /reports/report_fit.html | GET | 算法契合度报告 |

## 注意

- 只能 Windows（采集与脚本基于 Windows 路径与 bat）
- 采集频率已在 MediaCrawler 配置中设为 5 秒/条，不要调快
- 若采集报 461 CAPTCHA：停止后删除 ../MediaCrawler/browser_data 目录，重新启动并请用户重新扫码
- 数据仅用于个人学习分析，遵守平台条款
