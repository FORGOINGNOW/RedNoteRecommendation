# -*- coding: utf-8 -*-
"""
server.py — 零依赖 HTTP 服务（仅需 numpy）
  静态文件：/index.html /data.js /app.js ...
  JSON API：
    GET  /api/ping            引擎探测
    GET  /api/notes           笔记库元数据
    GET  /api/personas        用户画像
    POST /api/recommend       运行完整推荐链路
    POST /api/simulate        单次流量池分发模拟
    POST /api/simulate_batch  批量模拟 10 次
"""
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import algorithms as algo

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8765

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.md': 'text/plain; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.json': 'application/json; charset=utf-8',
    '.bat': 'text/plain; charset=utf-8',
}


def json_response(handler, obj, code=200):
    body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(body)


def handle_api(handler, method, path, body):
    if method == 'GET' and path == '/api/ping':
        return json_response(handler, {'ok': True, 'engine': 'numpy ' + str(algo.np.__version__), 'notes': len(algo.NOTES)})
    if method == 'GET' and path == '/api/notes':
        notes = [{'id': n['id'], 'title': n['title'], 'tags': n['tags'], 'primary': n['primary'],
                  'coverStyle': n['coverStyle'], 'quality': n['quality'], 'pop': n['pop'],
                  'hoursAgo': n['hoursAgo'], 'author': n['author']} for n in algo.NOTES]
        return json_response(handler, {'notes': notes})
    if method == 'GET' and path == '/api/personas':
        return json_response(handler, {'personas': [
            {'id': p['id'], 'name': p['name'], 'vec': [float(x) for x in p['vec']],
             'history': p['history'], 'keywords': p['keywords']} for p in algo.PERSONAS]})
    if method == 'POST' and path == '/api/recommend':
        persona = algo.PERSONA_BY_ID.get(body.get('persona'))
        if persona is None:
            return json_response(handler, {'error': 'unknown persona'}, 400)
        w = body.get('weights', {})
        total = float(w.get('ctr', 2)) + float(w.get('comp', 2)) + float(w.get('inter', 3)) + float(w.get('follow', 3)) or 1.0
        weights = {
            'ctr': float(w.get('ctr', 2)) / total,
            'comp': float(w.get('comp', 2)) / total,
            'inter': float(w.get('inter', 3)) / total,
            'follow': float(w.get('follow', 3)) / total,
        }
        seed = int(body.get('seed', 1))
        result = algo.run_pipeline(persona, weights, seed)
        result['engine'] = 'numpy'
        return json_response(handler, result)
    if method == 'POST' and path == '/api/simulate':
        cfg = {
            'title': str(body.get('title', '')),
            'titleScore': float(body.get('titleScore', 0.5)),
            'coverScore': float(body.get('coverScore', 0.6)),
            'quality': float(body.get('quality', 0.5)),
            'authorPower': float(body.get('authorPower', 1.0)),
            'trackFav': float(body.get('trackFav', 0.0)),
        }
        return json_response(handler, algo.full_simulate(cfg))
    if method == 'POST' and path == '/api/simulate_batch':
        cfg = {
            'title': str(body.get('title', '')),
            'titleScore': float(body.get('titleScore', 0.5)),
            'coverScore': float(body.get('coverScore', 0.6)),
            'quality': float(body.get('quality', 0.5)),
            'authorPower': float(body.get('authorPower', 1.0)),
            'trackFav': float(body.get('trackFav', 0.0)),
        }
        return json_response(handler, algo.simulate_batch(cfg))
    return json_response(handler, {'error': 'not found'}, 404)


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return handle_api(self, 'GET', parsed.path, None)
        return self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            except (ValueError, UnicodeDecodeError):
                return json_response(self, {'error': 'bad json'}, 400)
            return handle_api(self, 'POST', parsed.path, body)
        return json_response(self, {'error': 'not found'}, 404)

    def serve_static(self, path):
        if path == '/' or path == '':
            path = '/index.html'
        file_path = os.path.normpath(os.path.join(ROOT, path.lstrip('/')))
        if not file_path.startswith(ROOT) or not os.path.isfile(file_path):
            self.send_error(404)
            return
        ext = os.path.splitext(file_path)[1].lower()
        with open(file_path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', MIME.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass  # 安静模式


def open_browser():
    threading.Timer(0.8, lambda: webbrowser.open('http://localhost:%d' % PORT)).start()


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print('=' * 52)
    print('  小红书推荐 Pipeline 模拟器 · Python 后端已启动')
    print('  地址: http://localhost:%d' % PORT)
    print('  引擎: numpy %s · 笔记库 %d 条 · 画像 %d 个' % (algo.np.__version__, len(algo.NOTES), len(algo.PERSONAS)))
    print('  按 Ctrl+C 停止服务')
    print('=' * 52)
    open_browser()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止')
