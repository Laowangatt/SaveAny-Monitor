#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SaveAny-Bot Monitor v2.7.1
监控 SaveAny-Bot 的运行状态、资源占用和网络流量
支持配置文件编辑、Web 网页查看、日志捕获和下载任务列表
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
recent_logs = deque(maxlen=500)  # 保存最近500行日志用于Web显示

class StoppableHTTPServer(HTTPServer):
    """可停止的 HTTP 服务器，针对 Windows Server 优化"""
    
    allow_reuse_address = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self.socket.settimeout(1.0)
    
    def serve_forever_stoppable(self):
        """可停止的服务循环"""
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
        """停止服务器"""
        self._stop_event.set()
        try:
            self.socket.close()
        except Exception:
            pass

class MonitorHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""
    
    protocol_version = 'HTTP/1.0'
    timeout = 10
    
    def log_message(self, format, *args):
        pass
    
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except socket.timeout:
            pass
        except Exception as e:
            # 记录具体错误但不中断程序
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
        except Exception as e:
            # 记录具体错误但不中断程序
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
        except Exception as e:
            # 记录具体错误但不中断程序
            pass
    
    def send_html_page(self):
        """发送 HTML 页面"""
        html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SaveAny-Bot Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
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
        .progress-fill.warning { background: linear-gradient(90deg, #ff9800, #ffb74d); }
        .progress-fill.danger { background: linear-gradient(90deg, #ff5252, #ff8a80); }
        .speed-value { font-size: 1.5em; font-weight: bold; color: #69f0ae; }
        .speed-value.upload { color: #64b5f6; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 15px; }
        .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9em; transition: all 0.3s ease; }
        .btn-primary { background: #2196f3; color: #fff; }
        .btn-success { background: #00c853; color: #fff; }
        .btn-danger { background: #ff5252; color: #fff; }
        .btn-warning { background: #ff9800; color: #fff; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.3); }
        .config-editor, .log-viewer { width: 100%; min-height: 300px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 15px; color: #fff; font-family: "Consolas", "Monaco", monospace; font-size: 13px; resize: vertical; }
        .log-viewer { min-height: 400px; white-space: pre-wrap; word-wrap: break-word; overflow-y: auto; }
        .update-time { text-align: center; color: rgba(255,255,255,0.5); font-size: 0.9em; margin-top: 20px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { padding: 10px 20px; background: rgba(255,255,255,0.1); border: none; border-radius: 8px; color: #fff; cursor: pointer; }
        .tab.active { background: #2196f3; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .task-progress { width: 100px; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; display: inline-block; vertical-align: middle; margin-right: 8px; }
        .task-progress-fill { height: 100%; background: linear-gradient(90deg, #00c853, #69f0ae); border-radius: 4px; transition: width 0.3s ease; }
        .task-status { padding: 4px 10px; border-radius: 12px; font-size: 0.85em; }
        .task-status.downloading { background: #2196f3; }
        .task-status.completed { background: #00c853; }
        .task-status.cancelled { background: #ff9800; }
        .task-status.failed { background: #ff5252; }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } h1 { font-size: 1.5em; } }
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
                <div class="card">
                    <h2>进程状态</h2>
                    <div class="stat-row"><span class="stat-label">运行状态</span><span class="stat-value" id="status">检测中...</span></div>
                    <div class="stat-row"><span class="stat-label">进程 PID</span><span class="stat-value" id="pid">-</span></div>
                    <div class="stat-row"><span class="stat-label">运行时长</span><span class="stat-value" id="uptime">-</span></div>
                </div>
                <div class="card">
                    <h2>资源占用</h2>
                    <div class="stat-row"><span class="stat-label">CPU 使用率</span><span class="stat-value" id="cpu">0%</span></div>
                    <div class="progress-bar"><div class="progress-fill" id="cpuBar" style="width: 0%"></div></div>
                    <div class="stat-row" style="margin-top: 15px;"><span class="stat-label">内存使用</span><span class="stat-value" id="memory">0 MB</span></div>
                    <div class="progress-bar"><div class="progress-fill" id="memBar" style="width: 0%"></div></div>
                    <div class="stat-row" style="margin-top: 15px;"><span class="stat-label">线程数 / 句柄数</span><span class="stat-value"><span id="threads">-</span> / <span id="handles">-</span></span></div>
                </div>
                <div class="card">
                    <h2>进程网络流量</h2>
                    <div class="stat-row"><span class="stat-label">下载速度</span><span class="speed-value" id="downloadSpeed">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">上传速度</span><span class="speed-value upload" id="uploadSpeed">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">总下载 / 总上传</span><span class="stat-value"><span id="totalDownload">0 MB</span> / <span id="totalUpload">0 MB</span></span></div>
                </div>
                <div class="card">
                    <h2>系统网络流量</h2>
                    <div class="stat-row"><span class="stat-label">系统下载</span><span class="speed-value" id="sysDownload">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">系统上传</span><span class="speed-value upload" id="sysUpload">0 KB/s</span></div>
                </div>
            </div>
            <div class="card">
                <h2>进程控制</h2>
                <div class="btn-group">
                    <button class="btn btn-success" onclick="controlProcess('start')">启动</button>
                    <button class="btn btn-danger" onclick="controlProcess('stop')">停止</button>
                    <button class="btn btn-warning" onclick="controlProcess('restart')">重启</button>
                </div>
            </div>
        </div>

        <div id="logs" class="tab-content">
            <div class="card">
                <h2>实时日志</h2>
                <div id="logViewer" class="log-viewer"></div>
            </div>
        </div>

        <div id="config" class="tab-content">
            <div class="card">
                <h2>配置文件 (config.toml)</h2>
                <textarea id="configEditor" class="config-editor"></textarea>
                <div class="btn-group">
                    <button class="btn btn-primary" onclick="saveConfig()">保存配置</button>
                </div>
            </div>
        </div>
        <p class="update-time">最后更新: <span id="lastUpdate"></span></p>
    </div>

    <script>
        let lastTotalDownload = 0;
        let lastTotalUpload = 0;
        let lastSysTotalDownload = 0;
        let lastSysTotalUpload = 0;
        let lastTime = Date.now();

        function showTab(tabName) {
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.style.display = 'none');
            document.querySelector(`button[onclick="showTab('${tabName}')"]`).classList.add('active');
            document.getElementById(tabName).style.display = 'block';
            if (tabName === 'config') fetchConfig();
            if (tabName === 'logs') fetchLogs();
        }

        function updateStatus(data) {
            const now = Date.now();
            const timeDiff = (now - lastTime) / 1000; // in seconds
            lastTime = now;

            document.getElementById('status').textContent = data.status;
            document.getElementById('pid').textContent = data.pid;
            document.getElementById('uptime').textContent = data.uptime;
            document.getElementById('cpu').textContent = `${data.cpu.toFixed(1)}%`;
            document.getElementById('memory').textContent = data.memory;
            document.getElementById('threads').textContent = data.threads;
            document.getElementById('handles').textContent = data.handles;
            document.getElementById('totalDownload').textContent = data.total_download;
            document.getElementById('totalUpload').textContent = data.total_upload;
            document.getElementById('sysDownload').textContent = data.sys_download;
            document.getElementById('sysUpload').textContent = data.sys_upload;
            document.getElementById('lastUpdate').textContent = new Date().toLocaleString();

            const statusBadge = document.getElementById('statusBadge');
            statusBadge.textContent = data.status;
            if (data.status === "运行中") {
                statusBadge.className = 'status-badge status-running';
            } else {
                statusBadge.className = 'status-badge status-stopped';
            }

            const cpuBar = document.getElementById('cpuBar');
            cpuBar.style.width = `${data.cpu}%`;
            cpuBar.className = 'progress-fill';
            if (data.cpu > 80) cpuBar.classList.add('danger');
            else if (data.cpu > 50) cpuBar.classList.add('warning');

            const memBar = document.getElementById('memBar');
            memBar.style.width = `${data.memory_percent}%`;
            memBar.className = 'progress-fill';
            if (data.memory_percent > 80) memBar.classList.add('danger');
            else if (data.memory_percent > 50) memBar.classList.add('warning');
        }

        function fetchStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => updateStatus(data))
                .catch(error => console.error('Error fetching status:', error));
        }

        function fetchConfig() {
            fetch('/api/config')
                .then(response => response.text())
                .then(text => {
                    document.getElementById('configEditor').value = text;
                })
                .catch(error => console.error('Error fetching config:', error));
        }

        function saveConfig() {
            const configContent = document.getElementById('configEditor').value;
            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'text/plain' },
                body: configContent
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                if (data.status === 'success') fetchConfig();
            })
            .catch(error => console.error('Error saving config:', error));
        }

        function fetchLogs() {
            fetch('/api/logs')
                .then(response => response.text())
                .then(text => {
                    const logViewer = document.getElementById('logViewer');
                    logViewer.textContent = text;
                    logViewer.scrollTop = logViewer.scrollHeight;
                })
                .catch(error => console.error('Error fetching logs:', error));
        }

        function controlProcess(action) {
            fetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action })
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                fetchStatus();
            })
            .catch(error => console.error('Error controlling process:', error));
        }

        setInterval(fetchStatus, 2000);
        setInterval(fetchLogs, 5000);
        document.addEventListener('DOMContentLoaded', () => {
            fetchStatus();
        });
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(html.encode('utf-8')))
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def send_json_status(self):
        """发送 JSON 状态"""
        global monitor_data
        monitor_data['last_update'] = datetime.now().isoformat()
        json_data = json.dumps(monitor_data)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json_data.encode('utf-8'))

    def send_config(self):
        """发送配置文件内容"""
        global config_path
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        else:
            self.send_error(404, "Config file not found")

    def save_config(self):
        """保存配置文件"""
        global config_path
        if not config_path:
            self.send_error(500, "Config path not set")
            return
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(post_data)
            response = {'status': 'success', 'message': '配置已成功保存'}
        except Exception as e:
            response = {'status': 'error', 'message': f'保存失败: {e}'}
        
        json_response = json.dumps(response)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json_response.encode('utf-8'))

    def send_logs(self):
        """发送日志"""
        global recent_logs
        log_content = "\n".join(recent_logs)
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(log_content.encode('utf-8'))

    def handle_control(self):
        """处理进程控制请求"""
        global control_callback
        if not control_callback:
            self.send_error(500, "Control callback not set")
            return
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
            action = post_data.get('action')
            message = control_callback(action)
            response = {'status': 'success', 'message': message}
        except Exception as e:
            response = {'status': 'error', 'message': f'操作失败: {e}'}
        
        json_response = json.dumps(response)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json_response.encode('utf-8'))

class MonitorApp(tk.Tk):
    """主监控应用"""
    def __init__(self):
        super().__init__()
        self.title("SaveAny-Bot Monitor")
        self.geometry("1024x768")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.process = None
        self.bot_path = None
        self.start_time = None
        self.monitoring = False
        self.log_capture_thread = None
        self.stop_log_capture = threading.Event()
        self.web_server_thread = None
        self.httpd = None
        self.log_queue = queue.Queue()

        # 设置样式
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.configure_styles()

        # 创建主框架
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 创建 Notebook
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # 创建各个 Tab
        self.create_monitor_tab()
        self.create_settings_tab()
        self.create_log_tab()
        self.create_web_tab()

        # 状态栏
        self.status_bar = ttk.Label(self, text="准备就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # 设置全局回调
        global control_callback
        control_callback = self.control_process_from_web

    def configure_styles(self):
        """配置 ttk 样式"""
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabel', background='#f0f0f0')
        self.style.configure('TButton', padding=6)
        self.style.configure('TNotebook', background='#f0f0f0', tabmargins=[2, 5, 2, 0])
        self.style.configure('TNotebook.Tab', padding=[10, 5], font=('Segoe UI', 10))
        self.style.map('TNotebook.Tab', background=[('selected', '#ffffff')], foreground=[('selected', '#0078d7')])
        self.style.configure('Status.TLabel', font=('Segoe UI', 11, 'bold'))
        self.style.configure('Running.Status.TLabel', foreground='green')
        self.style.configure('Stopped.Status.TLabel', foreground='red')
        self.style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'))

    def create_monitor_tab(self):
        """创建监控 Tab"""
        monitor_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(monitor_frame, text='状态监控')

        # 进程控制框架
        control_frame = ttk.LabelFrame(monitor_frame, text="进程控制", padding="10")
        control_frame.pack(fill=tk.X, pady=5)

        self.select_button = ttk.Button(control_frame, text="选择 SaveAny-Bot 程序", command=self.select_bot_path)
        self.select_button.pack(side=tk.LEFT, padx=5)
        self.start_button = ttk.Button(control_frame, text="启动", command=self.start_process, state=tk.DISABLED)
        self.start_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(control_frame, text="停止", command=self.stop_process, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        self.restart_button = ttk.Button(control_frame, text="重启", command=self.restart_process, state=tk.DISABLED)
        self.restart_button.pack(side=tk.LEFT, padx=5)

        # 状态显示框架
        status_grid = ttk.Frame(monitor_frame, padding="10")
        status_grid.pack(fill=tk.BOTH, expand=True, pady=5)
        status_grid.columnconfigure(1, weight=1)
        status_grid.columnconfigure(3, weight=1)

        self.create_status_label(status_grid, "程序路径:", 0, 0)
        self.bot_path_label = self.create_status_value(status_grid, "尚未选择", 0, 1, columnspan=3)

        self.create_status_label(status_grid, "运行状态:", 1, 0)
        self.status_label = self.create_status_value(status_grid, "未运行", 1, 1, style='Stopped.Status.TLabel')
        self.create_status_label(status_grid, "进程 PID:", 1, 2)
        self.pid_label = self.create_status_value(status_grid, "-", 1, 3)

        self.create_status_label(status_grid, "CPU 使用率:", 2, 0)
        self.cpu_label = self.create_status_value(status_grid, "0%", 2, 1)
        self.create_status_label(status_grid, "内存使用:", 2, 2)
        self.memory_label = self.create_status_value(status_grid, "0 MB", 2, 3)

        self.create_status_label(status_grid, "运行时长:", 3, 0)
        self.uptime_label = self.create_status_value(status_grid, "-", 3, 1)
        self.create_status_label(status_grid, "线程数/句柄数:", 3, 2)
        self.handles_label = self.create_status_value(status_grid, "- / -", 3, 3)

        # 进度条
        ttk.Label(status_grid, text="CPU:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.cpu_progress = ttk.Progressbar(status_grid, orient=tk.HORIZONTAL, length=200, mode='determinate')
        self.cpu_progress.grid(row=4, column=1, sticky=tk.EW, pady=5)
        ttk.Label(status_grid, text="内存:").grid(row=4, column=2, sticky=tk.W, pady=5)
        self.memory_progress = ttk.Progressbar(status_grid, orient=tk.HORIZONTAL, length=200, mode='determinate')
        self.memory_progress.grid(row=4, column=3, sticky=tk.EW, pady=5)

        # 网络流量框架
        net_frame = ttk.LabelFrame(monitor_frame, text="网络流量", padding="10")
        net_frame.pack(fill=tk.X, pady=5)
        net_frame.columnconfigure(1, weight=1)
        net_frame.columnconfigure(3, weight=1)

        self.create_status_label(net_frame, "下载/上传速度:", 0, 0)
        self.net_io_label = self.create_status_value(net_frame, "0 KB/s / 0 KB/s", 0, 1)
        self.create_status_label(net_frame, "总下载/上传:", 0, 2)
        self.net_total_label = self.create_status_value(net_frame, "0 MB / 0 MB", 0, 3)
        self.create_status_label(net_frame, "系统网络速度:", 1, 0)
        self.sys_net_io_label = self.create_status_value(net_frame, "0 KB/s / 0 KB/s", 1, 1)

    def create_status_label(self, parent, text, row, col):
        ttk.Label(parent, text=text).grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)

    def create_status_value(self, parent, text, row, col, columnspan=1, style='Status.TLabel'):
        label = ttk.Label(parent, text=text, style=style)
        label.grid(row=row, column=col, columnspan=columnspan, sticky=tk.W, padx=5, pady=2)
        return label

    def create_settings_tab(self):
        """创建设置 Tab"""
        settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(settings_frame, text='配置编辑')

        # 配置文件路径选择
        config_frame = ttk.LabelFrame(settings_frame, text="配置文件", padding="10")
        config_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(config_frame, text="配置文件路径:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.config_path_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.config_path_var, width=60).grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)
        ttk.Button(config_frame, text="浏览", command=self.browse_config_path).grid(row=0, column=2, padx=5, pady=2)

        # 创建一个子Notebook用于分类设置
        settings_notebook = ttk.Notebook(settings_frame)
        settings_notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        # Telegram 设置
        telegram_tab = ttk.Frame(settings_notebook, padding="10")
        settings_notebook.add(telegram_tab, text='Telegram')
        self.create_telegram_settings(telegram_tab)

        # 存储设置
        storage_tab = ttk.Frame(settings_notebook, padding="10")
        settings_notebook.add(storage_tab, text='存储')
        self.create_storage_settings(storage_tab)

        # 下载设置
        downloader_tab = ttk.Frame(settings_notebook, padding="10")
        settings_notebook.add(downloader_tab, text='下载')
        self.create_downloader_settings(downloader_tab)

        # 其他设置
        misc_tab = ttk.Frame(settings_notebook, padding="10")
        settings_notebook.add(misc_tab, text='其他')
        self.create_misc_settings(misc_tab)

    def create_telegram_settings(self, parent):
        """创建 Telegram 设置界面"""
        # API Token
        ttk.Label(parent, text="Bot Token:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.token_entry = ttk.Entry(parent, width=50)
        self.token_entry.grid(row=0, column=1, sticky=tk.EW, pady=5)

        # Admin Users
        ttk.Label(parent, text="Admin Users (逗号分隔):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.admins_entry = ttk.Entry(parent, width=50)
        self.admins_entry.grid(row=1, column=1, sticky=tk.EW, pady=5)

        # Allowed Users
        ttk.Label(parent, text="Allowed Users (逗号分隔):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.allowed_users_entry = ttk.Entry(parent, width=50)
        self.allowed_users_entry.grid(row=2, column=1, sticky=tk.EW, pady=5)

        # Proxy
        proxy_frame = ttk.LabelFrame(parent, text="代理", padding="10")
        proxy_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=10)
        self.proxy_enable_var = tk.BooleanVar()
        ttk.Checkbutton(proxy_frame, text="启用代理", variable=self.proxy_enable_var).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(proxy_frame, text="URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.proxy_url_entry = ttk.Entry(proxy_frame, width=40)
        self.proxy_url_entry.grid(row=1, column=1, sticky=tk.EW, pady=5)

        # 保存按钮
        ttk.Button(parent, text="保存 Telegram 设置", command=self.save_telegram_settings).grid(row=4, column=1, sticky=tk.E, pady=10)

    def create_storage_settings(self, parent):
        """创建存储设置界面"""
        # 仅支持第一个 [[storages]] 的编辑
        ttk.Label(parent, text="注意: 仅支持编辑第一个存储配置", foreground="blue").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(parent, text="名称:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.storage_name_entry = ttk.Entry(parent, width=40)
        self.storage_name_entry.grid(row=1, column=1, sticky=tk.EW, pady=5)

        ttk.Label(parent, text="类型:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.storage_type_var = tk.StringVar()
        storage_types = ["local", "s3", "oss", "gdrive", "onedrive"]
        self.storage_type_menu = ttk.Combobox(parent, textvariable=self.storage_type_var, values=storage_types, state="readonly")
        self.storage_type_menu.grid(row=2, column=1, sticky=tk.EW, pady=5)

        self.storage_enable_var = tk.BooleanVar()
        ttk.Checkbutton(parent, text="启用", variable=self.storage_enable_var).grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(parent, text="基础路径 (base_path):").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.storage_path_entry = ttk.Entry(parent, width=40)
        self.storage_path_entry.grid(row=4, column=1, sticky=tk.EW, pady=5)

        ttk.Label(parent, text="并发任务数 (concurrent_tasks):").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.concurrent_tasks_entry = ttk.Entry(parent, width=10)
        self.concurrent_tasks_entry.grid(row=5, column=1, sticky=tk.W, pady=5)

        ttk.Label(parent, text="缓存路径 (cache_path):").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.cache_path_entry = ttk.Entry(parent, width=40)
        self.cache_path_entry.grid(row=6, column=1, sticky=tk.EW, pady=5)

        ttk.Button(parent, text="保存存储设置", command=self.save_storage_settings).grid(row=7, column=1, sticky=tk.E, pady=10)

    def create_downloader_settings(self, parent):
        """创建下载设置界面"""
        ttk.Label(parent, text="下载设置正在开发中...").pack(pady=20)

    def create_misc_settings(self, parent):
        """创建其他设置界面"""
        ttk.Label(parent, text="其他设置正在开发中...").pack(pady=20)

    def create_log_tab(self):
        """创建日志 Tab"""
        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text='实时日志')

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def create_web_tab(self):
        """创建 Web 访问 Tab"""
        web_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(web_frame, text='Web 监控')

        web_control_frame = ttk.Frame(web_frame)
        web_control_frame.pack(fill=tk.X, pady=5)

        ttk.Label(web_control_frame, text="端口:").pack(side=tk.LEFT, padx=5)
        self.web_port_entry = ttk.Entry(web_control_frame, width=10)
        self.web_port_entry.insert(0, "8080")
        self.web_port_entry.pack(side=tk.LEFT, padx=5)

        self.web_start_button = ttk.Button(web_control_frame, text="启动 Web 服务", command=self.start_web_server)
        self.web_start_button.pack(side=tk.LEFT, padx=5)
        self.web_stop_button = ttk.Button(web_control_frame, text="停止 Web 服务", command=self.stop_web_server, state=tk.DISABLED)
        self.web_stop_button.pack(side=tk.LEFT, padx=5)

        self.web_status_label = ttk.Label(web_frame, text="Web 服务未运行", foreground="red")
        self.web_status_label.pack(pady=10)

        self.web_link_label = ttk.Label(web_frame, text="", foreground="blue", cursor="hand2")
        self.web_link_label.pack(pady=5)
        self.web_link_label.bind("<Button-1>", lambda e: webbrowser.open(self.web_link_label.cget("text")))

    def select_bot_path(self):
        """选择 SaveAny-Bot 主程序路径"""
        path = filedialog.askopenfilename(
            title="选择 SaveAny-Bot 主程序",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if path:
            self.bot_path = path
            self.bot_path_label.config(text=self.bot_path)
            self.start_button.config(state=tk.NORMAL)
            self.status_bar.config(text=f"已选择程序: {self.bot_path}")
            
            # 自动查找配置文件
            dir_path = os.path.dirname(path)
            potential_config_path = os.path.join(dir_path, "config.toml")
            if os.path.exists(potential_config_path):
                global config_path
                config_path = potential_config_path
                self.config_path_var.set(config_path)
                self.status_bar.config(text=f"已加载配置文件: {config_path}")
                self.load_config_to_ui()
            else:
                messagebox.showwarning("警告", "在程序同目录下未找到 config.toml 文件。")
                
    def browse_config_path(self):
        """浏览选择配置文件路径"""
        path = filedialog.askopenfilename(
            title="选择配置文件",
            filetypes=[("配置文件", "*.toml"), ("所有文件", "*.*")]
        )
        if path:
            global config_path
            config_path = path
            self.config_path_var.set(config_path)
            self.status_bar.config(text=f"已加载配置文件: {config_path}")
            self.load_config_to_ui()

    def load_config_to_ui(self):
        """加载配置到设置界面"""
        global config_path
        if not config_path or not os.path.exists(config_path):
            return

        try:
            # 尝试导入 TOML 解析库
            try:
                import tomllib
                with open(config_path, 'rb') as f:
                    config = tomllib.load(f)
            except ImportError:
                try:
                    import toml
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = toml.load(f)
                except ImportError:
                    # 如果没有 TOML 库，使用正则表达式作为后备
                    with open(config_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    import re

                    # 加载 Telegram 设置
                    token_match = re.search(r'token\s*=\s*["\']([^"\']*)["\']', content)
                    if token_match:
                        self.token_entry.delete(0, tk.END)
                        self.token_entry.insert(0, token_match.group(1))

                    admins_match = re.search(r'admin_users\s*=\s*\[([^\]]*)\]', content)
                    if admins_match:
                        admins = admins_match.group(1).replace('"', '').replace("'", '').strip()
                        self.admins_entry.delete(0, tk.END)
                        self.admins_entry.insert(0, admins)

                    allowed_users_match = re.search(r'allowed_users\s*=\s*\[([^\]]*)\]', content)
                    if allowed_users_match:
                        allowed = allowed_users_match.group(1).replace('"', '').replace("'", '').strip()
                        self.allowed_users_entry.delete(0, tk.END)
                        self.allowed_users_entry.insert(0, allowed)

                    proxy_enable_match = re.search(r'\[telegram\.proxy\][\s\S]*?enable\s*=\s*(true|false)', content, re.IGNORECASE)
                    if proxy_enable_match:
                        self.proxy_enable_var.set(proxy_enable_match.group(1).lower() == 'true')

                    proxy_url_match = re.search(r'\[telegram\.proxy\][\s\S]*?url\s*=\s*["\']([^"\']*)["\']', content)
                    if proxy_url_match:
                        self.proxy_url_entry.delete(0, tk.END)
                        self.proxy_url_entry.insert(0, proxy_url_match.group(1))

                    # 加载存储设置 (第一个)
                    storage_match = re.search(r'\[\[storages\]\]([\s\S]*?)(?=\n\[\[storages\]\]|\Z)', content)
                    if storage_match:
                        storage_block = storage_match.group(1)
                        name_match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', storage_block)
                        if name_match: self.storage_name_entry.insert(0, name_match.group(1))
                        
                        type_match = re.search(r'type\s*=\s*["\']([^"\']*)["\']', storage_block)
                        if type_match: self.storage_type_var.set(type_match.group(1))

                        enable_match = re.search(r'enable\s*=\s*(true|false)', storage_block, re.IGNORECASE)
                        if enable_match: self.storage_enable_var.set(enable_match.group(1).lower() == 'true')

                        path_match = re.search(r'base_path\s*=\s*["\']([^"\']*)["\']', storage_block)
                        if path_match: self.storage_path_entry.insert(0, path_match.group(1))

                        tasks_match = re.search(r'concurrent_tasks\s*=\s*(\d+)', storage_block)
                        if tasks_match: self.concurrent_tasks_entry.insert(0, tasks_match.group(1))

                        cache_match = re.search(r'cache_path\s*=\s*["\']([^"\']*)["\']', storage_block)
                        if cache_match: self.cache_path_entry.insert(0, cache_match.group(1))
                    return

            # 使用 TOML 库加载配置
            # 加载 Telegram 设置
            if 'telegram' in config:
                telegram_config = config['telegram']
                if 'token' in telegram_config:
                    self.token_entry.delete(0, tk.END)
                    self.token_entry.insert(0, telegram_config['token'])
                if 'admin_users' in telegram_config:
                    admins = ', '.join(map(str, telegram_config['admin_users']))
                    self.admins_entry.delete(0, tk.END)
                    self.admins_entry.insert(0, admins)
                if 'allowed_users' in telegram_config:
                    allowed = ', '.join(map(str, telegram_config['allowed_users']))
                    self.allowed_users_entry.delete(0, tk.END)
                    self.allowed_users_entry.insert(0, allowed)
                if 'proxy' in telegram_config:
                    proxy_config = telegram_config['proxy']
                    if 'enable' in proxy_config:
                        self.proxy_enable_var.set(proxy_config['enable'])
                    if 'url' in proxy_config:
                        self.proxy_url_entry.delete(0, tk.END)
                        self.proxy_url_entry.insert(0, proxy_config['url'])

            # 加载存储设置 (第一个)
            if 'storages' in config and config['storages']:
                storage_config = config['storages'][0]
                if 'name' in storage_config:
                    self.storage_name_entry.delete(0, tk.END)
                    self.storage_name_entry.insert(0, storage_config['name'])
                if 'type' in storage_config:
                    self.storage_type_var.set(storage_config['type'])
                if 'enable' in storage_config:
                    self.storage_enable_var.set(storage_config['enable'])
                if 'base_path' in storage_config:
                    self.storage_path_entry.delete(0, tk.END)
                    self.storage_path_entry.insert(0, storage_config['base_path'])
                if 'concurrent_tasks' in storage_config:
                    self.concurrent_tasks_entry.delete(0, tk.END)
                    self.concurrent_tasks_entry.insert(0, str(storage_config['concurrent_tasks']))
                if 'cache_path' in storage_config:
                    self.cache_path_entry.delete(0, tk.END)
                    self.cache_path_entry.insert(0, storage_config['cache_path'])

        except Exception as e:
            messagebox.showerror("错误", f"加载配置文件失败: {e}")

    def save_telegram_settings(self):
        """保存 Telegram 相关设置"""
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            token = self.token_entry.get().strip()
            admins = self.admins_entry.get().strip()
            allowed_users = self.allowed_users_entry.get().strip()
            proxy_enable = 'true' if self.proxy_enable_var.get() else 'false'
            proxy_url = self.proxy_url_entry.get().strip()

            # 更新 token
            content = re.sub(r'(token\s*=\s*)["\'][^"\']*["\']', f'\1"{token}"', content)
            # 更新 admin_users
            admins_formatted = ', '.join([f'"{user.strip()}"' for user in admins.split(',') if user.strip()])
            content = re.sub(r'(admin_users\s*=\s*)\[[^\]]*\]', f'\1[{admins_formatted}]', content)
            # 更新 allowed_users
            allowed_formatted = ', '.join([f'"{user.strip()}"' for user in allowed_users.split(',') if user.strip()])
            content = re.sub(r'(allowed_users\s*=\s*)\[[^\]]*\]', f'\1[{allowed_formatted}]', content)

            # 更新 proxy
            if re.search(r'\[telegram\.proxy\]', content):
                # 更新现有配置
                content = re.sub(
                    r'(\[telegram\.proxy\][\s\S]*?enable\s*=\s*)(true|false)',
                    f'\1{proxy_enable}',
                    content,
                    flags=re.IGNORECASE
                )
                content = re.sub(
                    r'(\[telegram\.proxy\][\s\S]*?url\s*=\s*)["\'][^"\']*["\']',
                    f'\1"{proxy_url}"',
                    content
                )
            else:
                # 添加新配置
                proxy_config = f'''
[telegram.proxy]
enable = {proxy_enable}
url = "{proxy_url}"
'''
                content = content.replace('[telegram]', '[telegram]' + proxy_config, 1)

            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            messagebox.showinfo("成功", "Telegram 设置已保存")

        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def save_storage_settings(self):
        """保存存储设置到配置文件"""
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            name = self.storage_name_entry.get().strip()
            storage_type = self.storage_type_var.get()
            enable = 'true' if self.storage_enable_var.get() else 'false'
            base_path = self.storage_path_entry.get().strip()
            concurrent_tasks = self.concurrent_tasks_entry.get().strip() or "3"
            cache_path = self.cache_path_entry.get().strip()
            
            import re
            # 检查是否已存在 [[storages]] 部分
            if re.search(r'\[\[storages\]\]', content):
                # 更新第一个 storages 配置
                content = re.sub(
                    r'(\[\[storages\]\][\s\S]*?name\s*=\s*)["\']([^"\']*)["\']',
                    lambda m: f'{m.group(1)}"{name}"',
                    content,
                    count=1
                )
                content = re.sub(
                    r'(\[\[storages\]\][\s\S]*?type\s*=\s*)["\']([^"\']*)["\']',
                    lambda m: f'{m.group(1)}"{storage_type}"',
                    content,
                    count=1
                )
                content = re.sub(
                    r'(\[\[storages\]\][\s\S]*?enable\s*=\s*)(true|false)',
                    lambda m: f'{m.group(1)}{enable}',
                    content,
                    count=1,
                    flags=re.IGNORECASE
                )
                content = re.sub(
                    r'(\[\[storages\]\][\s\S]*?base_path\s*=\s*)["\']([^"\']*)["\']',
                    lambda m: f'{m.group(1)}"{base_path}"',
                    content,
                    count=1
                )
                # 添加或更新 concurrent_tasks
                if re.search(r'concurrent_tasks\s*=', content):
                    content = re.sub(
                        r'(concurrent_tasks\s*=\s*)\d+',
                        lambda m: f'{m.group(1)}{concurrent_tasks}',
                        content,
                        count=1
                    )
                else:
                    content = re.sub(
                        r'(base_path\s*=\s*["\'][^"\']*["\'])',
                        lambda m: f'{m.group(1)}\nconcurrent_tasks = {concurrent_tasks}',
                        content,
                        count=1
                    )
                # 添加或更新 cache_path
                if re.search(r'cache_path\s*=', content):
                    content = re.sub(
                        r'(cache_path\s*=\s*)["\']([^"\']*)["\']',
                        lambda m: f'{m.group(1)}"{cache_path}"',
                        content,
                        count=1
                    )
                else:
                    content = re.sub(
                        r'(concurrent_tasks\s*=\s*\d+)',
                        lambda m: f'{m.group(1)}\ncache_path = "{cache_path}"',
                        content,
                        count=1
                    )
            else:
                # 添加新配置
                storage_config = f'''
[[storages]]
name = "{name}"
type = "{storage_type}"
enable = {enable}
base_path = "{base_path}"
concurrent_tasks = {concurrent_tasks}
cache_path = "{cache_path}"
'''
                content += storage_config

            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)

            messagebox.showinfo("成功", "存储设置已保存")

        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def start_process(self):
        """启动 SaveAny-Bot 进程"""
        if self.monitoring:
            messagebox.showinfo("提示", "监控已在运行中")
            return
        if not self.bot_path or not os.path.exists(self.bot_path):
            messagebox.showerror("错误", "无效的程序路径")
            return

        try:
            # 直接启动进程，使用 CREATE_NO_WINDOW 标志避免弹出命令行窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.process = subprocess.Popen(
                [self.bot_path],
                cwd=os.path.dirname(self.bot_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo
            )
            time.sleep(2) # 等待进程启动
            
            # 验证进程是否正在运行
            if not self.process.poll() is None:
                raise RuntimeError("进程启动失败")

            # 保存 stdout 和 stderr 流
            stdout_stream = self.process.stdout
            stderr_stream = self.process.stderr
            
            # 获取进程信息
            self.process = psutil.Process(self.process.pid)
            self.start_time = datetime.fromtimestamp(self.process.create_time())
            self.monitoring = True
            self.update_button_states()
            self.status_bar.config(text="监控已启动")
            self.update_info()
            
            # 启动日志捕获
            self.stop_log_capture.clear()
            self.log_capture_thread = threading.Thread(target=self.capture_logs, args=(stdout_stream, stderr_stream), daemon=True)
            self.log_capture_thread.start()
            self.process_log_queue()

        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            self.process = None

    def stop_process(self):
        """停止 SaveAny-Bot 进程"""
        if not self.monitoring or not self.process:
            messagebox.showinfo("提示", "程序未在运行")
            return
        try:
            # 优雅地结束进程树
            parent = self.process
            children = parent.children(recursive=True)
            for child in children:
                child.terminate()
            parent.terminate()
            gone, alive = psutil.wait_procs([parent] + children, timeout=3)
            for p in alive:
                p.kill()
            
            self.monitoring = False
            self.start_time = None
            self.update_button_states()
            self.reset_labels()
            self.status_bar.config(text="监控已停止")
            self.stop_log_capture.set()
        except psutil.NoSuchProcess:
            self.status_bar.config(text="进程已不存在")
        except Exception as e:
            messagebox.showerror("停止失败", str(e))
        finally:
            self.monitoring = False
            self.process = None
            self.update_button_states()
            self.reset_labels()

    def restart_process(self):
        """重启进程"""
        self.stop_process()
        time.sleep(2)
        self.start_process()

    def control_process_from_web(self, action):
        """从 Web 界面控制进程"""
        if action == 'start':
            if not self.monitoring:
                self.after(0, self.start_process)
                return "正在启动..."
            return "已在运行中"
        elif action == 'stop':
            if self.monitoring:
                self.after(0, self.stop_process)
                return "正在停止..."
            return "已停止"
        elif action == 'restart':
            self.after(0, self.restart_process)
            return "正在重启..."
        return "未知操作"

    def update_info(self):
        """更新监控信息"""
        if not self.monitoring or not self.process or not self.process.is_running():
            if self.monitoring: # 如果之前在监控，但现在进程没了
                self.stop_process()
            return

        try:
            with self.process.oneshot():
                # CPU
                cpu_percent = self.process.cpu_percent()
                self.cpu_label.config(text=f"{cpu_percent:.1f}%")
                self.cpu_progress['value'] = cpu_percent
                monitor_data['cpu'] = cpu_percent

                # Memory
                mem_info = self.process.memory_info()
                mem_mb = mem_info.rss / 1024 / 1024
                self.memory_label.config(text=f"{mem_mb:.2f} MB")
                mem_percent = self.process.memory_percent()
                self.memory_progress['value'] = mem_percent
                monitor_data['memory'] = f"{mem_mb:.2f} MB"
                monitor_data['memory_percent'] = mem_percent

                # Other info
                num_threads = self.process.num_threads()
                num_handles = self.process.num_handles() if sys.platform == 'win32' else 'N/A'
                self.handles_label.config(text=f"{num_threads} / {num_handles}")
                monitor_data['threads'] = num_threads
                monitor_data['handles'] = num_handles

                # Uptime
                uptime = datetime.now() - self.start_time
                uptime_str = str(uptime).split('.')[0]
                self.uptime_label.config(text=uptime_str)
                monitor_data['uptime'] = uptime_str

            # Network
            self.update_network_info()
            
            monitor_data['status'] = "运行中"
            monitor_data['pid'] = self.process.pid

        except psutil.NoSuchProcess:
            self.stop_process()
        except Exception as e:
            # 记录错误但不停止监控
            self.status_bar.config(text=f"更新信息时出错: {e}")

        self.after(2000, self.update_info)

    def update_network_info(self):
        """更新网络流量信息"""
        try:
            # 进程网络IO - Windows 不支持获取单个进程的网络IO
            if not hasattr(self, 'last_net_time'):
                self.last_net_time = time.time()
            
            time_delta = time.time() - self.last_net_time
            if time_delta > 0:
                # 使用占位符表示进程级网络IO在Windows上不可用
                self.net_io_label.config(text="N/A (Windows)")
                monitor_data['download_speed'] = "N/A (Windows)"
                monitor_data['upload_speed'] = "N/A (Windows)"
            
            self.net_total_label.config(text="N/A (Windows)")
            monitor_data['total_download'] = "N/A (Windows)"
            monitor_data['total_upload'] = "N/A (Windows)"
            self.last_net_time = time.time()

            # 系统网络IO
            sys_io = psutil.net_io_counters()
            total_sent = sys_io.bytes_sent
            total_recv = sys_io.bytes_recv

            if not hasattr(self, 'last_sys_io'):
                self.last_sys_io = (total_recv, total_sent, time.time())

            last_recv, last_sent, last_time_sys = self.last_sys_io
            time_delta_sys = time.time() - last_time_sys

            if time_delta_sys > 0:
                recv_speed = (total_recv - last_recv) / time_delta_sys
                sent_speed = (total_sent - last_sent) / time_delta_sys
                self.sys_net_io_label.config(text=f"{recv_speed/1024:.2f} KB/s / {sent_speed/1024:.2f} KB/s")
                monitor_data['sys_download'] = f"{recv_speed/1024:.2f} KB/s"
                monitor_data['sys_upload'] = f"{sent_speed/1024:.2f} KB/s"

            self.last_sys_io = (total_recv, total_sent, time.time())

        except Exception as e:
            # 记录错误但继续运行
            self.status_bar.config(text=f"更新网络信息时出错: {e}")
            # 重置为默认值
            self.net_io_label.config(text="0 KB/s / 0 KB/s")
            self.net_total_label.config(text="0 MB / 0 MB")
            self.sys_net_io_label.config(text="0 KB/s / 0 KB/s")

    def capture_logs(self, stdout_stream, stderr_stream):
        """捕获子进程的 stdout 和 stderr"""
        for stream in [stdout_stream, stderr_stream]:
            if stream:
                threading.Thread(target=self.read_stream, args=(stream,), daemon=True).start()

    def read_stream(self, stream):
        """从流中读取日志行"""
        while not self.stop_log_capture.is_set():
            try:
                line = stream.readline()
                if not line:
                    break
                self.log_queue.put(line.strip())
            except Exception:
                break

    def process_log_queue(self):
        """处理日志队列并更新UI"""
        try:
            # 处理队列中的所有日志
            while True:
                try:
                    line = self.log_queue.get_nowait()
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, line + '\n')
                    self.log_text.see(tk.END)
                    self.log_text.config(state=tk.DISABLED)
                    recent_logs.append(line)
                    # 标记任务为完成
                    self.log_queue.task_done()
                except queue.Empty:
                    break
        except Exception as e:
            # 记录错误但继续运行
            self.status_bar.config(text=f"处理日志队列时出错: {e}")
        finally:
            if self.monitoring:
                # 即使队列为空，也要继续检查
                self.after(100, self.process_log_queue)

    def update_button_states(self):
        """更新按钮状态"""
        if self.monitoring:
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.restart_button.config(state=tk.NORMAL)
            self.select_button.config(state=tk.DISABLED)
            self.status_label.config(text="运行中", style='Running.Status.TLabel')
            self.pid_label.config(text=str(self.process.pid))
        else:
            self.start_button.config(state=tk.NORMAL if self.bot_path else tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            self.restart_button.config(state=tk.DISABLED)
            self.select_button.config(state=tk.NORMAL)
            self.status_label.config(text="未运行", style='Stopped.Status.TLabel')

    def reset_labels(self):
        """重置监控标签"""
        self.pid_label.config(text="-")
        self.cpu_label.config(text="0%")
        self.memory_label.config(text="0 MB")
        self.uptime_label.config(text="-")
        self.handles_label.config(text="- / -")
        self.net_io_label.config(text="0 KB/s / 0 KB/s")
        self.net_total_label.config(text="0 MB / 0 MB")
        self.sys_net_io_label.config(text="0 KB/s / 0 KB/s")
        self.cpu_progress['value'] = 0
        self.memory_progress['value'] = 0
        global monitor_data
        monitor_data = {k: (0 if isinstance(v, (int, float)) else ("-" if k not in ["status", "memory", "download_speed", "upload_speed", "total_download", "total_upload", "sys_download", "sys_upload", "last_update"] else "0 MB" if "MB" in str(v) else "0 KB/s" if "KB/s" in str(v) else "" if k == "last_update" else "未运行")) for k, v in monitor_data.items()}

    def start_web_server(self):
        """启动 Web 服务器"""
        if self.web_server_thread and self.web_server_thread.is_alive():
            messagebox.showinfo("提示", "Web 服务已在运行")
            return
        try:
            port = int(self.web_port_entry.get())
            self.httpd = StoppableHTTPServer(("", port), MonitorHTTPHandler)
            self.web_server_thread = threading.Thread(target=self.httpd.serve_forever_stoppable, daemon=True)
            self.web_server_thread.start()
            
            ip_address = self.get_ip_address()
            url = f"http://{ip_address}:{port}"
            self.web_status_label.config(text=f"Web 服务运行于: {url}", foreground="green")
            self.web_link_label.config(text=url)
            self.web_start_button.config(state=tk.DISABLED)
            self.web_stop_button.config(state=tk.NORMAL)
        except Exception as e:
            messagebox.showerror("错误", f"启动 Web 服务失败: {e}")

    def stop_web_server(self):
        """停止 Web 服务器"""
        if self.httpd:
            try:
                self.httpd.stop()
                # 等待线程结束，但设置超时
                if self.web_server_thread and self.web_server_thread.is_alive():
                    self.web_server_thread.join(timeout=3)
                    # 如果线程仍在运行，记录警告
                    if self.web_server_thread.is_alive():
                        self.status_bar.config(text="Web 服务器线程可能未完全停止")
                self.httpd = None
                self.web_status_label.config(text="Web 服务未运行", foreground="red")
                self.web_link_label.config(text="")
                self.web_start_button.config(state=tk.NORMAL)
                self.web_stop_button.config(state=tk.DISABLED)
            except Exception as e:
                self.status_bar.config(text=f"停止 Web 服务器时出错: {e}")
                self.web_status_label.config(text="Web 服务停止出错", foreground="orange")
                self.web_start_button.config(state=tk.NORMAL)
                self.web_stop_button.config(state=tk.DISABLED)

    def get_ip_address(self):
        """获取本机IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def on_closing(self):
        """关闭窗口时的处理"""
        if self.monitoring:
            if messagebox.askyesno("退出", "监控正在运行，确定要退出吗？\n这将停止 SaveAny-Bot 进程。"):
                self.stop_process()
                self.stop_web_server()
                self.destroy()
        else:
            self.stop_web_server()
            self.destroy()

if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()
