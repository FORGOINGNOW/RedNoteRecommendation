# -*- coding: utf-8 -*-
"""
assistant/server.py — 小红书赛道筛选 AI 助手 · 后端编排（纯标准库，零额外依赖）

  五步流程：
    1. 赛道分析   → 配置采集关键词与规模（写入 MediaCrawler 配置）
    2. 数据采集   → 后台启动 MediaCrawler 采集 + 进度监控
    3. 标签数据分析 → 调用 venv 运行分析模块，产出 results.json + HTML 报告
    4. 入场建议   → 规则引擎（可选大模型润色）
    5. 运营方案   → 30 天三阶段方案 + KPI + 风险提示
"""
import json
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
RT = PROJECT / "realtime_analysis"
CONFIG_FILE = HERE / "config.json"
STATE_FILE = HERE / "state.json"
RESULTS_FILE = HERE / "results.json"
LOG_DIR = HERE / "logs"
PORT = 8787

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
}


def detect_media_dir(cfg_media):
    """自动探测 MediaCrawler 目录：配置值 → 项目同级 → 项目内 → 常见路径"""
    candidates = [
        cfg_media,
        str(PROJECT.parent / "MediaCrawler"),
        str(PROJECT / "MediaCrawler"),
        "E:/数据分析/MediaCrawler",
        "E:/MediaCrawler",
        "C:/MediaCrawler",
    ]
    for c in candidates:
        if c and Path(c).exists() and (Path(c) / "config" / "base_config.py").exists():
            return str(Path(c))
    return cfg_media


