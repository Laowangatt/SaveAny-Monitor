#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SaveAny-Bot Monitor v2.7.2
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
                    <div class="stat-row" style="margin-top: 15px;"><span class="stat-label">总下载</span><span class="stat-value" id="totalDownload">0 MB</span></div>
                    <div class="stat-row"><span class="stat-label">总上传</span><span class="stat-value" id="totalUpload">0 MB</span></div>
                </div>
                <div class="card">
                    <h2>系统网络流量</h2>
                    <div class="stat-row"><span class="stat-label">系统下载</span><span class="stat-value" id="sysDownload">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">系统上传</span><span class="stat-value" id="sysUpload">0 KB/s</span></div>
                </div>
                <div class="card">
                    <h2>快捷控制</h2>
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
                <h2>实时日志</h2>
                <div class="btn-group" style="margin-bottom: 15px;">
                    <button class="btn btn-primary" onclick="loadLogs()">刷新日志</button>
                    <button class="btn btn-danger" onclick="clearLogs()">清空显示</button>
                    <label style="display: flex; align-items: center; color: #fff;">
                        <input type="checkbox" id="autoScroll" checked style="margin-right: 5px;"> 自动滚动
                    </label>
                </div>
                <div id="logViewer" class="log-viewer">等待日志...</div>
            </div>
        </div>
        
        <div id="config" class="tab-content">
            <div class="card">
                <h2>配置文件编辑 (config.toml)</h2>
                <textarea id="configEditor" class="config-editor" placeholder="加载配置文件中..."></textarea>
                <div class="btn-group">
                    <button class="btn btn-primary" onclick="loadConfig()">重新加载</button>
                    <button class="btn btn-success" onclick="saveConfig()">保存配置</button>
                </div>
            </div>
        </div>
        
        <p class="update-time">最后更新: <span id="updateTime">-</span></p>
    </div>
    
    <script>
        var logTimer = null;
        
        function showTab(name) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector('.tab[onclick*="' + name + '"]').classList.add('active');
            document.getElementById(name).classList.add('active');
            if (name === 'logs') { loadLogs(); if (!logTimer) logTimer = setInterval(loadLogs, 2000); }
            else if (name === 'config') loadConfig();
        }
        
        function updateStatus() {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/status', true);
            xhr.timeout = 5000;
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4 && xhr.status === 200) {
                    try {
                        var data = JSON.parse(xhr.responseText);
                        document.getElementById('status').textContent = data.status;
                        document.getElementById('pid').textContent = data.pid;
                        document.getElementById('uptime').textContent = data.uptime;
                        document.getElementById('cpu').textContent = data.cpu + '%';
                        document.getElementById('memory').textContent = data.memory;
                        document.getElementById('threads').textContent = data.threads;
                        document.getElementById('handles').textContent = data.handles;
                        document.getElementById('downloadSpeed').textContent = data.download_speed;
                        document.getElementById('uploadSpeed').textContent = data.upload_speed;
                        document.getElementById('totalDownload').textContent = data.total_download;
                        document.getElementById('totalUpload').textContent = data.total_upload;
                        document.getElementById('sysDownload').textContent = data.sys_download;
                        document.getElementById('sysUpload').textContent = data.sys_upload;
                        document.getElementById('updateTime').textContent = data.last_update;
                        var cpuBar = document.getElementById('cpuBar');
                        cpuBar.style.width = Math.min(data.cpu, 100) + '%';
                        cpuBar.className = 'progress-fill' + (data.cpu > 80 ? ' danger' : data.cpu > 50 ? ' warning' : '');
                        var memBar = document.getElementById('memBar');
                        memBar.style.width = Math.min(data.memory_percent, 100) + '%';
                        memBar.className = 'progress-fill' + (data.memory_percent > 80 ? ' danger' : data.memory_percent > 50 ? ' warning' : '');
                        var badge = document.getElementById('statusBadge');
                        if (data.status.indexOf('运行中') >= 0) { badge.textContent = '运行中'; badge.className = 'status-badge status-running'; }
                        else { badge.textContent = '未运行'; badge.className = 'status-badge status-stopped'; }
                    } catch(e) {}
                }
            };
            xhr.send();
        }
        
        function loadLogs() {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/logs', true);
            xhr.timeout = 5000;
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4 && xhr.status === 200) {
                    try {
                        var data = JSON.parse(xhr.responseText);
                        var viewer = document.getElementById('logViewer');
                        viewer.textContent = data.logs || '暂无日志';
                        if (document.getElementById('autoScroll').checked) viewer.scrollTop = viewer.scrollHeight;
                    } catch(e) {}
                }
            };
            xhr.send();
        }
        
        function clearLogs() { document.getElementById('logViewer').textContent = ''; }
        
        function loadConfig() {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/config', true);
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4 && xhr.status === 200) {
                    try {
                        var data = JSON.parse(xhr.responseText);
                        document.getElementById('configEditor').value = data.success ? data.content : '# 无法加载: ' + data.error;
                    } catch(e) {}
                }
            };
            xhr.send();
        }
        
        function saveConfig() {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/config', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4 && xhr.status === 200) {
                    try { var data = JSON.parse(xhr.responseText); alert(data.success ? '配置已保存！' : '保存失败: ' + data.error); } catch(e) {}
                }
            };
            xhr.send(JSON.stringify({ content: document.getElementById('configEditor').value }));
        }
        
        function controlProcess(action) {
            if ((action === 'stop' || action === 'restart') && !confirm('确定要' + (action === 'stop' ? '停止' : '重启') + '进程吗？')) return;
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/control', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4 && xhr.status === 200) {
                    try { var data = JSON.parse(xhr.responseText); alert(data.message); } catch(e) {}
                }
            };
            xhr.send(JSON.stringify({ action: action }));
        }
        
        function formatSize(bytes) {
            if (!bytes || isNaN(bytes) || bytes <= 0) return '0 B';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
            if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
            return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
        }
        
        updateStatus();
        setInterval(updateStatus, 1000);
    </script>
