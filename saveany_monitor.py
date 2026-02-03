#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SaveAny-Bot Monitor v2.7.1
监控 SaveAny-Bot 的运行状态、资源占用和网络流量
支持配置文件编辑、Web 网页查看、日志捕获
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
                    <div class="stat-row" style="margin-top: 10px;"><span class="stat-label">累计下载</span><span class="stat-value" id="totalDownload">0 MB</span></div>
                    <div class="stat-row"><span class="stat-label">累计上传</span><span class="stat-value" id="totalUpload">0 MB</span></div>
                </div>
                <div class="card">
                    <h2>系统整体网络</h2>
                    <div class="stat-row"><span class="stat-label">系统下载</span><span class="speed-value" id="sysDownload">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">系统上传</span><span class="speed-value upload" id="sysUpload">0 KB/s</span></div>
                </div>
                <div class="card">
                    <h2>进程控制</h2>
                    <div class="btn-group">
                        <button class="btn btn-success" onclick="controlProcess('start')">启动进程</button>
                        <button class="btn btn-danger" onclick="controlProcess('stop')">停止进程</button>
                        <button class="btn btn-warning" onclick="controlProcess('restart')">重启进程</button>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="logs" class="tab-content">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h2>实时日志 (最近500行)</h2>
                    <button class="btn btn-primary" onclick="loadLogs()">手动刷新</button>
                </div>
                <div id="logViewer" class="log-viewer">正在加载日志...</div>
            </div>
        </div>
        
        <div id="config" class="tab-content">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h2>配置文件 (config.toml)</h2>
                    <button class="btn btn-success" onclick="saveConfig()">保存配置</button>
                </div>
                <textarea id="configEditor" class="config-editor" spellcheck="false">正在加载配置...</textarea>
            </div>
        </div>
        
        <div class="update-time">最后更新: <span id="lastUpdate">-</span></div>
    </div>

    <script>
        function showTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            event.target.classList.add('active');
            
            if (tabId === 'config') loadConfig();
            if (tabId === 'logs') loadLogs();
        }

        async function updateStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                document.getElementById('status').textContent = data.status;
                document.getElementById('pid').textContent = data.pid;
                document.getElementById('uptime').textContent = data.uptime;
                document.getElementById('cpu').textContent = data.cpu + '%';
                document.getElementById('cpuBar').style.width = data.cpu + '%';
                document.getElementById('memory').textContent = data.memory;
                document.getElementById('memBar').style.width = data.memory_percent + '%';
                document.getElementById('threads').textContent = data.threads;
                document.getElementById('handles').textContent = data.handles;
                document.getElementById('downloadSpeed').textContent = data.download_speed;
                document.getElementById('uploadSpeed').textContent = data.upload_speed;
                document.getElementById('totalDownload').textContent = data.total_download;
                document.getElementById('totalUpload').textContent = data.total_upload;
                document.getElementById('sysDownload').textContent = data.sys_download;
                document.getElementById('sysUpload').textContent = data.sys_upload;
                document.getElementById('lastUpdate').textContent = data.last_update;
                
                const badge = document.getElementById('statusBadge');
                if (data.status === '运行中') {
                    badge.textContent = '运行中';
                    badge.className = 'status-badge status-running';
                } else {
                    badge.textContent = '未运行';
                    badge.className = 'status-badge status-stopped';
                }
            } catch (e) { console.error('Update failed', e); }
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();
                document.getElementById('configEditor').value = data.content;
            } catch (e) { alert('加载配置失败'); }
        }

        async function saveConfig() {
            const content = document.getElementById('configEditor').value;
            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'content=' + encodeURIComponent(content)
                });
                const result = await response.json();
                alert(result.message);
            } catch (e) { alert('保存失败'); }
        }

        async function loadLogs() {
            try {
                const response = await fetch('/api/logs');
                const data = await response.json();
                const viewer = document.getElementById('logViewer');
                viewer.textContent = data.logs.join('\\n');
                viewer.scrollTop = viewer.scrollHeight;
            } catch (e) { console.error('Load logs failed', e); }
        }

        async function controlProcess(action) {
            try {
                const response = await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'action=' + action
                });
                const result = await response.json();
                alert(result.message);
                setTimeout(updateStatus, 1000);
            } catch (e) { alert('操作失败'); }
        }

        setInterval(updateStatus, 2000);
        updateStatus();
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def send_json_status(self):
        """发送 JSON 状态数据"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(monitor_data).encode('utf-8'))
    
    def send_config(self):
        """发送配置文件内容"""
        global config_path
        content = ""
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                content = f"读取失败: {str(e)}"
        else:
            content = "配置文件未找到，请先在桌面程序中选择 SaveAny-Bot 路径"
            
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"content": content}).encode('utf-8'))
    
    def save_config(self):
        """保存配置文件内容"""
        global config_path
        content_len = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_len).decode('utf-8')
        params = parse_qs(post_data)
        new_content = params.get('content', [''])[0]
        
        result = {"success": False, "message": ""}
        
        if config_path and os.path.exists(config_path):
            try:
                # 备份
                with open(config_path + ".bak", 'w', encoding='utf-8') as f:
                    f.write(open(config_path, 'r', encoding='utf-8').read())
                # 保存
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                result = {"success": True, "message": "配置已保存，重启进程后生效"}
            except Exception as e:
                result = {"success": False, "message": f"保存失败: {str(e)}"}
        else:
            result = {"success": False, "message": "配置文件路径无效"}
            
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode('utf-8'))
    
    def send_logs(self):
        """发送日志内容"""
        global recent_logs
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"logs": list(recent_logs)}).encode('utf-8'))
    
    def handle_control(self):
        """处理进程控制请求"""
        content_len = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_len).decode('utf-8')
        params = parse_qs(post_data)
        action = params.get('action', [''])[0]
        
        message = "未知操作"
        if control_callback:
            message = control_callback(action)
            
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"message": message}).encode('utf-8'))


class SaveAnyMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("SaveAny-Bot Monitor v2.7.1")
        self.root.geometry("800x700")
        self.root.minsize(700, 600)
        
        # 设置全局回调用于 Web 控制
        global control_callback
        control_callback = self.handle_web_control
        
        self.target_process = "saveany-bot.exe"
        self.target_path = ""
        self.running = True
        self.process = None
        self.update_interval = 2000
        
        # 统计数据
        self.last_net_io = psutil.net_io_counters()
        self.last_net_time = time.time()
        self.proc_last_io = None
        self.proc_last_time = None
        
        # 日志相关
        self.log_file = None
        self.log_queue = queue.Queue()
        
        # Web 服务相关
        self.web_server = None
        self.web_thread = None
        self.web_port = 8080
        
        self.setup_ui()
        self.start_monitoring()
        
        # 启动日志处理队列
        self.process_log_queue()
        
        # 尝试自动查找进程
        self.root.after(1000, self.auto_detect_process)

    def setup_ui(self):
        # 创建主容器
        self.main_container = ttk.Frame(self.root, padding="10")
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # 顶部：路径选择
        path_frame = ttk.LabelFrame(self.main_container, text="程序设置", padding="10")
        path_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(path_frame, text="SaveAny-Bot 路径:").pack(side=tk.LEFT)
        self.path_label = ttk.Label(path_frame, text="未选择", foreground="gray", width=50)
        self.path_label.pack(side=tk.LEFT, padx=10)
        ttk.Button(path_frame, text="选择程序", command=self.browse_exe).pack(side=tk.RIGHT)
        
        # 创建选项卡
        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # 选项卡1：监控
        self.monitor_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.monitor_tab, text=" 实时监控 ")
        self.create_monitor_tab(self.monitor_tab)
        
        # 选项卡2：日志控制台
        self.console_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.console_tab, text=" 日志控制台 ")
        self.create_console_tab(self.console_tab)
        
        # 选项卡3：快捷设置
        self.settings_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.settings_tab, text=" 快捷设置 ")
        self.create_settings_tab(self.settings_tab)
        
        # 选项卡4：Web 远程
        self.web_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.web_tab, text=" Web 远程 ")
        self.create_web_tab(self.web_tab)
        
        # 底部：状态栏
        self.status_bar = ttk.Frame(self.root, relief=tk.SUNKEN, padding=(5, 2))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.sys_info_label = ttk.Label(self.status_bar, text="系统资源加载中...")
        self.sys_info_label.pack(side=tk.LEFT)
        
    def create_monitor_tab(self, parent):
        # 上部：进程信息
        info_frame = ttk.LabelFrame(parent, text="进程信息", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 状态显示网格
        grid_frame = ttk.Frame(info_frame)
        grid_frame.pack(fill=tk.X)
        
        ttk.Label(grid_frame, text="运行状态:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.status_label = ttk.Label(grid_frame, text="未运行", font=("Segoe UI", 10, "bold"), foreground="red")
        self.status_label.grid(row=0, column=1, sticky=tk.W, padx=(5, 20))
        
        ttk.Label(grid_frame, text="进程 PID:").grid(row=0, column=2, sticky=tk.W)
        self.pid_label = ttk.Label(grid_frame, text="-")
        self.pid_label.grid(row=0, column=3, sticky=tk.W, padx=(5, 20))
        
        ttk.Label(grid_frame, text="运行时长:").grid(row=0, column=4, sticky=tk.W)
        self.uptime_label = ttk.Label(grid_frame, text="-")
        self.uptime_label.grid(row=0, column=5, sticky=tk.W)
        
        # 资源占用
        res_frame = ttk.LabelFrame(parent, text="资源占用", padding="10")
        res_frame.pack(fill=tk.X, pady=(0, 10))
        
        # CPU
        ttk.Label(res_frame, text="CPU 使用率:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.cpu_progress = ttk.Progressbar(res_frame, length=200, mode='determinate')
        self.cpu_progress.grid(row=0, column=1, padx=10)
        self.cpu_label = ttk.Label(res_frame, text="0%")
        self.cpu_label.grid(row=0, column=2, sticky=tk.W)
        
        # 内存
        ttk.Label(res_frame, text="内存使用:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.mem_progress = ttk.Progressbar(res_frame, length=200, mode='determinate')
        self.mem_progress.grid(row=1, column=1, padx=10)
        self.mem_label = ttk.Label(res_frame, text="0 MB")
        self.mem_label.grid(row=1, column=2, sticky=tk.W)
        
        # 其他指标
        other_res = ttk.Frame(res_frame)
        other_res.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))
        ttk.Label(other_res, text="线程数:").pack(side=tk.LEFT)
        self.thread_label = ttk.Label(other_res, text="-")
        self.thread_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(other_res, text="句柄数:").pack(side=tk.LEFT)
        self.handle_label = ttk.Label(other_res, text="-")
        self.handle_label.pack(side=tk.LEFT, padx=5)
        
        # 网络流量
        net_frame = ttk.LabelFrame(parent, text="网络流量监控", padding="10")
        net_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 进程流量
        proc_net = ttk.Frame(net_frame)
        proc_net.pack(fill=tk.X, pady=5)
        ttk.Label(proc_net, text="[进程] 下载:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.download_label = ttk.Label(proc_net, text="0 KB/s", foreground="green", font=("Segoe UI", 10, "bold"))
        self.download_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(proc_net, text="上传:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.upload_label = ttk.Label(proc_net, text="0 KB/s", foreground="blue", font=("Segoe UI", 10, "bold"))
        self.upload_label.pack(side=tk.LEFT, padx=5)
        
        proc_total = ttk.Frame(net_frame)
        proc_total.pack(fill=tk.X, pady=2)
        ttk.Label(proc_total, text="累计下载:").pack(side=tk.LEFT)
        self.total_download_label = ttk.Label(proc_total, text="0 MB")
        self.total_download_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(proc_total, text="累计上传:").pack(side=tk.LEFT)
        self.total_upload_label = ttk.Label(proc_total, text="0 MB")
        self.total_upload_label.pack(side=tk.LEFT, padx=5)
        
        # 分隔线
        ttk.Separator(net_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 系统流量
        sys_net = ttk.Frame(net_frame)
        sys_net.pack(fill=tk.X)
        ttk.Label(sys_net, text="[系统] 下载:").pack(side=tk.LEFT)
        self.sys_download_label = ttk.Label(sys_net, text="0 KB/s")
        self.sys_download_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(sys_net, text="上传:").pack(side=tk.LEFT)
        self.sys_upload_label = ttk.Label(sys_net, text="0 KB/s")
        self.sys_upload_label.pack(side=tk.LEFT, padx=5)
        
        # 控制按钮
        ctrl_frame = ttk.Frame(parent)
        ctrl_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = ttk.Button(ctrl_frame, text=" 启动进程 ", command=self.start_process)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_btn = ttk.Button(ctrl_frame, text=" 停止进程 ", command=self.stop_process)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.restart_btn = ttk.Button(ctrl_frame, text=" 重启进程 ", command=self.restart_process)
        self.restart_btn.pack(side=tk.LEFT)
        
        # 底部日志摘要
        log_frame = ttk.LabelFrame(parent, text="最近日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=5, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def create_console_tab(self, parent):
        # 顶部工具栏
        tools = ttk.Frame(parent)
        tools.pack(fill=tk.X, pady=(0, 5))
        
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tools, text="自动滚动", variable=self.auto_scroll_var).pack(side=tk.LEFT)
        
        ttk.Button(tools, text="清空日志", command=self.clear_console_log).pack(side=tk.RIGHT, padx=5)
        ttk.Button(tools, text="打开日志目录", command=self.open_log_folder).pack(side=tk.RIGHT)
        
        # 日志文本框
        self.console_log = scrolledtext.ScrolledText(parent, font=("Consolas", 9), background="#1e1e1e", foreground="#d4d4d4")
        self.console_log.pack(fill=tk.BOTH, expand=True)
        
        # 底部提示
        ttk.Label(parent, text="提示: 这里实时显示 SaveAny-Bot 控制台输出的原始日志", foreground="gray").pack(fill=tk.X, pady=(5, 0))

    def create_settings_tab(self, parent):
        # 配置文件路径
        cfg_path_frame = ttk.LabelFrame(parent, text="配置文件路径", padding="10")
        cfg_path_frame.pack(fill=tk.X, pady=(0, 10))
        self.config_path_label = ttk.Label(cfg_path_frame, text="请先选择程序路径", foreground="gray")
        self.config_path_label.pack(fill=tk.X)
        
        # 代理设置
        proxy_frame = ttk.LabelFrame(parent, text="代理设置 [telegram.proxy]", padding="10")
        proxy_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 代理启用
        proxy_enable_row = ttk.Frame(proxy_frame)
        proxy_enable_row.pack(fill=tk.X, pady=(0, 5))
        self.proxy_enable_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(proxy_enable_row, text="启用代理", variable=self.proxy_enable_var).pack(side=tk.LEFT)
        
        # 代理状态显示
        ttk.Label(proxy_enable_row, text="状态:").pack(side=tk.LEFT, padx=(20, 5))
        self.proxy_status_label = ttk.Label(proxy_enable_row, text="未测试", foreground="gray")
        self.proxy_status_label.pack(side=tk.LEFT)
        
        # 代理 URL
        proxy_url_row = ttk.Frame(proxy_frame)
        proxy_url_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(proxy_url_row, text="代理地址:", width=10).pack(side=tk.LEFT)
        self.proxy_url_entry = ttk.Entry(proxy_url_row, width=50)
        self.proxy_url_entry.insert(0, "socks5://127.0.0.1:7890")
        self.proxy_url_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        
        # 代理按钮
        proxy_btn_row = ttk.Frame(proxy_frame)
        proxy_btn_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(proxy_btn_row, text="测试连接", command=self.test_proxy_connection).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(proxy_btn_row, text="从配置加载", command=self.load_proxy_from_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(proxy_btn_row, text="保存到配置", command=self.save_proxy_to_config).pack(side=tk.LEFT)
        
        # 存储设置
        storage_frame = ttk.LabelFrame(parent, text="存储设置 [[storages]]", padding="10")
        storage_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 存储名称
        storage_name_row = ttk.Frame(storage_frame)
        storage_name_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(storage_name_row, text="存储名称:", width=10).pack(side=tk.LEFT)
        self.storage_name_entry = ttk.Entry(storage_name_row, width=30)
        self.storage_name_entry.insert(0, "本地磁盘")
        self.storage_name_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        # 存储类型
        ttk.Label(storage_name_row, text="类型:").pack(side=tk.LEFT, padx=(20, 5))
        self.storage_type_var = tk.StringVar(value="local")
        storage_type_combo = ttk.Combobox(storage_name_row, textvariable=self.storage_type_var, 
                                          values=["local", "alist", "webdav", "s3", "telegram"], width=10, state="readonly")
        storage_type_combo.pack(side=tk.LEFT)
        
        # 存储启用
        self.storage_enable_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(storage_name_row, text="启用", variable=self.storage_enable_var).pack(side=tk.LEFT, padx=(20, 0))
        
        # 存储路径
        storage_path_row = ttk.Frame(storage_frame)
        storage_path_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(storage_path_row, text="保存路径:", width=10).pack(side=tk.LEFT)
        self.storage_path_entry = ttk.Entry(storage_path_row, width=50)
        self.storage_path_entry.insert(0, "./downloads")
        self.storage_path_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        ttk.Button(storage_path_row, text="浏览...", command=self.browse_storage_path).pack(side=tk.LEFT, padx=(5, 0))
        
        # 存储按钮
        storage_btn_row = ttk.Frame(storage_frame)
        storage_btn_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(storage_btn_row, text="从配置加载", command=self.load_storage_from_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(storage_btn_row, text="保存到配置", command=self.save_storage_to_config).pack(side=tk.LEFT)
        
        # 配置格式说明
        info_frame = ttk.LabelFrame(parent, text="配置格式说明", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_text = """代理配置格式:
