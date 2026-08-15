# -*- coding: utf-8 -*-
"""
daily_update.py — 每日自动更新：随机抖动采集 + 全部分析 + 报告刷新

防固定行为设计（降低反爬警觉）：
  1. 时间抖动：正式采集前随机延迟 0-45 分钟
  2. 参数抖动：每次采集量与间隔在基线附近随机浮动
  3. 461 风控自动处置：清理会话目录并标记需人工重扫，不硬刚

用法：
  python daily_update.py [--now]     # --now 跳过随机延迟（测试用）
"""
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
RT = PROJECT / "realtime_analysis"
CONFIG_FILE = HERE / "config.json"
LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    with open(LOG_DIR / "daily.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_media_dir():
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            md = cfg.get("media_dir", "")
            if md and (Path(md) / "config" / "base_config.py").exists():
                return md
        except ValueError:
            pass
    for cand in (PROJECT.parent / "MediaCrawler", PROJECT / "MediaCrawler",
                 Path("E:/数据分析/MediaCrawler")):
        if cand.exists():
            return str(cand)
    return None


def venv_python(media_dir):
    return str(Path(media_dir) / ".venv" / "Scripts" / "python.exe")


def patch_crawl_params(media_dir, base_notes=60):
    """随机抖动采集参数：模拟非固定行为"""
    cfg_path = Path(media_dir) / "config" / "base_config.py"
    src = cfg_path.read_text(encoding="utf-8")
    max_notes = max(30, base_notes + random.randint(-10, 10))
    sleep_sec = random.choice([4, 5, 6])
    src = re.sub(r"^CRAWLER_MAX_NOTES_COUNT = \d+", "CRAWLER_MAX_NOTES_COUNT = %d" % max_notes, src, flags=re.M)
    src = re.sub(r"^CRAWLER_MAX_SLEEP_SEC = \d+", "CRAWLER_MAX_SLEEP_SEC = %d" % sleep_sec, src, flags=re.M)
    cfg_path.write_text(src, encoding="utf-8")
    return max_notes, sleep_sec


def count_notes(media_dir):
    dd = Path(media_dir) / "data" / "xhs" / "jsonl"
    total = 0
    if dd.exists():
        for f in dd.glob("search_contents_*.jsonl"):
            try:
                total += sum(1 for _ in open(f, encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return total


def process_alive(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10).stdout
        return "python" in out.lower()
    except Exception:
        return True


def handle_risk_control(log_text, media_dir):
    """检测 461 风控：清理会话 + 标记需人工扫码"""
    if re.search(r"461|CAPTCHA|Verifytype", log_text):
        log("检测到 461 验证码风控，自动清理浏览器会话")
        bd = Path(media_dir) / "browser_data"
        if bd.exists():
            subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(bd)], timeout=60)
        (HERE / "state_needs_login.txt").write_text(
            datetime.now().strftime("%Y-%m-%d %H:%M") + " 461风控，请手动启动助手扫码登录后重试", encoding="utf-8")
        return True
    return False


def run_crawl(media_dir, vpy, now=False):
    """启动采集并监控直到结束/风控/停滞"""
    if not now:
        delay = random.uniform(0, 45 * 60)
        log("随机延迟 %.0f 分钟后开始采集" % (delay / 60))
        time.sleep(delay)

    max_notes, sleep_sec = patch_crawl_params(media_dir)
    log("本次采集参数：每词 %d 条 · 间隔 %d 秒" % (max_notes, sleep_sec))

    log_file = LOG_DIR / "daily_crawl.log"
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("")
    proc = subprocess.Popen(
        [vpy, "main.py"], cwd=media_dir,
        stdout=open(log_file, "a", encoding="utf-8", errors="ignore"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008,
    )
    log("采集进程已启动 pid=%d（浏览器弹出后请扫码，每日首次需人工登录）" % proc.pid)

    last = count_notes(media_dir)
    stall_min = 0
    while True:
        time.sleep(60)
        if not process_alive(proc.pid):
            log("采集进程已退出")
            break
        tail = ""
        try:
            tail = log_file.read_text(encoding="utf-8", errors="ignore")[-4000:]
        except OSError:
            pass
        if handle_risk_control(tail, media_dir):
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            return False
        n = count_notes(media_dir)
        if n != last:
            stall_min = 0
            last = n
            log("采集中… 累计 %d 条笔记" % n)
        else:
            stall_min += 1
            if stall_min >= 15:
                log("15 分钟无增长，判定停滞，结束本次采集")
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
                break
    return True


def run_analysis(media_dir, vpy):
    log("开始分析（约 1-2 分钟）…")
    my_kw = "英文学习,AI"
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if cfg.get("my_keywords"):
                my_kw = cfg["my_keywords"]
        except ValueError:
            pass
    dd = str(Path(media_dir) / "data" / "xhs" / "jsonl")
    cmds = [
        [vpy, str(HERE / "analysis_runner.py"), "--data-dir", dd,
         "--out", str(HERE / "results.json"), "--report-dir", str(RT / "report")],
        [vpy, str(RT / "analyze_compare.py"), "--data-dir", dd,
         "--my-keywords", my_kw, "--out-dir", str(RT / "report")],
    ]
    for cmd in cmds:
        log("运行: %s" % Path(cmd[1]).name)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            if r.returncode != 0:
                log("分析失败: %s" % (r.stderr or r.stdout)[-500:])
                return False
        except subprocess.TimeoutExpired:
            log("分析超时")
            return False
    log("分析完成，报告已刷新")
    return True


def main():
    now = "--now" in sys.argv
    log("=" * 56)
    log("每日更新开始（%s）" % ("跳过随机延迟" if now else "含随机抖动"))
    media_dir = load_media_dir()
    if not media_dir:
        log("未找到 MediaCrawler，请先运行 setup.bat 或在助手高级设置中配置路径")
        return 2
    vpy = venv_python(media_dir)
    if not Path(vpy).exists():
        log("未找到 MediaCrawler 虚拟环境: %s" % vpy)
        return 2

    ok = run_crawl(media_dir, vpy, now=now)
    if not ok:
        log("采集未正常完成（可能风控），跳过分析；解决后重新运行")
        return 2

    if not run_analysis(media_dir, vpy):
        return 2

    log("每日更新完成 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