</body>
</html>'''
        try:
            content = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            pass
    
    def send_json_status(self):
        try:
            content = json.dumps(monitor_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            pass
    
    def send_logs(self):
        """发送日志内容"""
        global recent_logs
        try:
            logs_text = '\n'.join(recent_logs) if recent_logs else '暂无日志，请通过监控程序启动 SaveAny-Bot 以捕获日志'
            result = {"logs": logs_text}
            content = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            pass
            
    def send_config(self):
        """发送配置文件内容"""
        global config_path
        try:
            content = ""
            success = False
            error = ""
            if config_path and os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    success = True
                except Exception as e:
                    error = str(e)
            else:
                error = "配置文件不存在"
            
            result = {"success": success, "content": content, "error": error}
            resp_content = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(resp_content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(resp_content)
        except Exception:
            pass
            
    def save_config(self):
        """保存配置文件"""
        global config_path
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_len)
            data = json.loads(post_data.decode('utf-8'))
            new_content = data.get('content', '')
            
            success = False
            error = ""
            if config_path:
                try:
                    with open(config_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    success = True
                except Exception as e:
                    error = str(e)
            else:
                error = "未设置配置文件路径"
                
            result = {"success": success, "error": error}
            resp_content = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(resp_content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(resp_content)
        except Exception:
            pass
            
    def handle_control(self):
        """处理进程控制请求"""
        global control_callback
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_len)
            data = json.loads(post_data.decode('utf-8'))
            action = data.get('action', '')
            
            message = "未知操作"
            if control_callback:
                if action == 'start':
                    control_callback('start')
                    message = "已发送启动指令"
                elif action == 'stop':
                    control_callback('stop')
                    message = "已发送停止指令"
                elif action == 'restart':
                    control_callback('restart')
                    message = "已发送重启指令"
            
            result = {"message": message}
            resp_content = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(resp_content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(resp_content)
        except Exception:
            pass


class SaveAnyMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("SaveAny-Bot Monitor v2.7.2")
        self.root.geometry("800x700")
        
        # 默认监控进程名
        self.target_process = "SaveAny-Bot.exe"
        self.target_path = None
        self.process = None
        self.running = True
        self.log_queue = queue.Queue()
        self.log_file = None
        
        # 流量统计
        self.last_net_io = psutil.net_io_counters()
        self.last_net_time = time.time()
        self.proc_last_io = None
        self.proc_last_time = None
        
        # Web 服务
        self.httpd = None
        self.web_port = 8080
        self.web_thread = None
        
        # 设置全局回调
        global control_callback
        control_callback = self.handle_web_control
        
        self.setup_ui()
        # 尝试自动检测和加载配置文件
        self.auto_detect_config()
        self.start_monitoring()
        self.process_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 监控页面
        monitor_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(monitor_frame, text=" 监控 ")
        self.create_monitor_tab(monitor_frame)
        
        # 日志页面
        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text=" 日志 ")
        self.create_log_tab(log_frame)
        
        # 配置编辑页面
        config_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(config_frame, text=" 配置编辑 ")
        self.create_config_tab(config_frame)
        
        # 设置页面
        settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(settings_frame, text=" 设置 ")
        self.create_settings_tab(settings_frame)
        
        # Web 服务页面
        web_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(web_frame, text=" Web 服务 ")
        self.create_web_tab(web_frame)
    
    def auto_detect_config(self):
        """自动检测并加载配置文件"""
        global config_path
        # 尝试在当前目录和常见位置查找 config.toml
        search_paths = [
            os.path.join(os.getcwd(), "config.toml"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml"),
            os.path.expanduser("~/SaveAny-Bot/config.toml"),
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                config_path = path
                self.target_path = os.path.dirname(path)
                if hasattr(self, 'path_label'):
                    self.path_label.config(text=self.target_path)
                # 延迟加载配置文件，确保 UI 已初始化
                self.root.after(500, self.load_config)
                self.log(f"自动检测到配置文件: {path}")
                return
        
        # 如果没有找到配置文件，记录日志
        if hasattr(self, 'log'):
            self.log("未找到配置文件，请手动选择程序或配置文件")
    
    def create_monitor_tab(self, parent):
        # 进程状态
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
        
        # 资源占用
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
        
        # 网络流量
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
        
        # 系统网络
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
        
        # 控制按钮
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
        
        # 简要日志
        log_frame = ttk.LabelFrame(parent, text="最近日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_frame, height=4, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log("SaveAny-Bot Monitor v2.7.2 已启动")
        self.log(f"正在监控进程: {self.target_process}")
    
    def create_log_tab(self, parent):
        """创建日志标签页"""
        # 说明
        info_frame = ttk.LabelFrame(parent, text="日志捕获", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_text = "通过本监控程序启动 SaveAny-Bot 可以捕获其控制台输出并保存到日志文件。\n日志文件保存在 SaveAny-Bot 同目录下的 logs 文件夹中。"
        ttk.Label(info_frame, text=info_text, wraplength=680).pack(fill=tk.X)
        
        # 日志设置
        settings_frame = ttk.Frame(parent)
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.capture_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="启用日志捕获", variable=self.capture_var).pack(side=tk.LEFT)
        
        ttk.Label(settings_frame, text="  日志文件:").pack(side=tk.LEFT, padx=(20, 0))
        self.log_path_label = ttk.Label(settings_frame, text="未启动", foreground="gray")
        self.log_path_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # 按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(btn_frame, text="清空显示", command=self.clear_console_log).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="打开日志文件夹", command=self.open_log_folder).pack(side=tk.LEFT, padx=(0, 10))
        
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn_frame, text="自动滚动", variable=self.auto_scroll_var).pack(side=tk.LEFT)
        
        # 日志显示区域
        log_display_frame = ttk.LabelFrame(parent, text="SaveAny-Bot 控制台输出", padding="5")
        log_display_frame.pack(fill=tk.BOTH, expand=True)
        
        self.console_log = scrolledtext.ScrolledText(
            log_display_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white'
        )
        self.console_log.pack(fill=tk.BOTH, expand=True)
        self.console_log.insert(tk.END, "等待 SaveAny-Bot 启动...\n提示: 请通过本监控程序的「启动进程」按钮启动 SaveAny-Bot 以捕获日志\n")
    
    def create_config_tab(self, parent):
        info_label = ttk.Label(parent, text="编辑 SaveAny-Bot 的配置文件 (config.toml)，修改后点击保存按钮。", wraplength=650)
        info_label.pack(fill=tk.X, pady=(0, 10))
        
        self.config_text = scrolledtext.ScrolledText(parent, wrap=tk.NONE, font=("Consolas", 10))
        self.config_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X)
        
        ttk.Button(btn_row, text="重新加载", command=self.load_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_row, text="保存配置", command=self.save_config).pack(side=tk.LEFT)
    
    def create_settings_tab(self, parent):
        # 监控设置
        monitor_frame = ttk.LabelFrame(parent, text="监控设置", padding="10")
        monitor_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(monitor_frame, text="监控进程名:").grid(row=0, column=0, sticky=tk.W)
        self.proc_name_var = tk.StringVar(value=self.target_process)
        ttk.Entry(monitor_frame, textvariable=self.proc_name_var, width=30).grid(row=0, column=1, padx=10, sticky=tk.W)
        ttk.Button(monitor_frame, text="应用", command=self.apply_proc_name).grid(row=0, column=2, sticky=tk.W)
        
        # Web 服务设置
        web_frame = ttk.LabelFrame(parent, text="Web 服务设置", padding="10")
        web_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(web_frame, text="Web 端口:").grid(row=0, column=0, sticky=tk.W)
        self.web_port_var = tk.StringVar(value=str(self.web_port))
        ttk.Entry(web_frame, textvariable=self.web_port_var, width=10).grid(row=0, column=1, padx=10, sticky=tk.W)
        
        self.web_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(web_frame, text="启用 Web 服务", variable=self.web_enabled_var).grid(row=1, column=0, columnspan=2, pady=10, sticky=tk.W)
        
        ttk.Button(web_frame, text="重启 Web 服务", command=self.restart_web_server).grid(row=2, column=0, sticky=tk.W)
        
        # 关于
        about_frame = ttk.LabelFrame(parent, text="关于", padding="10")
        about_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(about_frame, text="SaveAny-Bot Monitor v2.7.2\n针对 Windows Server 2025 优化\n用于监控 SaveAny-Bot 的运行状态").pack(fill=tk.X)
    
    def create_web_tab(self, parent):
        info_frame = ttk.LabelFrame(parent, text="Web 服务状态", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.web_status_label = ttk.Label(info_frame, text="服务未启动", font=("", 10, "bold"))
        self.web_status_label.pack(fill=tk.X, pady=(0, 5))
        
        self.web_url_label = ttk.Label(info_frame, text="访问地址: -", foreground="blue", cursor="hand2")
        self.web_url_label.pack(fill=tk.X)
        self.web_url_label.bind("<Button-1>", lambda e: webbrowser.open(self.web_url_label.cget("text").replace("访问地址: ", "")))
        
        tip_text = "提示: 启用 Web 服务后，您可以通过浏览器远程查看监控状态、日志和编辑配置。\n如果是在云服务器上运行，请确保防火墙已开放对应端口。"
        ttk.Label(parent, text=tip_text, wraplength=680, foreground="gray").pack(fill=tk.X, pady=10)
        
        ttk.Button(parent, text="在浏览器中打开", command=lambda: webbrowser.open(f"http://localhost:{self.web_port}")).pack(side=tk.LEFT)
    
    def apply_proc_name(self):
        self.target_process = self.proc_name_var.get()
        self.log(f"监控进程名已更改为: {self.target_process}")
        messagebox.showinfo("提示", f"监控进程名已更改为: {self.target_process}")
    
    def browse_exe(self):
        file_path = filedialog.askopenfilename(
            title="选择 SaveAny-Bot 程序",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if file_path:
            self.target_path = file_path
            self.path_label.config(text=file_path)
            self.target_process = os.path.basename(file_path)
            self.proc_name_var.set(self.target_process)
            self.update_config_path()
            self.log(f"已选择程序: {file_path}")
    
    def update_config_path(self):
        global config_path
        if self.target_path:
            potential_config = os.path.join(os.path.dirname(self.target_path), "config.toml")
            if os.path.exists(potential_config):
                config_path = potential_config
                # 延迟加载，确保 UI 已初始化
                self.root.after(100, self.load_config)
            else:
                # 配置文件不存在时的提示
                if hasattr(self, 'config_text'):
                    self.config_text.delete('1.0', tk.END)
                    self.config_text.insert(tk.END, f"# 配置文件未找到\n# 预期路径: {potential_config}")
    
    def load_config(self):
        global config_path
        # 确保 config_text 已初始化
        if not hasattr(self, 'config_text'):
            return
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.config_text.delete('1.0', tk.END)
                self.config_text.insert(tk.END, content)
                self.log(f"配置文件已加载: {config_path}")
            except Exception as e:
                self.log(f"加载配置失败: {e}")
                self.config_text.delete('1.0', tk.END)
                self.config_text.insert(tk.END, f"# 加载配置失败: {e}")
        else:
            self.config_text.delete('1.0', tk.END)
            if config_path:
                self.config_text.insert(tk.END, f"# 配置文件不存在\n# 路径: {config_path}\n# 请先选择程序或确保程序目录下存在 config.toml")
            else:
                self.config_text.insert(tk.END, "# 配置文件未找到，请先选择程序或确保程序目录下存在 config.toml")
    
    def save_config(self):
        global config_path
        if config_path:
            try:
                content = self.config_text.get('1.0', tk.END).strip()
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log("配置文件已保存")
                messagebox.showinfo("提示", "配置文件已保存")
            except Exception as e:
                self.log(f"保存配置失败: {e}")
                messagebox.showerror("错误", f"保存失败: {e}")
        else:
            messagebox.showwarning("警告", "未找到配置文件路径")
    
    def open_folder(self):
        if self.target_path:
            folder = os.path.dirname(self.target_path)
            if os.path.exists(folder):
                os.startfile(folder)
        else:
            messagebox.showwarning("警告", "请先选择程序或等待程序运行")
    
    def start_process(self):
        if self.process and self.process.poll() is None:
            messagebox.showwarning("警告", "程序已经在运行中")
            return
        
        if not self.target_path:
            self.browse_exe()
            if not self.target_path: return
            
        try:
            # 准备日志文件
            if self.capture_var.get():
                log_dir = os.path.join(os.path.dirname(self.target_path), "logs")
                if not os.path.exists(log_dir): os.makedirs(log_dir)
                log_filename = f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                log_path = os.path.join(log_dir, log_filename)
                self.log_file = open(log_path, 'a', encoding='utf-8')
                self.log_path_label.config(text=log_filename, foreground="black")
                self.log(f"日志将保存至: {log_filename}")
            
            # 启动进程
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            self.process = subprocess.Popen(
                [self.target_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=os.path.dirname(self.target_path),
                startupinfo=startupinfo
            )
            
            # 启动日志读取线程
            threading.Thread(target=self.read_process_output, daemon=True).start()
            self.log("程序已启动")
            
        except Exception as e:
            self.log(f"启动失败: {e}")
            messagebox.showerror("错误", f"启动失败: {e}")
    
    def stop_process(self):
        if self.process and self.process.poll() is None:
            try:
                # 尝试优雅停止
                if sys.platform == 'win32':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], capture_output=True)
                else:
                    self.process.terminate()
                self.log("程序已停止")
            except Exception as e:
                self.log(f"停止失败: {e}")
        else:
            # 尝试按名称停止
            found = False
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] == self.target_process:
                    try:
                        proc.kill()
                        found = True
                    except: pass
            if found: self.log(f"已按名称停止所有 {self.target_process}")
            else: messagebox.showinfo("提示", "程序未在运行")
            
    def restart_process(self):
        self.stop_process()
        self.root.after(1000, self.start_process)
        
    def read_process_output(self):
        """读取进程输出并放入队列"""
        if not self.process: return
        
        for line in iter(self.process.stdout.readline, ''):
            if not line: break
            clean_line = line.strip()
            if clean_line:
                self.add_console_log(clean_line)
        
        self.process.stdout.close()
        self.log("进程输出流已关闭")
        if self.log_file:
            self.log_file.close()
            self.log_file = None
            
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
    
    def start_monitoring(self):
        """启动监控线程"""
        threading.Thread(target=self.monitor_loop, daemon=True).start()
        if self.web_enabled_var.get():
            self.start_web_server()
            
    def monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                found = False
                for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'num_threads', 'create_time']):
                    if proc.info['name'] == self.target_process:
                        found = True
                        # 更新 UI
                        self.root.after(0, self.update_ui_data, proc)
                        break
                
                if not found:
                    self.root.after(0, self.update_ui_stopped)
                
                # 系统网络流量
                self.update_sys_network()
                
                # 更新 Web 数据的时间戳
                monitor_data["last_update"] = datetime.now().strftime("%H:%M:%S")
                
            except Exception as e:
                print(f"监控错误: {e}")
            
            time.sleep(1)
            
    def update_ui_data(self, proc):
        try:
            with proc.oneshot():
                pid = proc.pid
                self.status_label.config(text="运行中", foreground="#008000")
                self.pid_label.config(text=str(pid))
                monitor_data["status"] = "运行中"
                monitor_data["pid"] = str(pid)
                
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
                            # 修复上传下载颠倒：write_bytes 对应上传，read_bytes 对应下载
                            # 在某些系统中，进程的 read/write 可能被误解，这里根据用户反馈进行调整
                            read_speed = (io_counters.read_bytes - self.proc_last_io.read_bytes) / time_diff
                            write_speed = (io_counters.write_bytes - self.proc_last_io.write_bytes) / time_diff
                            
                            # 修复网络流量颠倒：下载速度应该是接收的数据，上传速度应该是发送的数据
                            dl_speed = self.format_speed(max(0, read_speed))
                            ul_speed = self.format_speed(max(0, write_speed))
                            self.download_label.config(text=dl_speed)
                            self.upload_label.config(text=ul_speed)
                            monitor_data["download_speed"] = dl_speed
                            monitor_data["upload_speed"] = ul_speed
                    
                    # 同样修复总流量：下载是读取的字节，上传是写入的字节
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
            self.update_ui_stopped()

    def update_ui_stopped(self):
        self.status_label.config(text="未运行", foreground="#FF0000")
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
        
        monitor_data.update({
            "status": "未运行", "pid": "-", "uptime": "-", "cpu": 0,
            "memory": "0 MB", "memory_percent": 0, "threads": "-", "handles": "-",
            "download_speed": "0 KB/s", "upload_speed": "0 KB/s",
        })
        
    def update_sys_network(self):
        try:
            net_io = psutil.net_io_counters()
            current_time = time.time()
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
        except: pass
        
    def format_speed(self, bytes_per_sec):
        if bytes_per_sec < 1024: return f"{bytes_per_sec:.1f} B/s"
        elif bytes_per_sec < 1024 * 1024: return f"{bytes_per_sec/1024:.1f} KB/s"
        else: return f"{bytes_per_sec/(1024*1024):.1f} MB/s"
        
    def format_bytes(self, b):
        if b < 1024: return f"{b} B"
        elif b < 1024 * 1024: return f"{b/1024:.1f} KB"
        elif b < 1024 * 1024 * 1024: return f"{b/(1024*1024):.1f} MB"
        else: return f"{b/(1024*1024*1024):.1f} GB"
        
    def format_uptime(self, seconds):
        td = timedelta(seconds=int(seconds))
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if days > 0: return f"{days}天 {hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 100:
            self.log_text.delete('1.0', '2.0')
            
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
                messagebox.showinfo("提示", "日志文件夹尚不存在，请先启动程序")
        else:
            messagebox.showwarning("警告", "请先选择程序")
            
    def start_web_server(self):
        try:
            self.web_port = int(self.web_port_var.get())
            server_address = ('', self.web_port)
            self.httpd = StoppableHTTPServer(server_address, MonitorHTTPHandler)
            
            self.web_thread = threading.Thread(target=self.httpd.serve_forever_stoppable, daemon=True)
            self.web_thread.start()
            
            hostname = socket.gethostname()
            try:
                local_ip = socket.gethostbyname(hostname)
            except:
                local_ip = "127.0.0.1"
                
            self.web_status_label.config(text="服务运行中", foreground="#008000")
            self.web_url_label.config(text=f"访问地址: http://{local_ip}:{self.web_port}")
            self.log(f"Web 服务已启动: http://{local_ip}:{self.web_port}")
        except Exception as e:
            self.log(f"Web 服务启动失败: {e}")
            self.web_status_label.config(text="启动失败", foreground="#FF0000")
            
    def stop_web_server(self):
        if self.httpd:
            self.httpd.stop()
            self.httpd = None
            self.web_status_label.config(text="服务已停止", foreground="black")
            self.web_url_label.config(text="访问地址: -")
            self.log("Web 服务已停止")
            
    def restart_web_server(self):
        self.stop_web_server()
        self.root.after(1000, self.start_web_server)
        
    def handle_web_control(self, action):
        """处理来自 Web 的控制指令"""
        if action == 'start':
            self.root.after(0, self.start_process)
        elif action == 'stop':
            self.root.after(0, self.stop_process)
        elif action == 'restart':
            self.root.after(0, self.restart_process)
            
    def on_closing(self):
        self.running = False
        if self.httpd:
            self.httpd.stop()
        if self.log_file:
            self.log_file.close()
        self.root.destroy()


if __name__ == "__main__":
    # 针对 Windows 高 DPI 优化
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    
    root = tk.Tk()
    app = SaveAnyMonitor(root)
    root.mainloop()