def load_config():
    default = {
        "media_dir": "",
        "keywords": "AI,Agent,人工智能,英文学习,职场转型,大模型应用",
        "my_keywords": "英文学习,AI",
        "max_notes": 100,
        "llm": {"api_key": "", "base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    }
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k, v in default.items():
                cfg.setdefault(k, v)
            cfg.setdefault("llm", default["llm"])
        except ValueError:
            cfg = dict(default)
    else:
        cfg = dict(default)
    resolved = detect_media_dir(cfg.get("media_dir", ""))
    if resolved != cfg.get("media_dir"):
        cfg["media_dir"] = resolved
        save_config(cfg)
    return cfg


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def venv_python(cfg):
    return str(Path(cfg["media_dir"]) / ".venv" / "Scripts" / "python.exe")


def data_dir(cfg):
    return str(Path(cfg["media_dir"]) / "data" / "xhs" / "jsonl")


def report_dir():
    return str(RT / "report")


def patch_media_config(cfg):
    """把关键词与采集量写入 MediaCrawler 的 base_config.py"""
    p = Path(cfg["media_dir"]) / "config" / "base_config.py"
    if not p.exists():
        raise FileNotFoundError("未找到 MediaCrawler 配置文件: " + str(p))
    src = p.read_text(encoding="utf-8")
    src, n1 = re.subn(r'^KEYWORDS = ".*"', 'KEYWORDS = "%s"' % cfg["keywords"], src, flags=re.M)
    src, n2 = re.subn(r'^CRAWLER_MAX_NOTES_COUNT = \d+',
                      'CRAWLER_MAX_NOTES_COUNT = %d' % int(cfg["max_notes"]), src, flags=re.M)
    p.write_text(src, encoding="utf-8")
    return n1, n2


def count_jsonl_lines(path_pattern):
    total = 0
    for f in Path(path_pattern).parent.glob(Path(path_pattern).name):
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                total += sum(1 for _ in fh)
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


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"pid": None, "running": False, "started_at": None}


def save_state(st):
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def env_info(cfg):
    media = Path(cfg["media_dir"])
    vp = Path(venv_python(cfg))
    dd = Path(data_dir(cfg))
    notes = count_jsonl_lines(str(dd / "search_contents_*.jsonl"))
    comments = count_jsonl_lines(str(dd / "search_comments_*.jsonl"))
    return {
        "media_dir_exists": media.exists(),
        "venv_ok": vp.exists(),
        "media_dir": cfg["media_dir"],
        "data_dir": str(dd),
        "notes": notes,
        "comments": comments,
        "results_exists": RESULTS_FILE.exists(),
        "config": {"keywords": cfg["keywords"], "my_keywords": cfg.get("my_keywords", "英文学习,AI"),
                   "max_notes": cfg["max_notes"], "llm_key_set": bool(cfg["llm"].get("api_key"))},
    }


def read_log_tail(path, n=12):
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


def json_response(handler, obj, code=200):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def handle_api(handler, method, path, body):
    cfg = load_config()

    if method == "GET" and path == "/api/env":
        return json_response(handler, env_info(cfg))

    if method == "POST" and path == "/api/config":
        cfg["keywords"] = str(body.get("keywords", cfg["keywords"])).strip() or cfg["keywords"]
        cfg["my_keywords"] = str(body.get("my_keywords", cfg.get("my_keywords", "英文学习,AI"))).strip() or cfg["my_keywords"]
        cfg["max_notes"] = int(body.get("max_notes", cfg["max_notes"]))
        if body.get("media_dir"):
            cfg["media_dir"] = str(body["media_dir"]).strip()
        llm = body.get("llm") or {}
        cfg["llm"]["api_key"] = str(llm.get("api_key", cfg["llm"].get("api_key", ""))).strip()
        cfg["llm"]["base_url"] = str(llm.get("base_url", cfg["llm"].get("base_url", "https://api.deepseek.com"))).strip()
        cfg["llm"]["model"] = str(llm.get("model", cfg["llm"].get("model", "deepseek-chat"))).strip()
        save_config(cfg)
        try:
            n1, n2 = patch_media_config(cfg)
            patched = "已同步 MediaCrawler 配置（关键词=%d 处，采集量=%d 处）" % (n1, n2)
        except Exception as e:
            patched = "MediaCrawler 配置同步失败: %s" % e
        return json_response(handler, {"ok": True, "patched": patched, "config": cfg})

    if method == "POST" and path == "/api/crawl/start":
        vp = venv_python(cfg)
        if not Path(vp).exists():
            return json_response(handler, {"ok": False, "error": "未找到 MediaCrawler 虚拟环境，请检查路径: " + vp}, 400)
        st = load_state()
        if st.get("pid") and process_alive(st["pid"]):
            return json_response(handler, {"ok": True, "already_running": True, **st})
        LOG_DIR.mkdir(exist_ok=True)
        log_f = LOG_DIR / "crawl.log"
        with open(log_f, "w", encoding="utf-8") as f:
            f.write("")
        proc = subprocess.Popen(
            [vp, "main.py"],
            cwd=cfg["media_dir"],
            stdout=open(log_f, "a", encoding="utf-8", errors="ignore"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008,
        )
        st = {"pid": proc.pid, "running": True, "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        save_state(st)
        return json_response(handler, {"ok": True, "already_running": False, **st})

    if method == "POST" and path == "/api/crawl/stop":
        st = load_state()
        if st.get("pid"):
            subprocess.run(["taskkill", "/PID", str(st["pid"]), "/T", "/F"],
                           capture_output=True, timeout=15)
        save_state({"pid": None, "running": False, "started_at": None})
        return json_response(handler, {"ok": True})

    if method == "GET" and path == "/api/crawl/status":
        st = load_state()
        alive = process_alive(st.get("pid"))
        st["running"] = alive
        save_state(st)
        notes = count_jsonl_lines(str(Path(data_dir(cfg)) / "search_contents_*.jsonl"))
        comments = count_jsonl_lines(str(Path(data_dir(cfg)) / "search_comments_*.jsonl"))
        return json_response(handler, {
            **st, "notes": notes, "comments": comments,
            "log_tail": read_log_tail(LOG_DIR / "crawl.log"),
        })

    if method == "POST" and path == "/api/analyze":
        vp = venv_python(cfg)
        if not Path(vp).exists():
            return json_response(handler, {"ok": False, "error": "未找到 MediaCrawler 虚拟环境"}, 400)
        runner = str(HERE / "analysis_runner.py")
        cmd = [vp, runner, "--data-dir", data_dir(cfg), "--out", str(RESULTS_FILE),
               "--report-dir", report_dir()]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=600, cwd=str(HERE))
        except subprocess.TimeoutExpired:
            return json_response(handler, {"ok": False, "error": "分析超时（超过10分钟）"}, 500)
        if proc.returncode != 0 or not RESULTS_FILE.exists():
            return json_response(handler, {"ok": False, "error": "分析失败",
                                           "log": (proc.stdout or "")[-800:] + "\n" + (proc.stderr or "")[-800:]}, 500)
        results = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        return json_response(handler, {"ok": True, "results": results})

    if method == "GET" and path == "/api/results":
        if RESULTS_FILE.exists():
            return json_response(handler, json.loads(RESULTS_FILE.read_text(encoding="utf-8")))
        return json_response(handler, {"error": "尚未分析"}, 404)

    if method == "POST" and path == "/api/advice":
        if not RESULTS_FILE.exists():
            return json_response(handler, {"ok": False, "error": "请先完成数据分析"}, 400)
        results = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        use_llm = bool(body.get("use_llm"))
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import advisor
        advice = advisor.generate(
            results,
            api_key=cfg["llm"].get("api_key") or None,
            base_url=cfg["llm"].get("base_url") or "https://api.deepseek.com",
            model=cfg["llm"].get("model") or "deepseek-chat",
            use_llm=use_llm,
        )
        return json_response(handler, {"ok": True, "advice": advice})

    return json_response(handler, {"error": "not found"}, 404)


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return handle_api(self, "GET", parsed.path, None)
        return self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except (ValueError, UnicodeDecodeError):
                return json_response(self, {"error": "bad json"}, 400)
            return handle_api(self, "POST", parsed.path, body)
        return json_response(self, {"error": "not found"}, 404)

    def serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        # 报告文件映射
        if path.startswith("/reports/"):
            name = Path(path).name
            base = Path(report_dir())
            if name in ("report.html", "report_fit.html", "report_lifecycle.html",
                        "report_compare.html", "report_index.html", "report_search.html"):
                return self._send_file(base / name, name)
        # 助手前端静态文件
        base = HERE / "static"
        file_path = (base / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(base)) or not file_path.is_file():
            self.send_error(404)
            return
        return self._send_file(file_path, file_path.name)

    def _send_file(self, file_path, name):
        ext = Path(name).suffix.lower()
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


def open_browser():
    threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d" % PORT)).start()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("=" * 60)
    print("  小红书赛道筛选 AI 助手已启动")
    print("  地址: http://localhost:%d" % PORT)
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    open_browser()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n助手已停止")
