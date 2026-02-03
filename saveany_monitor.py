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
                    <div class="stat-row" style="margin-top: 15px;"><span class="stat-label">累计下载 / 上传</span><span class="stat-value"><span id="totalDownload">0 MB</span> / <span id="totalUpload">0 MB</span></span></div>
                </div>
                <div class="card">
                    <h2>系统整体流量</h2>
                    <div class="stat-row"><span class="stat-label">系统下载</span><span class="stat-value" id="sysDownload">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">系统上传</span><span class="stat-value" id="sysUpload">0 KB/s</span></div>
                </div>
                <div class="card">
                    <h2>进程控制</h2>
                    <div class="btn-group">
                        <button class="btn btn-success" onclick="control('start')">启动进程</button>
                        <button class="btn btn-danger" onclick="control('stop')">停止进程</button>
                        <button class="btn btn-warning" onclick="control('restart')">重启进程</button>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="logs" class="tab-content">
            <div class="card">
                <h2>实时日志</h2>
                <div id="logViewer" class="log-viewer">等待日志...</div>
                <div class="btn-group">
                    <button class="btn btn-primary" onclick="loadLogs()">刷新日志</button>
                </div>
            </div>
        </div>
        
        <div id="config" class="tab-content">
            <div class="card">
                <h2>配置文件 (config.toml)</h2>
                <textarea id="configEditor" class="config-editor" spellcheck="false"></textarea>
                <div class="btn-group">
                    <button class="btn btn-success" onclick="saveConfig()">保存配置</button>
                    <button class="btn btn-primary" onclick="loadConfig()">重新加载</button>
                </div>
            </div>
        </div>
        
        <div class="update-time">最后更新: <span id="lastUpdate">-</span></div>
    </div>

    <script>
        let currentTab = 'monitor';
        let refreshInterval = null;

        function showTab(tabId) {
            currentTab = tabId;
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            event.currentTarget.classList.add('active');
            
            // 清理之前的定时器
            if (refreshInterval) {
                clearInterval(refreshInterval);
                refreshInterval = null;
            }

            if (tabId === 'logs') {
                loadLogs();
                // 切换到日志标签页时，每2秒刷新一次
                refreshInterval = setInterval(loadLogs, 2000);
            } else if (tabId === 'config') {
                loadConfig();
            } else if (tabId === 'monitor') {
                // 监控页面的数据由 updateStatus 统一处理
            }
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
                badge.textContent = data.status;
                badge.className = 'status-badge ' + (data.status === '运行中' ? 'status-running' : 'status-stopped');
            } catch (e) {}
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();
                document.getElementById('configEditor').value = data.content;
            } catch (e) { alert('加载配置失败'); }
        }

        async function saveConfig() {
            try {
                const content = document.getElementById('configEditor').value;
                const response = await fetch('/api/config', {
                    method: 'POST',
                    body: JSON.stringify({ content })
                });
                const data = await response.json();
                if (data.success) alert('配置已保存');
                else alert('保存失败: ' + data.message);
            } catch (e) { alert('保存请求失败'); }
        }

        async function loadLogs() {
            try {
                const response = await fetch('/api/logs');
                const data = await response.json();
                const viewer = document.getElementById('logViewer');
                const shouldScroll = viewer.scrollTop + viewer.clientHeight === viewer.scrollHeight;
                viewer.textContent = data.logs.join('\\n');
                if (shouldScroll) viewer.scrollTop = viewer.scrollHeight;
            } catch (e) {}
        }

        async function control(action) {
            try {
                const response = await fetch('/api/control', {
                    method: 'POST',
                    body: JSON.stringify({ action })
                });
                const data = await response.json();
                if (data.success) {
                    setTimeout(updateStatus, 1000);
                } else {
                    alert('操作失败: ' + data.message);
                }
            } catch (e) { alert('控制请求失败'); }
        }

        setInterval(updateStatus, 2000);
        updateStatus();
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(html.encode('utf-8'))))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def send_json_status(self):
        """发送 JSON 状态数据"""
        global monitor_data
        content = json.dumps(monitor_data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)

    def send_config(self):
        """发送配置文件内容"""
        global config_path
        try:
            content = ""
            if config_path and os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            result = {"content": content, "path": config_path or "未加载"}
            content_bytes = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content_bytes)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content_bytes)
        except Exception:
            pass

    def send_logs(self):
        """发送最近日志内容"""
        global recent_logs
        try:
            result = {"logs": list(recent_logs)}
            content = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            pass

    def save_config(self):
        """保存配置文件"""
        global config_path
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            new_content = data.get('content', '')
            
            if config_path and os.path.exists(config_path):
                # 备份
                with open(config_path + ".bak", 'w', encoding='utf-8') as f:
                    f.write(open(config_path, 'r', encoding='utf-8').read())
                # 写入
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                result = {"success": True, "message": "保存成功"}
            else:
                result = {"success": False, "message": "配置文件未加载"}
            
            content = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            pass

    def handle_control(self):
        """处理进程控制请求"""
        global control_callback
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            action = data.get('action', '')
            
            success = False
            message = "未知操作"
            
            if control_callback:
                if action == 'start':
                    success, message = control_callback('start')
                elif action == 'stop':
                    success, message = control_callback('stop')
                elif action == 'restart':
                    success, message = control_callback('restart')
            
            result = {"success": success, "message": message}
            content = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            pass


class SaveAnyMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("SaveAny-Bot Monitor v2.7.2")
        self.root.geometry("800x700")
        
        # 针对 Windows Server 2025 的 UI 适配
        self.target_process = "SaveAny-Bot.exe"
        self.target_path = None
        self.managed_process = None
        self.log_file = None
        self.log_file_path = None
        self.running = True
        self.update_interval = 2000  # 2秒更新一次
        
        # 流量统计
        self.last_net_io = None
        self.last_net_time = None
        self.proc_last_io = None
        self.proc_last_time = None
        
        # Web 服务
        self.web_server = None
        self.web_thread = None
        global control_callback
        control_callback = self.handle_web_control
        
        # 消息队列
        self.log_queue = queue.Queue()
        
        self.create_widgets()
        self.start_monitoring()
        self.process_log_queue()
        
        # 尝试自动查找
        self.root.after(1000, self.auto_detect)

    def create_widgets(self):
        # 创建 Notebook (标签页)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 监控标签页
        self.monitor_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.monitor_tab, text=" 状态监控 ")
        self.create_monitor_tab(self.monitor_tab)
        
        # 日志标签页
        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text=" 实时日志 ")
        self.create_log_tab(self.log_tab)
        
        # 配置标签页
        self.config_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.config_tab, text=" 配置编辑 ")
        self.create_config_tab(self.config_tab)
        
        # 设置标签页
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text=" 快捷设置 ")
        self.create_settings_tab(self.settings_tab)
        
        # Web 标签页
        self.web_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.web_tab, text=" Web 服务 ")
        self.create_web_tab(self.web_tab)
        
        # 状态栏
        self.status_bar = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 窗口关闭协议
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_monitor_tab(self, parent):
        # 状态面板
        status_frame = ttk.LabelFrame(parent, text="SaveAny-Bot 进程状态", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 第一行: 状态和 PID
        row1 = ttk.Frame(status_frame)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="当前状态:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(row1, text="未运行", foreground="red", font=('', 10, 'bold'))
        self.status_label.pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Label(row1, text="进程 PID:").pack(side=tk.LEFT)
        self.pid_label = ttk.Label(row1, text="-")
        self.pid_label.pack(side=tk.LEFT, padx=(5, 20))
        
        ttk.Label(row1, text="运行时长:").pack(side=tk.LEFT)
        self.uptime_label = ttk.Label(row1, text="-")
        self.uptime_label.pack(side=tk.LEFT)
        
        # 资源面板
        resource_frame = ttk.LabelFrame(parent, text="资源占用", padding="10")
        resource_frame.pack(fill=tk.X, pady=(0, 10))
        
        # CPU
        cpu_row = ttk.Frame(resource_frame)
        cpu_row.pack(fill=tk.X, pady=5)
        ttk.Label(cpu_row, text="CPU 使用率:", width=12).pack(side=tk.LEFT)
        self.cpu_progress = ttk.Progressbar(cpu_row, length=200, mode='determinate')
        self.cpu_progress.pack(side=tk.LEFT, padx=5)
        self.cpu_label = ttk.Label(cpu_row, text="0%")
        self.cpu_label.pack(side=tk.LEFT)
        
        # Memory
        mem_row = ttk.Frame(resource_frame)
        mem_row.pack(fill=tk.X, pady=5)
        ttk.Label(mem_row, text="内存占用:", width=12).pack(side=tk.LEFT)
        self.mem_progress = ttk.Progressbar(mem_row, length=200, mode='determinate')
        self.mem_progress.pack(side=tk.LEFT, padx=5)
        self.mem_label = ttk.Label(mem_row, text="0 MB")
        self.mem_label.pack(side=tk.LEFT)
        
        # Threads & Handles
        other_row = ttk.Frame(resource_frame)
        other_row.pack(fill=tk.X, pady=5)
        ttk.Label(other_row, text="线程数:").pack(side=tk.LEFT)
        self.thread_label = ttk.Label(other_row, text="-")
        self.thread_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(other_row, text="句柄数:").pack(side=tk.LEFT)
        self.handle_label = ttk.Label(other_row, text="-")
        self.handle_label.pack(side=tk.LEFT)
        
        # 流量面板
        traffic_frame = ttk.LabelFrame(parent, text="网络流量 (SaveAny-Bot 进程)", padding="10")
        traffic_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 速度
        speed_row = ttk.Frame(traffic_frame)
        speed_row.pack(fill=tk.X, pady=5)
        ttk.Label(speed_row, text="下载速度:").pack(side=tk.LEFT)
        self.download_label = ttk.Label(speed_row, text="0 KB/s", foreground="green", font=('', 11, 'bold'))
        self.download_label.pack(side=tk.LEFT, padx=(5, 30))
        ttk.Label(speed_row, text="上传速度:").pack(side=tk.LEFT)
        self.upload_label = ttk.Label(speed_row, text="0 KB/s", foreground="blue", font=('', 11, 'bold'))
        self.upload_label.pack(side=tk.LEFT)
        
        # 累计
        total_row = ttk.Frame(traffic_frame)
        total_row.pack(fill=tk.X, pady=5)
        ttk.Label(total_row, text="累计下载:").pack(side=tk.LEFT)
        self.total_download_label = ttk.Label(total_row, text="0 MB")
        self.total_download_label.pack(side=tk.LEFT, padx=(5, 30))
        ttk.Label(total_row, text="累计上传:").pack(side=tk.LEFT)
        self.total_upload_label = ttk.Label(total_row, text="0 MB")
        self.total_upload_label.pack(side=tk.LEFT)
        
        # 系统流量
        sys_net_frame = ttk.LabelFrame(parent, text="系统整体网络状态", padding="10")
        sys_net_frame.pack(fill=tk.X, pady=(0, 10))
        sys_net_row = ttk.Frame(sys_net_frame)
        sys_net_row.pack(fill=tk.X)
        ttk.Label(sys_net_row, text="系统下载:").pack(side=tk.LEFT)
        self.sys_download_label = ttk.Label(sys_net_row, text="0 KB/s")
        self.sys_download_label.pack(side=tk.LEFT, padx=(5, 30))
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

    def create_settings_tab(self, parent):
        """创建设置标签页 - 代理和存储设置"""
        # 代理设置
        proxy_frame = ttk.LabelFrame(parent, text="Telegram 代理设置 [telegram.proxy]", padding="10")
        proxy_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 代理启用
        proxy_enable_row = ttk.Frame(proxy_frame)
        proxy_enable_row.pack(fill=tk.X, pady=(0, 5))
        self.proxy_enable_var = tk.BooleanVar(value=False)
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
            self.target_process = os.path.basename(filepath)
            self.path_label.config(text=filepath)
            self.log(f"已选择程序: {filepath}")
            self.update_config_path()

    def start_process(self):
        """启动进程并捕获输出"""
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
            
            # 创建日志目录
            log_dir = os.path.join(work_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            
            # 创建日志文件
            log_filename = datetime.now().strftime("bot_%Y%m%d_%H%M%S.log")
            self.log_file_path = os.path.join(log_dir, log_filename)
            self.log_file = open(self.log_file_path, 'w', encoding='utf-8')
            self.log_path_label.config(text=self.log_file_path, foreground="green")
            
            # 启动进程，捕获输出
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                self.managed_process = subprocess.Popen(
                    [self.target_path],
                    cwd=work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    startupinfo=startupinfo,
                    bufsize=1,
                    universal_newlines=True,
                    encoding='utf-8',
                    errors='replace'
                )
            else:
                self.managed_process = subprocess.Popen(
                    [self.target_path],
                    cwd=work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True,
                    encoding='utf-8',
                    errors='replace'
                )
            
            # 启动读取输出的线程
            threading.Thread(target=self.read_process_output, daemon=True).start()
            
            self.log("SaveAny-Bot 已启动并开始捕获日志")
            self.status_bar.config(text="SaveAny-Bot 运行中")
            
        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {str(e)}")
            if self.log_file:
                self.log_file.close()
                self.log_file = None

    def read_process_output(self):
        """在后台线程中读取进程输出"""
        if not self.managed_process:
            return
        
        try:
            for line in iter(self.managed_process.stdout.readline, ''):
                if not self.running:
                    break
                line = line.strip()
                if line:
                    self.add_console_log(line)
            
            self.managed_process.stdout.close()
            return_code = self.managed_process.wait()
            self.log(f"SaveAny-Bot 进程已退出，退出码: {return_code}")
            self.status_bar.config(text="SaveAny-Bot 已停止")
            
            if self.log_file:
                self.log_file.close()
                self.log_file = None
                
        except Exception as e:
            self.log(f"读取输出错误: {str(e)}")

    def stop_process(self):
        proc = self.find_process()
        if proc:
            try:
                proc.terminate()
                self.log(f"已发送终止信号给进程 PID: {proc.pid}")
                self.status_bar.config(text="正在停止进程...")
            except Exception as e:
                messagebox.showerror("错误", f"停止失败: {str(e)}")
        else:
            messagebox.showinfo("提示", "进程未在运行")

    def restart_process(self):
        self.stop_process()
        self.root.after(2000, self.start_process)

    def open_folder(self):
        if self.target_path:
            dir_path = os.path.dirname(self.target_path)
            if sys.platform == 'win32':
                os.startfile(dir_path)
            else:
                subprocess.Popen(['xdg-open', dir_path])
        else:
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")

    def load_config(self):
        global config_path
        if not config_path or not os.path.exists(config_path):
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.config_editor.delete('1.0', tk.END)
            self.config_editor.insert(tk.END, content)
            self.config_status.config(text=f"配置已加载: {config_path}", foreground="green")
            self.log("配置文件已加载")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")

    def save_config(self):
        global config_path
        if not config_path:
            messagebox.showwarning("警告", "请先加载配置文件")
            return
        
        try:
            content = self.config_editor.get('1.0', tk.END).strip()
            # 备份
            with open(config_path + ".bak", 'w', encoding='utf-8') as f:
                f.write(open(config_path, 'r', encoding='utf-8').read())
            # 写入
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.config_status.config(text="配置已保存并备份 (.bak)", foreground="green")
            self.log("配置文件已保存")
            messagebox.showinfo("成功", "配置文件已保存！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")

    def reload_config(self):
        self.load_config()

    def start_web_server(self):
        try:
            port = int(self.port_entry.get())
            self.web_server = StoppableHTTPServer(('0.0.0.0', port), MonitorHTTPHandler)
            self.web_thread = threading.Thread(target=self.web_server.serve_forever_stoppable, daemon=True)
            self.web_thread.start()
            
            self.web_status_label.config(text="运行中", foreground="green")
            self.start_web_btn.config(state=tk.DISABLED)
            self.stop_web_btn.config(state=tk.NORMAL)
            self.open_browser_btn.config(state=tk.NORMAL)
            
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            url = f"http://{local_ip}:{port}"
            self.url_label.config(text=url)
            self.log(f"Web 服务已启动: {url}")
        except Exception as e:
            messagebox.showerror("错误", f"Web 服务启动失败: {str(e)}")

    def stop_web_server(self):
        if self.web_server:
            self.web_server.stop()
            self.web_server = None
            self.web_status_label.config(text="已停止", foreground="red")
            self.start_web_btn.config(state=tk.NORMAL)
            self.stop_web_btn.config(state=tk.DISABLED)
            self.open_browser_btn.config(state=tk.DISABLED)
            self.url_label.config(text="Web 服务已停止")
            self.log("Web 服务已停止")

    def open_web_browser(self):
        port = self.port_entry.get()
        webbrowser.open(f"http://127.0.0.1:{port}")

    def handle_web_control(self, action):
        """处理来自 Web 的控制请求"""
        if action == 'start':
            if self.find_process():
                return False, "进程已在运行"
            self.root.after(10, self.start_process)
            return True, "正在启动..."
        elif action == 'stop':
            if not self.find_process():
                return False, "进程未运行"
            self.root.after(10, self.stop_process)
            return True, "正在停止..."
        elif action == 'restart':
            self.root.after(10, self.restart_process)
            return True, "正在重启..."
        return False, "无效操作"

    def auto_detect(self):
        proc = self.find_process()
        if proc:
            try:
                exe_path = proc.exe()
                if exe_path:
                    self.target_path = exe_path
                    self.path_label.config(text=exe_path)
                    self.update_config_path()
                    self.log(f"自动检测到运行中的程序: {exe_path}")
            except Exception:
                pass

    def test_proxy_connection(self):
        """测试代理连接"""
        url = self.proxy_url_entry.get().strip()
        if not url:
            messagebox.showwarning("警告", "请输入代理地址")
            return
        
        self.proxy_status_label.config(text="测试中...", foreground="blue")
        self.root.update_idletasks()
        
        def run_test():
            try:
                import socks
                import socket
                
                # 解析 socks5://127.0.0.1:7890
                if '://' in url:
                    addr = url.split('://')[1]
                else:
                    addr = url
                
                if '@' in addr:
                    auth, server = addr.split('@')
                    user, pwd = auth.split(':')
                    host, port = server.split(':')
                else:
                    user, pwd = None, None
                    host, port = addr.split(':')
                
                s = socks.socksocket()
                s.set_proxy(socks.SOCKS5, host, int(port), username=user, password=pwd)
                s.settimeout(5)
                s.connect(("google.com", 80))
                s.close()
                self.root.after(0, lambda: self.proxy_status_label.config(text="连接成功", foreground="green"))
            except Exception as e:
                self.root.after(0, lambda: self.proxy_status_label.config(text=f"失败: {str(e)[:20]}", foreground="red"))
        
        threading.Thread(target=run_test, daemon=True).start()

    def load_proxy_from_config(self):
        """从配置文件加载代理设置"""
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            enable_match = re.search(r'\[telegram\.proxy\][\s\S]*?enable\s*=\s*(true|false)', content, re.IGNORECASE)
            if enable_match:
                self.proxy_enable_var.set(enable_match.group(1).lower() == 'true')
            
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
            
            import re
            if re.search(r'\[telegram\.proxy\]', content):
                content = re.sub(
                    r'(\[telegram\.proxy\][\s\S]*?enable\s*=\s*)(true|false)',
                    f'\\1{enable}', content, flags=re.IGNORECASE
                )
                content = re.sub(
                    r'(\[telegram\.proxy\][\s\S]*?url\s*=\s*)["\'][^"\']*["\']',
                    f'\\1"{url}"', content
                )
            else:
                proxy_config = f'''\n[telegram.proxy]\nenable = {enable}\nurl = "{url}"\n'''
                if '[telegram]' in content:
                    match = re.search(r'(\[telegram\][^\[]*)', content)
                    if match:
                        insert_pos = match.end()
                        content = content[:insert_pos] + proxy_config + content[insert_pos:]
                else:
                    content += proxy_config
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.settings_status.config(text="代理设置已保存到配置文件", foreground="green")
            self.log("已保存代理设置")
            messagebox.showinfo("成功", "代理设置已保存！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")

    def browse_storage_path(self):
        folder = filedialog.askdirectory(title="选择保存路径")
        if folder:
            self.storage_path_entry.delete(0, tk.END)
            self.storage_path_entry.insert(0, folder.replace('/', '\\') if sys.platform == 'win32' else folder)

    def load_storage_from_config(self):
        global config_path
        if not config_path or not os.path.exists(config_path):
            messagebox.showwarning("警告", "请先选择 SaveAny-Bot 程序路径")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            storage_match = re.search(
                r'\[\[storages\]\][\s\S]*?name\s*=\s*["\']([^"\']+)["\'][\s\S]*?type\s*=\s*["\']([^"\']+)["\'][\s\S]*?enable\s*=\s*(true|false)[\s\S]*?base_path\s*=\s*["\']([^"\']+)["\']',
                content, re.IGNORECASE
            )
            
            if storage_match:
                self.storage_name_entry.delete(0, tk.END)
                self.storage_name_entry.insert(0, storage_match.group(1))
                self.storage_type_var.set(storage_match.group(2))
                self.storage_enable_var.set(storage_match.group(3).lower() == 'true')
                self.storage_path_entry.delete(0, tk.END)
                self.storage_path_entry.insert(0, storage_match.group(4))
                self.settings_status.config(text="存储设置已从配置文件加载", foreground="green")
                self.log("已加载存储设置")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")

    def save_storage_to_config(self):
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
            
            import re
            if re.search(r'\[\[storages\]\]', content):
                content = re.sub(r'(\[\[storages\]\][\s\S]*?name\s*=\s*)["\'][^"\']*["\']', f'\\1"{name}"', content, count=1)
                content = re.sub(r'(\[\[storages\]\][\s\S]*?type\s*=\s*)["\'][^"\']*["\']', f'\\1"{storage_type}"', content, count=1)
                content = re.sub(r'(\[\[storages\]\][\s\S]*?enable\s*=\s*)(true|false)', f'\\1{enable}', content, count=1, flags=re.IGNORECASE)
                content = re.sub(r'(\[\[storages\]\][\s\S]*?base_path\s*=\s*)["\'][^"\']*["\']', f'\\1"{base_path}"', content, count=1)
            else:
                storage_config = f'''\n[[storages]]\nname = "{name}"\ntype = "{storage_type}"\nenable = {enable}\nbase_path = "{base_path}"\n'''
                content += storage_config
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.settings_status.config(text="存储设置已保存到配置文件", foreground="green")
            self.log("已保存存储设置")
            messagebox.showinfo("成功", "存储设置已保存！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")

    def get_settings_file_path(self):
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(app_dir, 'monitor_settings.ini')

    def load_auto_load_setting(self):
        try:
            settings_file = self.get_settings_file_path()
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('auto_load_config='):
                            return line.strip().split('=')[1].lower() == 'true'
        except Exception:
            pass
        return False

    def save_auto_load_setting(self):
        try:
            settings_file = self.get_settings_file_path()
            auto_load = self.auto_load_config_var.get()
            settings = {}
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            settings[key] = value
            settings['auto_load_config'] = 'true' if auto_load else 'false'
            with open(settings_file, 'w', encoding='utf-8') as f:
                for key, value in settings.items():
                    f.write(f'{key}={value}\n')
            self.settings_status.config(text="设置已更新", foreground="green")
        except Exception as e:
            self.settings_status.config(text=f"保存失败: {str(e)}", foreground="red")

    def auto_load_settings_on_startup(self):
        global config_path
        if not self.load_auto_load_setting() or not config_path or not os.path.exists(config_path):
            return
        try:
            self.load_proxy_from_config_silent()
            self.load_storage_from_config_silent()
            self.log("已自动加载配置文件设置")
        except Exception:
            pass

    def load_proxy_from_config_silent(self):
        global config_path
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            import re
            enable_match = re.search(r'\[telegram\.proxy\][\s\S]*?enable\s*=\s*(true|false)', content, re.IGNORECASE)
            if enable_match:
                self.proxy_enable_var.set(enable_match.group(1).lower() == 'true')
            url_match = re.search(r'\[telegram\.proxy\][\s\S]*?url\s*=\s*["\']([^"\']+)["\']', content)
            if url_match:
                self.proxy_url_entry.delete(0, tk.END)
                self.proxy_url_entry.insert(0, url_match.group(1))
        except Exception:
            pass

    def load_storage_from_config_silent(self):
        global config_path
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            import re
            storage_match = re.search(r'\[\[storages\]\]([\s\S]*?)(?=\[\[|$)', content)
            if storage_match:
                storage_content = storage_match.group(1)
                name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', storage_content)
                if name_match:
                    self.storage_name_entry.delete(0, tk.END)
                    self.storage_name_entry.insert(0, name_match.group(1))
                type_match = re.search(r'type\s*=\s*["\']([^"\']+)["\']', storage_content)
                if type_match:
                    self.storage_type_var.set(type_match.group(1))
                enable_match = re.search(r'enable\s*=\s*(true|false)', storage_content, re.IGNORECASE)
                if enable_match:
                    self.storage_enable_var.set(enable_match.group(1).lower() == 'true')
                path_match = re.search(r'base_path\s*=\s*["\']([^"\']+)["\']', storage_content)
                if path_match:
                    self.storage_path_entry.delete(0, tk.END)
                    self.storage_path_entry.insert(0, path_match.group(1))
        except Exception:
            pass

    def on_closing(self):
        self.running = False
        if self.web_server:
            try: self.web_server.stop()
            except Exception: pass
        if self.log_file:
            try: self.log_file.close()
            except Exception: pass
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    style = ttk.Style()
    try: style.theme_use('vista')
    except Exception:
        try: style.theme_use('clam')
        except Exception: pass
    app = SaveAnyMonitor(root)
    root.mainloop()

if __name__ == "__main__":
    main()