[telegram.proxy]
enable = true
url = "socks5://用户名:密码@IP:端口"

存储配置格式:
[[storages]]
name = "本地磁盘"
type = "local"
enable = true
base_path = "Z:/sp/uuu"""
        info_label = ttk.Label(info_frame, text=info_text, font=("Consolas", 9), justify=tk.LEFT)
        info_label.pack(fill=tk.X)
        
        # 启动设置
        startup_frame = ttk.LabelFrame(parent, text="启动设置", padding="10")
        startup_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.auto_load_config_var = tk.BooleanVar(value=self.load_auto_load_setting())
        ttk.Checkbutton(startup_frame, text="启动时自动从配置文件加载设置", 
                       variable=self.auto_load_config_var,
                       command=self.save_auto_load_setting).pack(side=tk.LEFT)
        
        # 状态提示
        self.settings_status = ttk.Label(parent, text="提示: 修改设置后请点击「保存到配置」按钮", foreground="blue")
        self.settings_status.pack(fill=tk.X, pady=(10, 0))
    
    def create_web_tab(self, parent):
        info_frame = ttk.LabelFrame(parent, text="Web 监控服务", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_text = "启动 Web 服务后，可通过浏览器远程查看监控状态、日志和编辑配置。"
        ttk.Label(info_frame, text=info_text, wraplength=650).pack(fill=tk.X)
        
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
        """添加控制台日志"""
        global recent_logs
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        
        # 添加到全局日志队列（用于Web显示）
        recent_logs.append(log_line)
        
        # 写入日志文件
        if self.log_file:
            try:
                self.log_file.write(log_line + '\n')
                self.log_file.flush()
            except Exception:
                pass
        
        # 添加到队列等待UI更新
        self.log_queue.put(log_line)
    
    def process_log_queue(self):
        """处理日志队列，更新UI"""
        try:
            while True:
                log_line = self.log_queue.get_nowait()
                self.console_log.insert(tk.END, log_line + '\n')
                if self.auto_scroll_var.get():
                    self.console_log.see(tk.END)
                # 限制显示行数
                lines = int(self.console_log.index('end-1c').split('.')[0])
                if lines > 2000:
                    self.console_log.delete('1.0', '500.0')
        except queue.Empty:
            pass
        
        if self.running:
            self.root.after(100, self.process_log_queue)
    
    def clear_console_log(self):
        """清空控制台日志显示"""
        self.console_log.delete('1.0', tk.END)
    
    def open_log_folder(self):
        """打开日志文件夹"""
        if self.target_path:
            log_dir = os.path.join(os.path.dirname(self.target_path), "logs")
            if os.path.exists(log_dir):
                if sys.platform == 'win32':
                    os.startfile(log_dir)
                else:
                    subprocess.Popen(['xdg-open', log_dir])
            else:
                messagebox.showinfo("提示", f"日志文件夹不存在: {log_dir}")
        else:
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
    
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
                        self.uptime_label.config(text=self.format_uptime(uptime))
                        monitor_data["uptime"] = self.format_uptime(uptime)
                        
                        # 流量统计
                        io_counters = proc.io_counters()
                        current_time = time.time()
                        if self.proc_last_io and self.proc_last_time:
                            time_diff = current_time - self.proc_last_time
                            if time_diff > 0:
                                read_speed = (io_counters.read_bytes - self.proc_last_io.read_bytes) / time_diff
                                write_speed = (io_counters.write_bytes - self.proc_last_io.write_bytes) / time_diff
                                
                                dl_speed = self.format_speed(max(0, read_speed))
                                ul_speed = self.format_speed(max(0, write_speed))
                                
                                # 交换显示位置以修正显示反了的问题
                                self.download_label.config(text=ul_speed)
                                self.upload_label.config(text=dl_speed)
                                monitor_data["download_speed"] = ul_speed
                                monitor_data["upload_speed"] = dl_speed
                            
                            total_dl = self.format_bytes(io_counters.read_bytes)
                            total_ul = self.format_bytes(io_counters.write_bytes)
                            
                            # 交换累计显示位置
                            self.total_download_label.config(text=total_ul)
                            self.total_upload_label.config(text=total_dl)
                            monitor_data["total_download"] = total_ul
                            monitor_data["total_upload"] = total_dl
                            
                            self.proc_last_io = io_counters
                            self.proc_last_time = current_time
                        else:
                            self.proc_last_io = io_counters
                            self.proc_last_time = current_time
                            
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
                        
                        # 交换系统流量显示位置
                        self.sys_download_label.config(text=sys_ul)
                        self.sys_upload_label.config(text=sys_dl)
                        monitor_data["sys_download"] = sys_ul
                        monitor_data["sys_upload"] = sys_dl
                
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
        
        monitor_data.update({
            "status": "未运行", "pid": "-", "uptime": "-", "cpu": 0,
            "memory": "0 MB", "memory_percent": 0, "threads": "-", "handles": "-",
            "download_speed": "0 KB/s", "upload_speed": "0 KB/s",
            "total_download": "0 MB", "total_upload": "0 MB"
        })

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
                self.auto_load_settings_on_startup()

    def browse_exe(self):
        filepath = filedialog.askopenfilename(
            title="选择 SaveAny-Bot 程序",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if filepath:
            self.target_path = filepath
            self.path_label.config(text=filepath, foreground="black")
            self.target_process = os.path.basename(filepath)
            self.update_config_path()
            self.log(f"已选择程序: {self.target_process}")

    def auto_detect_process(self):
        proc = self.find_process()
        if proc:
            try:
                exe_path = proc.exe()
                self.target_path = exe_path
                self.path_label.config(text=exe_path, foreground="black")
                self.target_process = os.path.basename(exe_path)
                self.update_config_path()
                self.log(f"自动检测到运行中的进程: {self.target_process}")
            except Exception:
                pass

    def start_process(self):
        if not self.target_path:
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        
        if self.find_process():
            messagebox.showinfo("提示", "进程已在运行中")
            return
            
        try:
            # 准备日志文件
            log_dir = os.path.join(os.path.dirname(self.target_path), "logs")
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            log_filename = f"monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self.log_file = open(os.path.join(log_dir, log_filename), 'a', encoding='utf-8')
            
            # 启动进程，重定向输出
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            self.process = subprocess.Popen(
                self.target_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding='utf-8',
                cwd=os.path.dirname(self.target_path),
                startupinfo=startupinfo
            )
            
            # 启动读取输出的线程
            def read_output():
                for line in iter(self.process.stdout.readline, ''):
                    self.add_console_log(line.strip())
                self.process.stdout.close()
                self.log("进程输出流已关闭")
            
            threading.Thread(target=read_output, daemon=True).start()
            
            self.log(f"进程已启动 (PID: {self.process.pid})")
            self.status_label.config(text="运行中", foreground="green")
            
        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {str(e)}")
            self.log(f"启动失败: {str(e)}")

    def stop_process(self):
        proc = self.find_process()
        if not proc:
            messagebox.showinfo("提示", "没有运行中的进程")
            return
            
        if messagebox.askyesno("确认", f"确定要停止进程 {self.target_process} 吗？"):
            try:
                proc.terminate()
                self.log("已发送停止信号")
                # 等待一会儿检查是否停止
                self.root.after(2000, self.check_process_stopped)
            except Exception as e:
                messagebox.showerror("错误", f"停止失败: {str(e)}")

    def check_process_stopped(self):
        if not self.find_process():
            self.log("进程已完全停止")
            if self.log_file:
                self.log_file.close()
                self.log_file = None
        else:
            if messagebox.askyesno("警告", "进程未响应停止信号，是否强制结束？"):
                proc = self.find_process()
                if proc:
                    proc.kill()
                    self.log("已强制结束进程")

    def restart_process(self):
        proc = self.find_process()
        if proc:
            proc.terminate()
            self.log("正在重启进程...")
            self.root.after(2000, self.start_process)
        else:
            self.start_process()

    def start_web_server(self):
        if self.web_server:
            return
            
        try:
            port_str = self.port_entry.get().strip()
            self.web_port = int(port_str) if port_str else 8080
            
            server_address = ('', self.web_port)
            self.web_server = StoppableHTTPServer(server_address, MonitorHTTPHandler)
            
            self.web_thread = threading.Thread(target=self.web_server.serve_forever_stoppable, daemon=True)
            self.web_thread.start()
            
            self.web_status_label.config(text="运行中", foreground="green")
            local_ip = self.get_local_ip()
            self.url_label.config(text=f"http://{local_ip}:{self.web_port}")
            
            self.start_web_btn.config(state=tk.DISABLED)
            self.stop_web_btn.config(state=tk.NORMAL)
            self.open_browser_btn.config(state=tk.NORMAL)
            self.port_entry.config(state=tk.DISABLED)
            
            self.log(f"Web 服务已在端口 {self.web_port} 启动")
            
        except Exception as e:
            messagebox.showerror("错误", f"Web 服务启动失败: {str(e)}")
            self.web_server = None

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
            # 使用 root.after 在主线程中启动
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
    
    def test_proxy_connection(self):
        """测试 SOCKS5 代理连接"""
        proxy_url = self.proxy_url_entry.get().strip()
        if not proxy_url:
            self.proxy_status_label.config(text="请输入代理地址", foreground="red")
            return
        
        self.proxy_status_label.config(text="测试中...", foreground="orange")
        self.root.update()
        
        def do_test():
            try:
                import re
                # 解析 SOCKS5 URL: socks5://[user:pass@]host:port
                pattern = r'socks5://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)'
                match = re.match(pattern, proxy_url)
                if not match:
                    self.root.after(0, lambda: self.proxy_status_label.config(text="URL 格式错误", foreground="red"))
                    return
                
                username = match.group(1)
                password = match.group(2)
                host = match.group(3)
                port = int(match.group(4))
                
                start_time = time.time()
                
                # 尝试连接代理服务器
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                sock.connect((host, port))
                
                # SOCKS5 握手
                if username and password:
                    # 用户名/密码认证
                    sock.send(b'\x05\x02\x00\x02')  # 支持无认证和用户名/密码认证
                else:
                    sock.send(b'\x05\x01\x00')  # 无认证
                
                response = sock.recv(2)
                if len(response) < 2 or response[0] != 0x05:
                    sock.close()
                    self.root.after(0, lambda: self.proxy_status_label.config(text="代理响应错误", foreground="red"))
                    return
                
                auth_method = response[1]
                
                if auth_method == 0x02 and username and password:
                    # 发送用户名/密码
                    auth_packet = bytes([0x01, len(username)]) + username.encode() + bytes([len(password)]) + password.encode()
                    sock.send(auth_packet)
                    auth_response = sock.recv(2)
                    if len(auth_response) < 2 or auth_response[1] != 0x00:
                        sock.close()
                        self.root.after(0, lambda: self.proxy_status_label.config(text="认证失败", foreground="red"))
                        return
                elif auth_method == 0xFF:
                    sock.close()
                    self.root.after(0, lambda: self.proxy_status_label.config(text="代理拒绝连接", foreground="red"))
                    return
                
                elapsed = (time.time() - start_time) * 1000
                sock.close()
                
                # 根据延迟设置颜色
                if elapsed < 200:
                    color = "green"
                elif elapsed < 500:
                    color = "orange"
                else:
                    color = "red"
                
                self.root.after(0, lambda: self.proxy_status_label.config(text=f"连接成功 ({elapsed:.0f}ms)", foreground=color))
                
            except socket.timeout:
                self.root.after(0, lambda: self.proxy_status_label.config(text="连接超时", foreground="red"))
            except ConnectionRefusedError:
                self.root.after(0, lambda: self.proxy_status_label.config(text="连接被拒绝", foreground="red"))
            except Exception as e:
                self.root.after(0, lambda: self.proxy_status_label.config(text=f"错误: {str(e)[:20]}", foreground="red"))
        
        threading.Thread(target=do_test, daemon=True).start()
    
    def load_proxy_from_config(self):
        """从配置文件加载代理设置"""
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 [telegram.proxy] 部分
            import re
            
            # 查找 enable
            enable_match = re.search(r'\[telegram\.proxy\][\s\S]*?enable\s*=\s*(true|false)', content, re.IGNORECASE)
            if enable_match:
                self.proxy_enable_var.set(enable_match.group(1).lower() == 'true')
            
            # 查找 url
            url_match = re.search(r'\[telegram\.proxy\][\s\S]*?url\s*=\s*["\']([^"\']+)["\']', content)
            if url_match:
                self.proxy_url_entry.delete(0, tk.END)
                self.proxy_url_entry.insert(0, url_match.group(1))
            
            self.settings_status.config(text="代理设置已从配置文件加载", foreground="green")
            self.log("已加载代理设置")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")
    
    def save_proxy_to_config(self):
        """保存代理设置到配置文件"""
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            enable = 'true' if self.proxy_enable_var.get() else 'false'
            url = self.proxy_url_entry.get().strip()
            
            # 检查是否已存在 [telegram.proxy] 部分
            import re
            if re.search(r'\[telegram\.proxy\]', content):
                # 更新现有配置
                content = re.sub(
                    r'(\[telegram\.proxy\][\s\S]*?enable\s*=\s*)(true|false)',
                    f'\\1{enable}',
                    content,
                    flags=re.IGNORECASE
                )
                content = re.sub(
                    r'(\[telegram\.proxy\][\s\S]*?url\s*=\s*)["\'][^"\']*["\']',
                    f'\\1"{url}"',
                    content
                )
            else:
                # 添加新配置
                proxy_config = f'''\n[telegram.proxy]
# 启用代理连接 telegram
enable = {enable}
url = "{url}"\n'''
                # 在 [telegram] 部分后添加
                if '[telegram]' in content:
                    # 找到下一个 section 或文件末尾
                    match = re.search(r'(\[telegram\][^\[]*)', content)
                    if match:
                        insert_pos = match.end()
                        content = content[:insert_pos] + proxy_config + content[insert_pos:]
                else:
                    content += proxy_config
            
            # 备份并保存
            backup_path = config_path + ".bak"
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(open(config_path, 'r', encoding='utf-8').read())
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.settings_status.config(text="代理设置已保存到配置文件", foreground="green")
            self.log("已保存代理设置")
            messagebox.showinfo("成功", "代理设置已保存！\n如果 SaveAny-Bot 正在运行，可能需要重启才能生效。")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")
    
    def browse_storage_path(self):
        """浏览选择存储路径"""
        folder = filedialog.askdirectory(title="选择保存路径")
        if folder:
            self.storage_path_entry.delete(0, tk.END)
            self.storage_path_entry.insert(0, folder)
    
    def load_storage_from_config(self):
        """从配置文件加载第一个存储设置"""
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            # 查找第一个 [[storages]] 部分
            storage_match = re.search(r'\[\[storages\]\][\s\S]*?(?=\[\[storages\]\]|\[|$)', content)
            if storage_match:
                section = storage_match.group(0)
                
                # 提取各字段
                name_m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', section)
                type_m = re.search(r'type\s*=\s*["\']([^"\']+)["\']', section)
                enable_m = re.search(r'enable\s*=\s*(true|false)', section, re.IGNORECASE)
                path_m = re.search(r'base_path\s*=\s*["\']([^"\']+)["\']', section)
                
                if name_m: self.storage_name_entry.delete(0, tk.END); self.storage_name_entry.insert(0, name_m.group(1))
                if type_m: self.storage_type_var.set(type_m.group(1))
                if enable_m: self.storage_enable_var.set(enable_m.group(1).lower() == 'true')
                if path_m: self.storage_path_entry.delete(0, tk.END); self.storage_path_entry.insert(0, path_m.group(1))
                
                self.settings_status.config(text="存储设置已从配置文件加载", foreground="green")
                self.log("已加载存储设置")
            else:
                messagebox.showinfo("提示", "配置文件中未找到 [[storages]] 设置")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")

    def save_storage_to_config(self):
        """保存存储设置到配置文件"""
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            name = self.storage_name_entry.get().strip()
            stype = self.storage_type_var.get()
            enable = 'true' if self.storage_enable_var.get() else 'false'
            path = self.storage_path_entry.get().strip()
            
            import re
            # 检查是否已存在 [[storages]]
            if '[[storages]]' in content:
                # 只替换第一个存储配置
                # 这是一个简化的正则表达式，可能需要根据实际情况调整
                new_section = f'[[storages]]\nname = "{name}"\ntype = "{stype}"\nenable = {enable}\nbase_path = "{path}"'
                content = re.sub(r'\[\[storages\]\][\s\S]*?(?=\[\[storages\]\]|\[|$)', new_section + '\n', content, count=1)
            else:
                # 添加到文件末尾
                content += f'\n[[storages]]\nname = "{name}"\ntype = "{stype}"\nenable = {enable}\nbase_path = "{path}"\n'
            
            # 备份并保存
            backup_path = config_path + ".bak"
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(open(config_path, 'r', encoding='utf-8').read())
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.settings_status.config(text="存储设置已保存到配置文件", foreground="green")
            self.log("已保存存储设置")
            messagebox.showinfo("成功", "存储设置已保存！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")

    def load_auto_load_setting(self):
        """加载自动加载设置"""
        try:
            if os.path.exists("monitor_settings.json"):
                with open("monitor_settings.json", 'r') as f:
                    data = json.load(f)
                    return data.get("auto_load_config", False)
        except Exception:
            pass
        return False

    def save_auto_load_setting(self):
        """保存自动加载设置"""
        try:
            data = {"auto_load_config": self.auto_load_config_var.get()}
            with open("monitor_settings.json", 'w') as f:
                json.dump(data, f)
        except Exception:
            pass

    def auto_load_settings_on_startup(self):
        """启动时自动加载设置"""
        if self.auto_load_config_var.get():
            self.load_proxy_from_config()
            self.load_storage_from_config()
            self.log("已根据设置自动加载配置参数")

    def load_config(self):
        """加载基础配置信息"""
        pass


if __name__ == "__main__":
    # 针对 Windows Server 优化 DPI 感知
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
        
    root = tk.Tk()
    
    # 设置主题样式
    style = ttk.Style()
    if sys.platform == 'win32':
        style.theme_use('vista')
    
    app = SaveAnyMonitor(root)
    
    def on_closing():
        app.running = False
        if app.web_server:
            app.web_server.stop()
        if app.log_file:
            app.log_file.close()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
