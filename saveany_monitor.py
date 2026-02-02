#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SaveAny-Bot Monitor v2.5
监控 SaveAny-Bot 的运行状态、资源占用和网络流量
支持配置文件编辑、Web 网页查看、日志捕获
新增：自定义日志位置、SOCKS5 代理设置、下载位置设置
v2.5: 修复配置文件格式，使用正确的 [telegram.proxy] 和 [[storages]] 格式
针对 Windows Server 2025 优化
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import psutil
import threading
import time
import os
import subprocess
import sys
import json
import socket
import webbrowser
import queue
import re
from datetime import datetime, timedelta
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# 全局变量用于 Web 服务
monitor_data = {
    "status": "未运行",
    "pid": "-",
    "uptime": "-",
    "cpu": 0,
    "memory": "0 MB",
    "memory_percent": 0,
    "threads": "-",
    "handles": "-",
    "download_speed": "0 KB/s",
    "upload_speed": "0 KB/s",
    "total_download": "0 MB",
    "total_upload": "0 MB",
    "sys_download": "0 KB/s",
    "sys_upload": "0 KB/s",
    "last_update": ""
}

# 全局变量
config_path = None
control_callback = None
recent_logs = deque(maxlen=500)

# 监控程序设置文件
SETTINGS_FILE = "monitor_settings.json"


class StoppableHTTPServer(HTTPServer):
    allow_reuse_address = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self.socket.settimeout(1.0)
    
    def serve_forever_stoppable(self):
        while not self._stop_event.is_set():
            try:
                self.handle_request()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue
    
    def stop(self):
        self._stop_event.set()
        try:
            self.socket.close()
        except Exception:
            pass


class MonitorHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    timeout = 10
    
    def log_message(self, format, *args):
        pass
    
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except Exception:
            pass
    
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            if parsed_path.path == '/' or parsed_path.path == '/index.html':
                self.send_html_page()
            elif parsed_path.path == '/api/status':
                self.send_json_status()
            elif parsed_path.path == '/api/config':
                self.send_config()
            elif parsed_path.path == '/api/logs':
                self.send_logs()
            else:
                self.send_error(404, "Not Found")
        except Exception:
            pass
    
    def do_POST(self):
        try:
            parsed_path = urlparse(self.path)
            if parsed_path.path == '/api/config':
                self.save_config()
            elif parsed_path.path == '/api/control':
                self.handle_control()
            else:
                self.send_error(404, "Not Found")
        except Exception:
            pass
    
    def send_html_page(self):
        html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SaveAny-Bot Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; color: #fff; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 30px; font-size: 2em; }
        .status-badge { display: inline-block; padding: 5px 15px; border-radius: 20px; font-size: 0.9em; margin-left: 10px; }
        .status-running { background: #00c853; }
        .status-stopped { background: #ff5252; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .card { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); border-radius: 15px; padding: 20px; border: 1px solid rgba(255,255,255,0.1); }
        .card h2 { font-size: 1.2em; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.2); }
        .stat-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .stat-row:last-child { border-bottom: none; }
        .stat-label { color: rgba(255,255,255,0.7); }
        .stat-value { font-weight: bold; font-size: 1.1em; }
        .progress-bar { width: 100%; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; margin-top: 5px; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #00c853, #69f0ae); border-radius: 4px; transition: width 0.3s ease; }
        .speed-value { font-size: 1.5em; font-weight: bold; color: #69f0ae; }
        .speed-value.upload { color: #64b5f6; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 15px; }
        .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9em; transition: all 0.3s ease; }
        .btn-primary { background: #2196f3; color: #fff; }
        .btn-success { background: #00c853; color: #fff; }
        .btn-danger { background: #ff5252; color: #fff; }
        .btn-warning { background: #ff9800; color: #fff; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.3); }
        .config-editor, .log-viewer { width: 100%; min-height: 300px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 15px; color: #fff; font-family: Consolas, Monaco, monospace; font-size: 13px; resize: vertical; }
        .log-viewer { min-height: 400px; white-space: pre-wrap; word-wrap: break-word; overflow-y: auto; }
        .update-time { text-align: center; color: rgba(255,255,255,0.5); font-size: 0.9em; margin-top: 20px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { padding: 10px 20px; background: rgba(255,255,255,0.1); border: none; border-radius: 8px; color: #fff; cursor: pointer; }
        .tab.active { background: #2196f3; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h1>SaveAny-Bot Monitor <span id="statusBadge" class="status-badge status-stopped">未运行</span></h1>
        <div class="tabs">
            <button class="tab active" onclick="showTab('monitor')">监控</button>
            <button class="tab" onclick="showTab('logs')">日志</button>
            <button class="tab" onclick="showTab('config')">配置</button>
        </div>
        <div id="monitor" class="tab-content active">
            <div class="grid">
                <div class="card"><h2>进程状态</h2><div class="stat-row"><span class="stat-label">运行状态</span><span class="stat-value" id="status">检测中...</span></div><div class="stat-row"><span class="stat-label">进程 PID</span><span class="stat-value" id="pid">-</span></div><div class="stat-row"><span class="stat-label">运行时长</span><span class="stat-value" id="uptime">-</span></div></div>
                <div class="card"><h2>资源占用</h2><div class="stat-row"><span class="stat-label">CPU 使用率</span><span class="stat-value" id="cpu">0%</span></div><div class="progress-bar"><div class="progress-fill" id="cpuBar" style="width: 0%"></div></div><div class="stat-row" style="margin-top: 15px;"><span class="stat-label">内存使用</span><span class="stat-value" id="memory">0 MB</span></div><div class="progress-bar"><div class="progress-fill" id="memBar" style="width: 0%"></div></div><div class="stat-row" style="margin-top: 15px;"><span class="stat-label">线程数 / 句柄数</span><span class="stat-value"><span id="threads">-</span> / <span id="handles">-</span></span></div></div>
                <div class="card"><h2>进程网络流量</h2><div class="stat-row"><span class="stat-label">下载速度</span><span class="speed-value" id="downloadSpeed">0 KB/s</span></div><div class="stat-row"><span class="stat-label">上传速度</span><span class="speed-value upload" id="uploadSpeed">0 KB/s</span></div><div class="stat-row"><span class="stat-label">总下载 / 总上传</span><span class="stat-value"><span id="totalDownload">0 MB</span> / <span id="totalUpload">0 MB</span></span></div></div>
                <div class="card"><h2>系统网络流量</h2><div class="stat-row"><span class="stat-label">系统下载</span><span class="speed-value" id="sysDownload">0 KB/s</span></div><div class="stat-row"><span class="stat-label">系统上传</span><span class="speed-value upload" id="sysUpload">0 KB/s</span></div></div>
            </div>
            <div class="card"><h2>进程控制</h2><div class="btn-group"><button class="btn btn-success" onclick="controlProcess('start')">启动进程</button><button class="btn btn-danger" onclick="controlProcess('stop')">停止进程</button><button class="btn btn-warning" onclick="controlProcess('restart')">重启进程</button></div></div>
        </div>
        <div id="logs" class="tab-content"><div class="card"><h2>实时日志</h2><div class="btn-group" style="margin-bottom: 15px;"><button class="btn btn-primary" onclick="refreshLogs()">刷新日志</button><button class="btn btn-danger" onclick="clearLogs()">清空显示</button></div><div id="logViewer" class="log-viewer">等待日志...</div></div></div>
        <div id="config" class="tab-content"><div class="card"><h2>配置文件编辑</h2><div class="btn-group" style="margin-bottom: 15px;"><button class="btn btn-primary" onclick="loadConfig()">加载配置</button><button class="btn btn-success" onclick="saveConfig()">保存配置</button></div><textarea id="configEditor" class="config-editor" placeholder="加载配置文件..."></textarea></div></div>
        <p class="update-time">最后更新: <span id="updateTime">-</span></p>
    </div>
    <script>
        function showTab(tabId) { document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active')); document.querySelectorAll('.tab').forEach(t => t.classList.remove('active')); document.getElementById(tabId).classList.add('active'); event.target.classList.add('active'); }
        function updateStatus() { fetch('/api/status').then(r => r.json()).then(data => { document.getElementById('status').textContent = data.status; document.getElementById('pid').textContent = data.pid; document.getElementById('uptime').textContent = data.uptime; document.getElementById('cpu').textContent = data.cpu + '%'; document.getElementById('cpuBar').style.width = Math.min(data.cpu, 100) + '%'; document.getElementById('memory').textContent = data.memory; document.getElementById('memBar').style.width = Math.min(data.memory_percent, 100) + '%'; document.getElementById('threads').textContent = data.threads; document.getElementById('handles').textContent = data.handles; document.getElementById('downloadSpeed').textContent = data.download_speed; document.getElementById('uploadSpeed').textContent = data.upload_speed; document.getElementById('totalDownload').textContent = data.total_download; document.getElementById('totalUpload').textContent = data.total_upload; document.getElementById('sysDownload').textContent = data.sys_download; document.getElementById('sysUpload').textContent = data.sys_upload; document.getElementById('updateTime').textContent = data.last_update; var badge = document.getElementById('statusBadge'); if (data.status === '运行中') { badge.textContent = '运行中'; badge.className = 'status-badge status-running'; } else { badge.textContent = '未运行'; badge.className = 'status-badge status-stopped'; } }).catch(e => console.error('Error:', e)); }
        function controlProcess(action) { fetch('/api/control', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: action}) }).then(r => r.json()).then(data => alert(data.message)).catch(e => alert('操作失败: ' + e)); }
        function loadConfig() { fetch('/api/config').then(r => r.json()).then(data => { if (data.content) { document.getElementById('configEditor').value = data.content; } else { alert(data.error || '加载失败'); } }).catch(e => alert('加载失败: ' + e)); }
        function saveConfig() { var content = document.getElementById('configEditor').value; fetch('/api/config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({content: content}) }).then(r => r.json()).then(data => alert(data.message || data.error)).catch(e => alert('保存失败: ' + e)); }
        function refreshLogs() { fetch('/api/logs').then(r => r.json()).then(data => { var viewer = document.getElementById('logViewer'); viewer.textContent = data.logs.join('\\n') || '暂无日志'; viewer.scrollTop = viewer.scrollHeight; }).catch(e => console.error('Error:', e)); }
        function clearLogs() { document.getElementById('logViewer').textContent = ''; }
        setInterval(updateStatus, 1000); setInterval(refreshLogs, 3000); updateStatus(); refreshLogs();
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(html.encode('utf-8')))
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def send_json_status(self):
        response = json.dumps(monitor_data, ensure_ascii=False)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(response.encode('utf-8')))
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))
    
    def send_config(self):
        global config_path
        if not config_path or not os.path.exists(config_path):
            response = json.dumps({"error": "配置文件未找到"}, ensure_ascii=False)
        else:
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                response = json.dumps({"content": content}, ensure_ascii=False)
            except Exception as e:
                response = json.dumps({"error": str(e)}, ensure_ascii=False)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(response.encode('utf-8')))
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))
    
    def send_logs(self):
        global recent_logs
        response = json.dumps({"logs": list(recent_logs)}, ensure_ascii=False)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(response.encode('utf-8')))
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))
    
    def save_config(self):
        global config_path
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            if not config_path:
                response = json.dumps({"error": "配置文件路径未设置"}, ensure_ascii=False)
            else:
                if os.path.exists(config_path):
                    backup_path = config_path + ".bak"
                    with open(config_path, 'r', encoding='utf-8') as f:
                        backup_content = f.read()
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(backup_content)
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(data['content'])
                response = json.dumps({"message": "配置已保存"}, ensure_ascii=False)
        except Exception as e:
            response = json.dumps({"error": str(e)}, ensure_ascii=False)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(response.encode('utf-8')))
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))
    
    def handle_control(self):
        global control_callback
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            action = data.get('action', '')
            if control_callback:
                result = control_callback(action)
                response = json.dumps({"message": result}, ensure_ascii=False)
            else:
                response = json.dumps({"error": "控制回调未设置"}, ensure_ascii=False)
        except Exception as e:
            response = json.dumps({"error": str(e)}, ensure_ascii=False)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(response.encode('utf-8')))
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))


class SaveAnyMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("SaveAny-Bot Monitor v2.5")
        self.root.geometry("780x750")
        self.root.minsize(750, 650)
        
        self.target_process = "saveany-bot.exe"
        self.target_path = None
        self.process = None
        self.managed_process = None
        self.running = True
        self.update_interval = 1000
        
        self.net_history = deque(maxlen=60)
        self.last_net_io = None
        self.last_net_time = None
        self.proc_last_io = None
        self.proc_last_time = None
        
        self.web_server = None
        self.web_thread = None
        self.web_port = 8080
        
        self.log_queue = queue.Queue()
        self.log_file = None
        self.log_file_path = None
        self.capture_logs = True
        self.custom_log_dir = None
        
        self.settings = {}
        self.load_settings()
        
        global config_path, control_callback, recent_logs
        config_path = None
        control_callback = self.handle_web_control
        recent_logs = deque(maxlen=500)
        
        self.create_widgets()
        self.start_monitoring()
        self.process_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def load_settings(self):
        try:
            settings_path = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__), SETTINGS_FILE)
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
                    self.custom_log_dir = self.settings.get('log_dir', None)
        except Exception:
            self.settings = {}
    
    def save_settings(self):
        try:
            settings_path = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__), SETTINGS_FILE)
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存设置失败: {str(e)}")
    
    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        monitor_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(monitor_frame, text=" 📊 监控 ")
        self.create_monitor_tab(monitor_frame)
        
        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text=" 📝 日志 ")
        self.create_log_tab(log_frame)
        
        settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(settings_frame, text=" ⚙️ 设置 ")
        self.create_settings_tab(settings_frame)
        
        config_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(config_frame, text=" 📄 配置编辑 ")
        self.create_config_tab(config_frame)
        
        web_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(web_frame, text=" 🌐 Web 服务 ")
        self.create_web_tab(web_frame)
    
    def create_monitor_tab(self, parent):
        status_frame = ttk.LabelFrame(parent, text="进程状态", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        status_row = ttk.Frame(status_frame)
        status_row.pack(fill=tk.X)
        
        ttk.Label(status_row, text="运行状态:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(status_row, text="检测中...", font=("Microsoft YaHei", 10, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Label(status_row, text="PID:").pack(side=tk.LEFT)
        self.pid_label = ttk.Label(status_row, text="-")
        self.pid_label.pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Label(status_row, text="运行时长:").pack(side=tk.LEFT)
        self.uptime_label = ttk.Label(status_row, text="-")
        self.uptime_label.pack(side=tk.LEFT)
        
        resource_frame = ttk.LabelFrame(parent, text="资源占用", padding="10")
        resource_frame.pack(fill=tk.X, pady=(0, 10))
        
        cpu_row = ttk.Frame(resource_frame)
        cpu_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(cpu_row, text="CPU 使用率:", width=12).pack(side=tk.LEFT)
        self.cpu_progress = ttk.Progressbar(cpu_row, length=300, mode='determinate')
        self.cpu_progress.pack(side=tk.LEFT, padx=(5, 10))
        self.cpu_label = ttk.Label(cpu_row, text="0%", width=8)
        self.cpu_label.pack(side=tk.LEFT)
        
        mem_row = ttk.Frame(resource_frame)
        mem_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(mem_row, text="内存使用:", width=12).pack(side=tk.LEFT)
        self.mem_progress = ttk.Progressbar(mem_row, length=300, mode='determinate')
        self.mem_progress.pack(side=tk.LEFT, padx=(5, 10))
        self.mem_label = ttk.Label(mem_row, text="0 MB", width=8)
        self.mem_label.pack(side=tk.LEFT)
        
        thread_row = ttk.Frame(resource_frame)
        thread_row.pack(fill=tk.X)
        ttk.Label(thread_row, text="线程数:", width=12).pack(side=tk.LEFT)
        self.thread_label = ttk.Label(thread_row, text="-")
        self.thread_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(thread_row, text="句柄数:").pack(side=tk.LEFT)
        self.handle_label = ttk.Label(thread_row, text="-")
        self.handle_label.pack(side=tk.LEFT)
        
        network_frame = ttk.LabelFrame(parent, text="网络流量 (进程)", padding="10")
        network_frame.pack(fill=tk.X, pady=(0, 10))
        
        download_row = ttk.Frame(network_frame)
        download_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(download_row, text="下载速度:", width=12).pack(side=tk.LEFT)
        self.download_label = ttk.Label(download_row, text="0 KB/s", font=("Microsoft YaHei", 10))
        self.download_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(download_row, text="总下载:").pack(side=tk.LEFT)
        self.total_download_label = ttk.Label(download_row, text="0 MB")
        self.total_download_label.pack(side=tk.LEFT)
        
        upload_row = ttk.Frame(network_frame)
        upload_row.pack(fill=tk.X)
        ttk.Label(upload_row, text="上传速度:", width=12).pack(side=tk.LEFT)
        self.upload_label = ttk.Label(upload_row, text="0 KB/s", font=("Microsoft YaHei", 10))
        self.upload_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(upload_row, text="总上传:").pack(side=tk.LEFT)
        self.total_upload_label = ttk.Label(upload_row, text="0 MB")
        self.total_upload_label.pack(side=tk.LEFT)
        
        sys_network_frame = ttk.LabelFrame(parent, text="系统网络流量 (全局)", padding="10")
        sys_network_frame.pack(fill=tk.X, pady=(0, 10))
        
        sys_net_row = ttk.Frame(sys_network_frame)
        sys_net_row.pack(fill=tk.X)
        ttk.Label(sys_net_row, text="系统下载:", width=12).pack(side=tk.LEFT)
        self.sys_download_label = ttk.Label(sys_net_row, text="0 KB/s")
        self.sys_download_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(sys_net_row, text="系统上传:").pack(side=tk.LEFT)
        self.sys_upload_label = ttk.Label(sys_net_row, text="0 KB/s")
        self.sys_upload_label.pack(side=tk.LEFT)
        
        control_frame = ttk.LabelFrame(parent, text="控制", padding="10")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_row = ttk.Frame(control_frame)
        btn_row.pack(fill=tk.X)
        
        self.start_btn = ttk.Button(btn_row, text="启动进程", command=self.start_process)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_btn = ttk.Button(btn_row, text="停止进程", command=self.stop_process)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.restart_btn = ttk.Button(btn_row, text="重启进程", command=self.restart_process)
        self.restart_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.browse_btn = ttk.Button(btn_row, text="选择程序", command=self.browse_exe)
        self.browse_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.open_folder_btn = ttk.Button(btn_row, text="打开目录", command=self.open_folder)
        self.open_folder_btn.pack(side=tk.LEFT)
        
        path_row = ttk.Frame(control_frame)
        path_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(path_row, text="程序路径:").pack(side=tk.LEFT)
        self.path_label = ttk.Label(path_row, text="自动检测", wraplength=500)
        self.path_label.pack(side=tk.LEFT, padx=(5, 0))
        
        log_frame = ttk.LabelFrame(parent, text="最近日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_frame, height=4, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log("SaveAny-Bot Monitor v2.5 已启动")
        self.log(f"正在监控进程: {self.target_process}")
    
    def create_log_tab(self, parent):
        info_frame = ttk.LabelFrame(parent, text="日志捕获", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_text = "通过本监控程序启动 SaveAny-Bot 可以捕获其控制台输出并保存到日志文件。"
        ttk.Label(info_frame, text=info_text, wraplength=680).pack(fill=tk.X)
        
        settings_frame = ttk.Frame(parent)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.capture_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="启用日志捕获", variable=self.capture_var).pack(side=tk.LEFT)
        
        ttk.Label(settings_frame, text="  日志文件:").pack(side=tk.LEFT, padx=(20, 0))
        self.log_path_label = ttk.Label(settings_frame, text="未启动", foreground="gray")
        self.log_path_label.pack(side=tk.LEFT, padx=(5, 0))
        
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(btn_frame, text="清空显示", command=self.clear_console_log).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="打开日志文件夹", command=self.open_log_folder).pack(side=tk.LEFT, padx=(0, 10))
        
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn_frame, text="自动滚动", variable=self.auto_scroll_var).pack(side=tk.LEFT)
        
        log_display_frame = ttk.LabelFrame(parent, text="SaveAny-Bot 控制台输出", padding="5")
        log_display_frame.pack(fill=tk.BOTH, expand=True)
        
        self.console_log = scrolledtext.ScrolledText(log_display_frame, wrap=tk.WORD, font=("Consolas", 9), bg='#1e1e1e', fg='#d4d4d4', insertbackground='white')
        self.console_log.pack(fill=tk.BOTH, expand=True)
        self.console_log.insert(tk.END, "等待 SaveAny-Bot 启动...\n提示: 请通过本监控程序的「启动进程」按钮启动 SaveAny-Bot 以捕获日志\n")
    
    def create_settings_tab(self, parent):
        # 日志位置设置
        log_frame = ttk.LabelFrame(parent, text="📁 日志保存位置", padding="10")
        log_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(log_frame, text="设置 SaveAny-Bot 日志文件的保存位置（默认为程序目录下的 logs 文件夹）").pack(fill=tk.X, pady=(0, 10))
        
        log_path_row = ttk.Frame(log_frame)
        log_path_row.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(log_path_row, text="日志目录:").pack(side=tk.LEFT)
        self.log_dir_entry = ttk.Entry(log_path_row, width=50)
        self.log_dir_entry.pack(side=tk.LEFT, padx=(5, 10), fill=tk.X, expand=True)
        if self.custom_log_dir:
            self.log_dir_entry.insert(0, self.custom_log_dir)
        
        ttk.Button(log_path_row, text="浏览...", command=self.browse_log_dir).pack(side=tk.LEFT)
        
        log_btn_row = ttk.Frame(log_frame)
        log_btn_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(log_btn_row, text="应用日志位置", command=self.apply_log_dir).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(log_btn_row, text="恢复默认", command=self.reset_log_dir).pack(side=tk.LEFT)
        
        # SOCKS5 代理设置
        proxy_frame = ttk.LabelFrame(parent, text="🌐 SOCKS5 代理设置", padding="10")
        proxy_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(proxy_frame, text="设置 SaveAny-Bot 使用的 SOCKS5 代理（将自动更新到 config.toml）").pack(fill=tk.X, pady=(0, 10))
        
        proxy_enable_row = ttk.Frame(proxy_frame)
        proxy_enable_row.pack(fill=tk.X, pady=(0, 5))
        
        self.proxy_enable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(proxy_enable_row, text="启用代理", variable=self.proxy_enable_var).pack(side=tk.LEFT)
        
        proxy_addr_row = ttk.Frame(proxy_frame)
        proxy_addr_row.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(proxy_addr_row, text="代理地址:", width=10).pack(side=tk.LEFT)
        self.proxy_host_entry = ttk.Entry(proxy_addr_row, width=20)
        self.proxy_host_entry.insert(0, "127.0.0.1")
        self.proxy_host_entry.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Label(proxy_addr_row, text="端口:").pack(side=tk.LEFT)
        self.proxy_port_entry = ttk.Entry(proxy_addr_row, width=8)
        self.proxy_port_entry.insert(0, "7897")
        self.proxy_port_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        proxy_auth_row = ttk.Frame(proxy_frame)
        proxy_auth_row.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(proxy_auth_row, text="用户名:", width=10).pack(side=tk.LEFT)
        self.proxy_user_entry = ttk.Entry(proxy_auth_row, width=15)
        self.proxy_user_entry.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Label(proxy_auth_row, text="密码:").pack(side=tk.LEFT)
        self.proxy_pass_entry = ttk.Entry(proxy_auth_row, width=15, show="*")
        self.proxy_pass_entry.pack(side=tk.LEFT, padx=(5, 10))
        
        self.proxy_show_pass_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(proxy_auth_row, text="显示密码", variable=self.proxy_show_pass_var, command=self.toggle_proxy_password).pack(side=tk.LEFT)
        
        proxy_btn_row = ttk.Frame(proxy_frame)
        proxy_btn_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(proxy_btn_row, text="应用代理设置", command=self.apply_proxy_settings).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(proxy_btn_row, text="从配置读取", command=self.load_proxy_from_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(proxy_btn_row, text="测试连接", command=self.test_proxy_connection).pack(side=tk.LEFT)
        
        # SOCKS5 代理运行状态显示
        proxy_status_row = ttk.Frame(proxy_frame)
        proxy_status_row.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(proxy_status_row, text="代理状态:").pack(side=tk.LEFT)
        self.proxy_status_label = ttk.Label(proxy_status_row, text="未检测", foreground="gray")
        self.proxy_status_label.pack(side=tk.LEFT, padx=(5, 15))
        
        ttk.Label(proxy_status_row, text="延迟:").pack(side=tk.LEFT)
        self.proxy_latency_label = ttk.Label(proxy_status_row, text="-", foreground="gray")
        self.proxy_latency_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # 下载位置设置
        download_frame = ttk.LabelFrame(parent, text="📥 下载保存位置", padding="10")
        download_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(download_frame, text="设置 SaveAny-Bot 下载文件的默认保存位置（将自动更新到 config.toml）").pack(fill=tk.X, pady=(0, 10))
        
        download_path_row = ttk.Frame(download_frame)
        download_path_row.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(download_path_row, text="下载目录:").pack(side=tk.LEFT)
        self.download_dir_entry = ttk.Entry(download_path_row, width=50)
        self.download_dir_entry.pack(side=tk.LEFT, padx=(5, 10), fill=tk.X, expand=True)
        
        ttk.Button(download_path_row, text="浏览...", command=self.browse_download_dir).pack(side=tk.LEFT)
        
        download_btn_row = ttk.Frame(download_frame)
        download_btn_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(download_btn_row, text="应用下载位置", command=self.apply_download_dir).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(download_btn_row, text="从配置读取", command=self.load_download_from_config).pack(side=tk.LEFT)
        
        self.settings_status = ttk.Label(parent, text="提示: 修改设置后需要重启 SaveAny-Bot 才能生效", foreground="blue")
        self.settings_status.pack(fill=tk.X, pady=(10, 0))
    
    def browse_log_dir(self):
        dir_path = filedialog.askdirectory(title="选择日志保存目录")
        if dir_path:
            self.log_dir_entry.delete(0, tk.END)
            self.log_dir_entry.insert(0, dir_path)
    
    def apply_log_dir(self):
        log_dir = self.log_dir_entry.get().strip()
        if log_dir:
            if not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("错误", f"创建目录失败: {str(e)}")
                    return
            self.custom_log_dir = log_dir
            self.settings['log_dir'] = log_dir
            self.save_settings()
            self.settings_status.config(text=f"✓ 日志目录已设置为: {log_dir}", foreground="green")
            self.log(f"日志目录已更改为: {log_dir}")
        else:
            messagebox.showwarning("警告", "请输入或选择日志目录")
    
    def reset_log_dir(self):
        self.log_dir_entry.delete(0, tk.END)
        self.custom_log_dir = None
        if 'log_dir' in self.settings:
            del self.settings['log_dir']
        self.save_settings()
        self.settings_status.config(text="✓ 日志目录已恢复为默认（程序目录/logs）", foreground="green")
        self.log("日志目录已恢复为默认")
    
    def toggle_proxy_password(self):
        if self.proxy_show_pass_var.get():
            self.proxy_pass_entry.config(show="")
        else:
            self.proxy_pass_entry.config(show="*")
    
    def apply_proxy_settings(self):
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径以加载配置文件")
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            enable = self.proxy_enable_var.get()
            host = self.proxy_host_entry.get().strip()
            port = self.proxy_port_entry.get().strip()
            user = self.proxy_user_entry.get().strip()
            password = self.proxy_pass_entry.get().strip()
            
            if user and password:
                import urllib.parse
                user_encoded = urllib.parse.quote(user, safe='')
                pass_encoded = urllib.parse.quote(password, safe='')
                proxy_url = f"socks5://{user_encoded}:{pass_encoded}@{host}:{port}"
            else:
                proxy_url = f"socks5://{host}:{port}"
            
            enable_str = "true" if enable else "false"
            
            # 使用正确的 [telegram.proxy] 格式
            if '[telegram.proxy]' in content:
                content = re.sub(r'(\[telegram\.proxy\].*?enable\s*=\s*)(true|false)', f'\\1{enable_str}', content, flags=re.DOTALL)
                content = re.sub(r'(\[telegram\.proxy\].*?url\s*=\s*")[^"]*(")' , f'\\1{proxy_url}\\2', content, flags=re.DOTALL)
            else:
                # 在 [telegram] 部分后添加 [telegram.proxy]
                if '[telegram]' in content:
                    proxy_config = f'\n[telegram.proxy]\n# 启用代理连接 telegram\nenable = {enable_str}\nurl = "{proxy_url}"\n'
                    # 找到 [telegram] 部分的末尾（下一个 [ 开头的行之前）
                    telegram_match = re.search(r'(\[telegram\][^\[]*)', content)
                    if telegram_match:
                        telegram_section = telegram_match.group(1)
                        content = content.replace(telegram_section, telegram_section.rstrip() + proxy_config)
                    else:
                        content += proxy_config
                else:
                    proxy_config = f'\n[telegram.proxy]\n# 启用代理连接 telegram\nenable = {enable_str}\nurl = "{proxy_url}"\n'
                    content += proxy_config
            
            backup_path = config_path + ".bak"
            with open(config_path, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(backup_content)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.settings_status.config(text=f"✓ 代理设置已保存（{'已启用' if enable else '已禁用'}）", foreground="green")
            self.log(f"代理设置已更新: {proxy_url if enable else '已禁用'}")
            messagebox.showinfo("成功", "代理设置已保存！\n如果 SaveAny-Bot 正在运行，需要重启才能生效。")
        except Exception as e:
            messagebox.showerror("错误", f"保存代理设置失败: {str(e)}")
    
    def load_proxy_from_config(self):
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径以加载配置文件")
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用正确的 [telegram.proxy] 格式
            enable_match = re.search(r'\[telegram\.proxy\].*?enable\s*=\s*(true|false)', content, re.DOTALL)
            if enable_match:
                self.proxy_enable_var.set(enable_match.group(1) == 'true')
            
            url_match = re.search(r'\[telegram\.proxy\].*?url\s*=\s*"([^"]*)"', content, re.DOTALL)
            if url_match:
                proxy_url = url_match.group(1)
                url_pattern = r'socks5://(?:([^:@]+):([^@]+)@)?([^:]+):(\d+)'
                url_parts = re.match(url_pattern, proxy_url)
                if url_parts:
                    user, password, host, port = url_parts.groups()
                    self.proxy_host_entry.delete(0, tk.END)
                    self.proxy_host_entry.insert(0, host or "127.0.0.1")
                    self.proxy_port_entry.delete(0, tk.END)
                    self.proxy_port_entry.insert(0, port or "7897")
                    self.proxy_user_entry.delete(0, tk.END)
                    if user:
                        import urllib.parse
                        self.proxy_user_entry.insert(0, urllib.parse.unquote(user))
                    self.proxy_pass_entry.delete(0, tk.END)
                    if password:
                        import urllib.parse
                        self.proxy_pass_entry.insert(0, urllib.parse.unquote(password))
            
            self.settings_status.config(text="✓ 已从配置文件读取代理设置", foreground="green")
        except Exception as e:
            messagebox.showerror("错误", f"读取代理设置失败: {str(e)}")
    
    def test_proxy_connection(self):
        """测试 SOCKS5 代理连接状态"""
        host = self.proxy_host_entry.get().strip()
        port = self.proxy_port_entry.get().strip()
        user = self.proxy_user_entry.get().strip()
        password = self.proxy_pass_entry.get().strip()
        
        if not host or not port:
            messagebox.showwarning("警告", "请先填写代理地址和端口")
            return
        
        self.proxy_status_label.config(text="检测中...", foreground="orange")
        self.proxy_latency_label.config(text="-", foreground="gray")
        self.root.update()
        
        # 在后台线程中测试连接
        def test_connection():
            try:
                import socks
                start_time = time.time()
                
                # 创建 SOCKS5 代理连接
                s = socks.socksocket()
                s.set_proxy(socks.SOCKS5, host, int(port), username=user if user else None, password=password if password else None)
                s.settimeout(10)
                
                # 尝试连接 Telegram API 服务器
                s.connect(("api.telegram.org", 443))
                latency = (time.time() - start_time) * 1000  # 转换为毫秒
                s.close()
                
                # 更新 UI（在主线程中）
                self.root.after(0, lambda: self.update_proxy_status(True, latency))
            except ImportError:
                # 如果没有安装 PySocks，尝试直接 TCP 连接测试
                try:
                    start_time = time.time()
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(5)
                    s.connect((host, int(port)))
                    latency = (time.time() - start_time) * 1000
                    s.close()
                    self.root.after(0, lambda: self.update_proxy_status(True, latency, "TCP连接正常"))
                except Exception as e:
                    self.root.after(0, lambda: self.update_proxy_status(False, 0, str(e)))
            except Exception as e:
                self.root.after(0, lambda: self.update_proxy_status(False, 0, str(e)))
        
        threading.Thread(target=test_connection, daemon=True).start()
    
    def update_proxy_status(self, success, latency, message=None):
        """更新代理状态显示"""
        if success:
            if latency < 200:
                latency_color = "green"
            elif latency < 500:
                latency_color = "orange"
            else:
                latency_color = "red"
            
            status_text = message if message else "连接正常"
            self.proxy_status_label.config(text=f"✓ {status_text}", foreground="green")
            self.proxy_latency_label.config(text=f"{latency:.0f} ms", foreground=latency_color)
            self.settings_status.config(text=f"✓ 代理连接测试成功，延迟: {latency:.0f}ms", foreground="green")
        else:
            error_msg = message if message else "连接失败"
            self.proxy_status_label.config(text=f"✗ {error_msg[:20]}", foreground="red")
            self.proxy_latency_label.config(text="-", foreground="gray")
            self.settings_status.config(text=f"✗ 代理连接测试失败: {error_msg}", foreground="red")
    
    def browse_download_dir(self):
        dir_path = filedialog.askdirectory(title="选择下载保存目录")
        if dir_path:
            self.download_dir_entry.delete(0, tk.END)
            self.download_dir_entry.insert(0, dir_path)
    
    def apply_download_dir(self):
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径以加载配置文件")
            return
        
        download_dir = self.download_dir_entry.get().strip()
        if not download_dir:
            messagebox.showwarning("警告", "请输入或选择下载目录")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            download_dir = download_dir.replace('\\', '/')
            
            # 使用正确的 [[storages]] 格式
            # 查找现有的 [[storages]] 配置并更新 base_path
            if '[[storages]]' in content:
                # 查找 type = "local" 的 storage 并更新 base_path
                local_storage_pattern = r'(\[\[storages\]\][^\[]*type\s*=\s*"local"[^\[]*base_path\s*=\s*")[^"]*(")'  
                if re.search(local_storage_pattern, content, re.DOTALL):
                    content = re.sub(local_storage_pattern, f'\\1{download_dir}\\2', content, flags=re.DOTALL)
                else:
                    # 没有找到 local 类型的 storage，添加一个新的
                    storage_config = f'\n[[storages]]\nname = "本地磁盘"\ntype = "local"\nenable = true\nbase_path = "{download_dir}"\n'
                    content += storage_config
            else:
                # 没有 [[storages]] 配置，添加一个新的
                storage_config = f'\n[[storages]]\nname = "本地磁盘"\ntype = "local"\nenable = true\nbase_path = "{download_dir}"\n'
                content += storage_config
            
            backup_path = config_path + ".bak"
            with open(config_path, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(backup_content)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.settings_status.config(text=f"✓ 下载目录已设置为: {download_dir}", foreground="green")
            self.log(f"下载目录已更新: {download_dir}")
            messagebox.showinfo("成功", "下载目录设置已保存！\n如果 SaveAny-Bot 正在运行，需要重启才能生效。")
        except Exception as e:
            messagebox.showerror("错误", f"保存下载目录设置失败: {str(e)}")
    
    def load_download_from_config(self):
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径以加载配置文件")
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用正确的 [[storages]] 格式读取
            # 查找 type = "local" 的 storage 的 base_path
            local_storage_pattern = r'\[\[storages\]\][^\[]*type\s*=\s*"local"[^\[]*base_path\s*=\s*"([^"]*)"'
            path_match = re.search(local_storage_pattern, content, re.DOTALL)
            if path_match:
                download_path = path_match.group(1)
                self.download_dir_entry.delete(0, tk.END)
                self.download_dir_entry.insert(0, download_path)
                self.settings_status.config(text="✓ 已从配置文件读取下载目录设置", foreground="green")
            else:
                self.settings_status.config(text="配置文件中未找到本地存储设置", foreground="orange")
        except Exception as e:
            messagebox.showerror("错误", f"读取下载目录设置失败: {str(e)}")
    
    def create_config_tab(self, parent):
        ttk.Label(parent, text="编辑 SaveAny-Bot 的配置文件 (config.toml)，修改后点击保存按钮。", wraplength=650).pack(fill=tk.X, pady=(0, 10))
        
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.load_config_btn = ttk.Button(btn_frame, text="加载配置", command=self.load_config)
        self.load_config_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.save_config_btn = ttk.Button(btn_frame, text="保存配置", command=self.save_config)
        self.save_config_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.reload_config_btn = ttk.Button(btn_frame, text="重新加载", command=self.reload_config)
        self.reload_config_btn.pack(side=tk.LEFT)
        
        path_frame = ttk.Frame(parent)
        path_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(path_frame, text="配置文件:").pack(side=tk.LEFT)
        self.config_path_label = ttk.Label(path_frame, text="未加载", foreground="gray")
        self.config_path_label.pack(side=tk.LEFT, padx=(5, 0))
        
        editor_frame = ttk.Frame(parent)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        self.config_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.NONE, font=("Consolas", 10), undo=True)
        self.config_editor.pack(fill=tk.BOTH, expand=True)
        
        h_scrollbar = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL, command=self.config_editor.xview)
        h_scrollbar.pack(fill=tk.X)
        self.config_editor.configure(xscrollcommand=h_scrollbar.set)
        
        self.config_status = ttk.Label(parent, text="提示: 请先选择 SaveAny-Bot 程序路径以加载配置文件", foreground="blue")
        self.config_status.pack(fill=tk.X, pady=(10, 0))
    
    def create_web_tab(self, parent):
        info_frame = ttk.LabelFrame(parent, text="Web 监控服务", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(info_frame, text="启动 Web 服务后，可通过浏览器远程查看监控状态、日志和编辑配置。", wraplength=650).pack(fill=tk.X)
        
        port_frame = ttk.Frame(parent)
        port_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(port_frame, text="监听端口:").pack(side=tk.LEFT)
        self.port_entry = ttk.Entry(port_frame, width=10)
        self.port_entry.insert(0, "8080")
        self.port_entry.pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Label(port_frame, text="状态:").pack(side=tk.LEFT)
        self.web_status_label = ttk.Label(port_frame, text="未启动", foreground="gray")
        self.web_status_label.pack(side=tk.LEFT, padx=(5, 0))
        
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.start_web_btn = ttk.Button(btn_frame, text="启动 Web 服务", command=self.start_web_server)
        self.start_web_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_web_btn = ttk.Button(btn_frame, text="停止 Web 服务", command=self.stop_web_server, state=tk.DISABLED)
        self.stop_web_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.open_browser_btn = ttk.Button(btn_frame, text="打开浏览器", command=self.open_web_browser, state=tk.DISABLED)
        self.open_browser_btn.pack(side=tk.LEFT)
        
        url_frame = ttk.LabelFrame(parent, text="访问地址", padding="10")
        url_frame.pack(fill=tk.X, pady=(0, 10))
        self.url_label = ttk.Label(url_frame, text="Web 服务未启动", font=("Consolas", 11))
        self.url_label.pack(fill=tk.X)
        
        tips_frame = ttk.LabelFrame(parent, text="使用提示", padding="10")
        tips_frame.pack(fill=tk.X)
        tips_text = "本地访问: http://127.0.0.1:端口号\n局域网访问: http://本机IP:端口号\nWeb 界面支持查看实时日志、编辑配置、控制进程"
        ttk.Label(tips_frame, text=tips_text, justify=tk.LEFT).pack(fill=tk.X)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 100:
            self.log_text.delete('1.0', '2.0')
    
    def add_console_log(self, message):
        global recent_logs
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        recent_logs.append(log_line)
        if self.log_file:
            try:
                self.log_file.write(log_line + '\n')
                self.log_file.flush()
            except Exception:
                pass
        self.log_queue.put(log_line)
    
    def process_log_queue(self):
        try:
            while True:
                log_line = self.log_queue.get_nowait()
                self.console_log.insert(tk.END, log_line + '\n')
                if self.auto_scroll_var.get():
                    self.console_log.see(tk.END)
                lines = int(self.console_log.index('end-1c').split('.')[0])
                if lines > 2000:
                    self.console_log.delete('1.0', '500.0')
        except queue.Empty:
            pass
        if self.running:
            self.root.after(100, self.process_log_queue)
    
    def clear_console_log(self):
        self.console_log.delete('1.0', tk.END)
    
    def open_log_folder(self):
        log_dir = self.custom_log_dir
        if not log_dir and self.target_path:
            log_dir = os.path.join(os.path.dirname(self.target_path), "logs")
        if log_dir and os.path.exists(log_dir):
            if sys.platform == 'win32':
                os.startfile(log_dir)
            else:
                subprocess.Popen(['xdg-open', log_dir])
        else:
            messagebox.showinfo("提示", f"日志文件夹不存在: {log_dir}")
    
    def find_process(self):
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == self.target_process.lower():
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def format_bytes(self, bytes_value):
        if bytes_value < 1024:
            return f"{bytes_value} B"
        elif bytes_value < 1024 * 1024:
            return f"{bytes_value / 1024:.1f} KB"
        elif bytes_value < 1024 * 1024 * 1024:
            return f"{bytes_value / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_value / (1024 * 1024 * 1024):.2f} GB"
    
    def format_speed(self, bytes_per_sec):
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
    
    def format_uptime(self, seconds):
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            return f"{int(seconds // 60)}分{int(seconds % 60)}秒"
        elif seconds < 86400:
            return f"{int(seconds // 3600)}时{int((seconds % 3600) // 60)}分"
        else:
            return f"{int(seconds // 86400)}天{int((seconds % 86400) // 3600)}时"
    
    def update_ui(self):
        global monitor_data
        if not self.running:
            return
        try:
            proc = self.find_process()
            if proc:
                try:
                    self.status_label.config(text="运行中", foreground="green")
                    self.pid_label.config(text=str(proc.pid))
                    monitor_data["status"] = "运行中"
                    monitor_data["pid"] = str(proc.pid)
                    
                    with proc.oneshot():
                        cpu_percent = proc.cpu_percent()
                        self.cpu_progress['value'] = min(cpu_percent, 100)
                        self.cpu_label.config(text=f"{cpu_percent:.1f}%")
                        monitor_data["cpu"] = round(cpu_percent, 1)
                        
                        mem_info = proc.memory_info()
                        mem_mb = mem_info.rss / (1024 * 1024)
                        total_mem = psutil.virtual_memory().total
                        mem_percent = (mem_info.rss / total_mem) * 100
                        self.mem_progress['value'] = min(mem_percent, 100)
                        self.mem_label.config(text=f"{mem_mb:.1f} MB")
                        monitor_data["memory"] = f"{mem_mb:.1f} MB"
                        monitor_data["memory_percent"] = round(mem_percent, 1)
                        
                        num_threads = proc.num_threads()
                        self.thread_label.config(text=str(num_threads))
                        monitor_data["threads"] = str(num_threads)
                        
                        try:
                            num_handles = proc.num_handles()
                            self.handle_label.config(text=str(num_handles))
                            monitor_data["handles"] = str(num_handles)
                        except AttributeError:
                            self.handle_label.config(text="N/A")
                            monitor_data["handles"] = "N/A"
                        
                        create_time = proc.create_time()
                        uptime = time.time() - create_time
                        uptime_str = self.format_uptime(uptime)
                        self.uptime_label.config(text=uptime_str)
                        monitor_data["uptime"] = uptime_str
                        
                        exe_path = proc.exe()
                        if exe_path and not self.target_path:
                            self.target_path = exe_path
                            self.path_label.config(text=exe_path)
                            self.update_config_path()
                        
                        try:
                            io_counters = proc.io_counters()
                            current_time = time.time()
                            if self.proc_last_io and self.proc_last_time:
                                time_diff = current_time - self.proc_last_time
                                if time_diff > 0:
                                    read_speed = (io_counters.read_bytes - self.proc_last_io.read_bytes) / time_diff
                                    write_speed = (io_counters.write_bytes - self.proc_last_io.write_bytes) / time_diff
                                    dl_speed = self.format_speed(max(0, read_speed))
                                    ul_speed = self.format_speed(max(0, write_speed))
                                    self.download_label.config(text=dl_speed)
                                    self.upload_label.config(text=ul_speed)
                                    monitor_data["download_speed"] = dl_speed
                                    monitor_data["upload_speed"] = ul_speed
                            total_dl = self.format_bytes(io_counters.read_bytes)
                            total_ul = self.format_bytes(io_counters.write_bytes)
                            self.total_download_label.config(text=total_dl)
                            self.total_upload_label.config(text=total_ul)
                            monitor_data["total_download"] = total_dl
                            monitor_data["total_upload"] = total_ul
                            self.proc_last_io = io_counters
                            self.proc_last_time = current_time
                        except (psutil.AccessDenied, AttributeError):
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.set_offline_status()
            else:
                self.set_offline_status()
            
            try:
                net_io = psutil.net_io_counters()
                current_time = time.time()
                if self.last_net_io and self.last_net_time:
                    time_diff = current_time - self.last_net_time
                    if time_diff > 0:
                        download_speed = (net_io.bytes_recv - self.last_net_io.bytes_recv) / time_diff
                        upload_speed = (net_io.bytes_sent - self.last_net_io.bytes_sent) / time_diff
                        sys_dl = self.format_speed(max(0, download_speed))
                        sys_ul = self.format_speed(max(0, upload_speed))
                        self.sys_download_label.config(text=sys_dl)
                        self.sys_upload_label.config(text=sys_ul)
                        monitor_data["sys_download"] = sys_dl
                        monitor_data["sys_upload"] = sys_ul
                self.last_net_io = net_io
                self.last_net_time = current_time
            except Exception:
                pass
            
            monitor_data["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            self.log(f"更新错误: {str(e)}")
        
        if self.running:
            self.root.after(self.update_interval, self.update_ui)
    
    def set_offline_status(self):
        global monitor_data
        self.status_label.config(text="未运行", foreground="red")
        self.pid_label.config(text="-")
        self.uptime_label.config(text="-")
        self.cpu_progress['value'] = 0
        self.cpu_label.config(text="0%")
        self.mem_progress['value'] = 0
        self.mem_label.config(text="0 MB")
        self.thread_label.config(text="-")
        self.handle_label.config(text="-")
        self.download_label.config(text="0 KB/s")
        self.upload_label.config(text="0 KB/s")
        self.total_download_label.config(text="0 MB")
        self.total_upload_label.config(text="0 MB")
        self.proc_last_io = None
        self.proc_last_time = None
        monitor_data.update({"status": "未运行", "pid": "-", "uptime": "-", "cpu": 0, "memory": "0 MB", "memory_percent": 0, "threads": "-", "handles": "-", "download_speed": "0 KB/s", "upload_speed": "0 KB/s", "total_download": "0 MB", "total_upload": "0 MB"})
    
    def start_monitoring(self):
        self.update_ui()
    
    def update_config_path(self):
        global config_path
        if self.target_path:
            dir_path = os.path.dirname(self.target_path)
            cfg_path = os.path.join(dir_path, "config.toml")
            config_path = cfg_path
            self.config_path_label.config(text=cfg_path, foreground="black")
            if os.path.exists(cfg_path):
                self.load_config()
    
    def browse_exe(self):
        filepath = filedialog.askopenfilename(title="选择 SaveAny-Bot 程序", filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if filepath:
            self.target_path = filepath
            self.target_process = os.path.basename(filepath)
            self.path_label.config(text=filepath)
            self.log(f"已选择程序: {filepath}")
            self.update_config_path()
    
    def start_process(self):
        if self.find_process():
            messagebox.showinfo("提示", "进程已在运行中")
            return
        if not self.target_path:
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            self.browse_exe()
            return
        if not os.path.exists(self.target_path):
            messagebox.showerror("错误", f"程序文件不存在: {self.target_path}")
            return
        try:
            work_dir = os.path.dirname(self.target_path)
            if self.custom_log_dir:
                log_dir = self.custom_log_dir
            else:
                log_dir = os.path.join(work_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            
            log_filename = datetime.now().strftime("bot_%Y%m%d_%H%M%S.log")
            self.log_file_path = os.path.join(log_dir, log_filename)
            self.log_file = open(self.log_file_path, 'w', encoding='utf-8')
            self.log_path_label.config(text=self.log_file_path, foreground="green")
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                self.managed_process = subprocess.Popen([self.target_path], cwd=work_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=startupinfo, bufsize=1, universal_newlines=True, encoding='utf-8', errors='replace')
            else:
                self.managed_process = subprocess.Popen([self.target_path], cwd=work_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True)
            
            self.log(f"正在启动进程: {self.target_path}")
            self.log(f"日志文件: {self.log_file_path}")
            self.add_console_log(f"=== SaveAny-Bot 启动 ===")
            self.add_console_log(f"程序路径: {self.target_path}")
            self.add_console_log(f"工作目录: {work_dir}")
            self.add_console_log(f"日志文件: {self.log_file_path}")
            self.add_console_log("=" * 50)
            
            output_thread = threading.Thread(target=self.read_process_output, daemon=True)
            output_thread.start()
        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {str(e)}")
            self.log(f"启动失败: {str(e)}")
    
    def read_process_output(self):
        if not self.managed_process:
            return
        try:
            for line in iter(self.managed_process.stdout.readline, ''):
                if not self.running:
                    break
                line = line.rstrip('\n\r')
                if line:
                    self.add_console_log(line)
            self.managed_process.stdout.close()
            return_code = self.managed_process.wait()
            self.add_console_log(f"=== SaveAny-Bot 已退出，返回码: {return_code} ===")
        except Exception as e:
            self.add_console_log(f"读取输出错误: {str(e)}")
        finally:
            self.managed_process = None
            if self.log_file:
                try:
                    self.log_file.close()
                except Exception:
                    pass
                self.log_file = None
    
    def stop_process(self):
        proc = self.find_process()
        if not proc:
            messagebox.showinfo("提示", "进程未在运行")
            return
        if messagebox.askyesno("确认", "确定要停止 SaveAny-Bot 进程吗？"):
            try:
                proc.terminate()
                self.log("已发送停止信号")
                try:
                    proc.wait(timeout=5)
                    self.log("进程已停止")
                except psutil.TimeoutExpired:
                    proc.kill()
                    self.log("进程已强制终止")
            except Exception as e:
                messagebox.showerror("错误", f"停止失败: {str(e)}")
                self.log(f"停止失败: {str(e)}")
    
    def restart_process(self):
        proc = self.find_process()
        if proc:
            try:
                if not self.target_path:
                    self.target_path = proc.exe()
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                self.log("进程已停止，正在重启...")
                time.sleep(1)
                self.start_process()
            except Exception as e:
                messagebox.showerror("错误", f"重启失败: {str(e)}")
                self.log(f"重启失败: {str(e)}")
        else:
            self.start_process()
    
    def open_folder(self):
        if self.target_path and os.path.exists(self.target_path):
            folder = os.path.dirname(self.target_path)
            if sys.platform == 'win32':
                os.startfile(folder)
            else:
                subprocess.Popen(['xdg-open', folder])
        else:
            proc = self.find_process()
            if proc:
                try:
                    folder = os.path.dirname(proc.exe())
                    if sys.platform == 'win32':
                        os.startfile(folder)
                    else:
                        subprocess.Popen(['xdg-open', folder])
                except Exception:
                    messagebox.showwarning("警告", "无法获取程序目录")
            else:
                messagebox.showwarning("警告", "请先选择程序或等待进程运行")
    
    def load_config(self):
        global config_path
        if not config_path:
            if self.target_path:
                self.update_config_path()
            else:
                self.config_status.config(text="请先选择 SaveAny-Bot 程序路径", foreground="red")
                return
        if not os.path.exists(config_path):
            self.config_status.config(text=f"配置文件不存在: {config_path}", foreground="red")
            self.config_editor.delete('1.0', tk.END)
            self.config_editor.insert('1.0', f"# 配置文件不存在: {config_path}")
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.config_editor.delete('1.0', tk.END)
            self.config_editor.insert('1.0', content)
            self.config_status.config(text=f"配置已加载: {config_path}", foreground="green")
            self.log(f"已加载配置文件: {config_path}")
        except Exception as e:
            self.config_status.config(text=f"加载失败: {str(e)}", foreground="red")
    
    def save_config(self):
        global config_path
        if not config_path:
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        content = self.config_editor.get('1.0', tk.END)
        try:
            if os.path.exists(config_path):
                backup_path = config_path + ".bak"
                with open(config_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(backup_content)
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.config_status.config(text=f"配置已保存: {config_path}", foreground="green")
            self.log(f"配置已保存到: {config_path}")
            messagebox.showinfo("成功", "配置文件已保存！\n如果 SaveAny-Bot 正在运行，可能需要重启才能生效。")
        except Exception as e:
            self.config_status.config(text=f"保存失败: {str(e)}", foreground="red")
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def reload_config(self):
        if messagebox.askyesno("确认", "确定要重新加载配置文件吗？\n未保存的修改将丢失。"):
            self.load_config()
    
    def start_web_server(self):
        try:
            self.web_port = int(self.port_entry.get())
            self.web_server = StoppableHTTPServer(('0.0.0.0', self.web_port), MonitorHTTPHandler)
            self.web_thread = threading.Thread(target=self.web_server.serve_forever_stoppable, daemon=True)
            self.web_thread.start()
            local_ip = self.get_local_ip()
            self.web_status_label.config(text="运行中", foreground="green")
            self.url_label.config(text=f"本地: http://127.0.0.1:{self.web_port}  |  局域网: http://{local_ip}:{self.web_port}")
            self.start_web_btn.config(state=tk.DISABLED)
            self.stop_web_btn.config(state=tk.NORMAL)
            self.open_browser_btn.config(state=tk.NORMAL)
            self.port_entry.config(state=tk.DISABLED)
            self.log(f"Web 服务已启动，端口: {self.web_port}")
        except Exception as e:
            self.web_server = None
            messagebox.showerror("错误", f"启动 Web 服务失败: {str(e)}")
    
    def stop_web_server(self):
        if self.web_server:
            def stop_server():
                try:
                    self.web_server.stop()
                except Exception:
                    pass
            stop_thread = threading.Thread(target=stop_server, daemon=True)
            stop_thread.start()
            self.root.after(500, self._finish_stop_web_server)
    
    def _finish_stop_web_server(self):
        self.web_server = None
        self.web_thread = None
        self.web_status_label.config(text="已停止", foreground="gray")
        self.url_label.config(text="Web 服务未启动")
        self.start_web_btn.config(state=tk.NORMAL)
        self.stop_web_btn.config(state=tk.DISABLED)
        self.open_browser_btn.config(state=tk.DISABLED)
        self.port_entry.config(state=tk.NORMAL)
        self.log("Web 服务已停止")
    
    def open_web_browser(self):
        webbrowser.open(f"http://127.0.0.1:{self.web_port}")
    
    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def handle_web_control(self, action):
        if action == 'start':
            if self.find_process():
                return "进程已在运行中"
            if not self.target_path:
                return "请先在桌面程序中选择 SaveAny-Bot 程序路径"
            self.root.after(0, self.start_process)
            return "启动命令已发送"
        elif action == 'stop':
            proc = self.find_process()
            if not proc:
                return "进程未在运行"
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                return "进程已停止"
            except Exception as e:
                return f"停止失败: {str(e)}"
        elif action == 'restart':
            proc = self.find_process()
            if proc:
                try:
                    if not self.target_path:
                        self.target_path = proc.exe()
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    time.sleep(1)
                except Exception as e:
                    return f"停止失败: {str(e)}"
            if not self.target_path:
                return "请先在桌面程序中选择 SaveAny-Bot 程序路径"
            self.root.after(0, self.start_process)
            return "重启命令已发送"
        return "未知操作"
    
    def on_closing(self):
        self.running = False
        if self.web_server:
            try:
                self.web_server.stop()
            except Exception:
                pass
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    style = ttk.Style()
    try:
        style.theme_use('vista')
    except Exception:
        try:
            style.theme_use('clam')
        except Exception:
            pass
    app = SaveAnyMonitor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
