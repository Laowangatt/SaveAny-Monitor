#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SaveAny-Monitor Server v1.0
账号管理和在线验证服务端
提供 HTTP API 用于客户端验证
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import os
import hashlib
import base64
import hmac
import secrets
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import socket

# 加密密钥
SECRET_KEY = b'SaveAny-Monitor-Auth-Key-2024-Secure'

# 全局变量
server_instance = None
accounts = {}
server_log = []
ACCOUNTS_FILE = 'accounts.dat'


def generate_salt() -> str:
    """生成随机盐值"""
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    """使用 PBKDF2 对密码进行哈希"""
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return base64.b64encode(key).decode('utf-8')


def create_signature(data: str) -> str:
    """创建数据签名"""
    signature = hmac.new(SECRET_KEY, data.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(signature.digest()).decode('utf-8')


def verify_signature(data: str, signature: str) -> bool:
    """验证数据签名"""
    expected = create_signature(data)
    return hmac.compare_digest(expected, signature)


def encrypt_data(data: dict) -> str:
    """加密数据"""
    json_str = json.dumps(data, ensure_ascii=False)
    signature = create_signature(json_str)
    full_data = {'data': data, 'signature': signature}
    encoded = base64.b64encode(json.dumps(full_data, ensure_ascii=False).encode('utf-8'))
    result = []
    for i, b in enumerate(encoded):
        result.append(b ^ (i % 256))
    return base64.b64encode(bytes(result)).decode('utf-8')


def decrypt_data(encrypted: str) -> dict:
    """解密数据"""
    try:
        data = base64.b64decode(encrypted.encode('utf-8'))
        result = []
        for i, b in enumerate(data):
            result.append(b ^ (i % 256))
        decoded = base64.b64decode(bytes(result))
        full_data = json.loads(decoded.decode('utf-8'))
        json_str = json.dumps(full_data['data'], ensure_ascii=False)
        if not verify_signature(json_str, full_data['signature']):
            return None
        return full_data['data']
    except Exception:
        return None


def load_accounts():
    """加载账号数据"""
    global accounts
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                encrypted = f.read()
            data = decrypt_data(encrypted)
            if data:
                accounts = data.get('accounts', {})
                return
        except Exception:
            pass
    accounts = {}


def save_accounts():
    """保存账号数据"""
    global accounts
    data = {'accounts': accounts, 'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    encrypted = encrypt_data(data)
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        f.write(encrypted)


def add_log(message: str):
    """添加日志"""
    global server_log
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    server_log.append(log_entry)
    if len(server_log) > 1000:
        server_log = server_log[-500:]


class AuthHandler(BaseHTTPRequestHandler):
    """认证 API 处理器"""
    
    def log_message(self, format, *args):
        add_log(f"HTTP: {args[0]}")
    
    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """处理 GET 请求"""
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/status':
            self.send_json({'status': 'online', 'version': '1.0'})
        else:
            self.send_error(404)
    
    def do_POST(self):
        """处理 POST 请求"""
        global accounts
        
        parsed = urlparse(self.path)
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}
        except Exception:
            data = {}
        
        if parsed.path == '/api/verify':
            # 验证账号
            username = data.get('username', '')
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json({'success': False, 'message': '用户名和密码不能为空'})
                add_log(f"验证失败: 空用户名或密码")
                return
            
            if username not in accounts:
                self.send_json({'success': False, 'message': '账号不存在'})
                add_log(f"验证失败: 账号 {username} 不存在")
                return
            
            account = accounts[username]
            if not account.get('enabled', True):
                self.send_json({'success': False, 'message': '账号已禁用'})
                add_log(f"验证失败: 账号 {username} 已禁用")
                return
            
            password_hash = hash_password(password, account['salt'])
            if password_hash != account['password_hash']:
                self.send_json({'success': False, 'message': '密码错误'})
                add_log(f"验证失败: 账号 {username} 密码错误")
                return
            
            # 生成 token
            token_data = {
                'username': username,
                'issued': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'valid': True
            }
            token = encrypt_data(token_data)
            
            self.send_json({
                'success': True, 
                'message': '验证成功',
                'token': token,
                'username': username
            })
            add_log(f"验证成功: 账号 {username}")
        
        elif parsed.path == '/api/validate_token':
            # 验证 token
            token = data.get('token', '')
            if not token:
                self.send_json({'success': False, 'message': 'Token 不能为空'})
                return
            
            token_data = decrypt_data(token)
            if not token_data:
                self.send_json({'success': False, 'message': 'Token 无效'})
                return
            
            username = token_data.get('username', '')
            if username not in accounts:
                self.send_json({'success': False, 'message': '账号不存在'})
                return
            
            if not accounts[username].get('enabled', True):
                self.send_json({'success': False, 'message': '账号已禁用'})
                return
            
            self.send_json({
                'success': True,
                'message': 'Token 有效',
                'username': username
            })
        
        else:
            self.send_error(404)
    
    def send_json(self, data):
        """发送 JSON 响应"""
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content)


class ServerApp:
    """服务端主程序"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("SaveAny-Monitor Server v1.0")
        self.root.geometry("700x550")
        self.root.resizable(True, True)
        self.root.minsize(600, 450)
        
        self.server = None
        self.server_thread = None
        self.running = False
        
        load_accounts()
        self.create_widgets()
        self.update_accounts_list()
        self.update_log()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        # 创建 Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 服务器控制页
        self.server_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.server_frame, text="服务器")
        self.create_server_tab()
        
        # 账号管理页
        self.accounts_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.accounts_frame, text="账号管理")
        self.create_accounts_tab()
        
        # 日志页
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text="日志")
        self.create_log_tab()
    
    def create_server_tab(self):
        # 服务器配置
        config_frame = ttk.LabelFrame(self.server_frame, text="服务器配置")
        config_frame.pack(fill='x', padx=10, pady=10)
        
        # 端口设置
        port_frame = ttk.Frame(config_frame)
        port_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(port_frame, text="监听端口:").pack(side='left')
        self.port_var = tk.StringVar(value="8899")
        self.port_entry = ttk.Entry(port_frame, textvariable=self.port_var, width=10)
        self.port_entry.pack(side='left', padx=5)
        
        ttk.Label(port_frame, text="(默认: 8899)").pack(side='left')
        
        # 控制按钮
        btn_frame = ttk.Frame(config_frame)
        btn_frame.pack(fill='x', padx=10, pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="启动服务", command=self.start_server, width=15)
        self.start_btn.pack(side='left', padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="停止服务", command=self.stop_server, width=15, state='disabled')
        self.stop_btn.pack(side='left', padx=5)
        
        # 状态显示
        status_frame = ttk.LabelFrame(self.server_frame, text="服务器状态")
        status_frame.pack(fill='x', padx=10, pady=10)
        
        self.status_label = ttk.Label(status_frame, text="状态: 未启动", font=('Segoe UI', 12))
        self.status_label.pack(padx=10, pady=10)
        
        # 连接信息
        info_frame = ttk.LabelFrame(self.server_frame, text="连接信息")
        info_frame.pack(fill='x', padx=10, pady=10)
        
        self.info_text = tk.Text(info_frame, height=6, wrap='word')
        self.info_text.pack(fill='x', padx=10, pady=10)
        self.info_text.insert('1.0', "服务未启动\n\n客户端配置说明:\n1. 在客户端设置中填入服务器地址\n2. 格式: http://服务器IP:端口\n3. 例如: http://192.168.1.100:8899")
        self.info_text.config(state='disabled')
    
    def create_accounts_tab(self):
        # 添加账号
        add_frame = ttk.LabelFrame(self.accounts_frame, text="添加账号")
        add_frame.pack(fill='x', padx=10, pady=10)
        
        form_frame = ttk.Frame(add_frame)
        form_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(form_frame, text="用户名:").grid(row=0, column=0, sticky='w', pady=2)
        self.new_username = ttk.Entry(form_frame, width=20)
        self.new_username.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(form_frame, text="密码:").grid(row=0, column=2, sticky='w', pady=2)
        self.new_password = ttk.Entry(form_frame, width=20, show='*')
        self.new_password.grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Button(form_frame, text="添加", command=self.add_account, width=10).grid(row=0, column=4, padx=10, pady=2)
        
        # 账号列表
        list_frame = ttk.LabelFrame(self.accounts_frame, text="账号列表")
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 创建 Treeview
        columns = ('username', 'created', 'status')
        self.accounts_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
        
        self.accounts_tree.heading('username', text='用户名')
        self.accounts_tree.heading('created', text='创建时间')
        self.accounts_tree.heading('status', text='状态')
        
        self.accounts_tree.column('username', width=150)
        self.accounts_tree.column('created', width=150)
        self.accounts_tree.column('status', width=80)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.accounts_tree.yview)
        self.accounts_tree.configure(yscrollcommand=scrollbar.set)
        
        self.accounts_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # 操作按钮
        btn_frame = ttk.Frame(self.accounts_frame)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(btn_frame, text="删除选中", command=self.delete_account, width=12).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="启用/禁用", command=self.toggle_account, width=12).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="刷新列表", command=self.update_accounts_list, width=12).pack(side='left', padx=5)
    
    def create_log_tab(self):
        # 日志显示
        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap='word', height=20)
        self.log_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 清空按钮
        btn_frame = ttk.Frame(self.log_frame)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(btn_frame, text="清空日志", command=self.clear_log, width=12).pack(side='left', padx=5)
    
    def start_server(self):
        try:
            port = int(self.port_var.get())
            if port < 1 or port > 65535:
                raise ValueError("端口范围错误")
        except ValueError:
            messagebox.showerror("错误", "请输入有效的端口号 (1-65535)")
            return
        
        try:
            self.server = HTTPServer(('0.0.0.0', port), AuthHandler)
            self.running = True
            
            self.server_thread = threading.Thread(target=self.run_server, daemon=True)
            self.server_thread.start()
            
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.port_entry.config(state='disabled')
            self.status_label.config(text=f"状态: 运行中 (端口: {port})", foreground='green')
            
            # 更新连接信息
            local_ip = self.get_local_ip()
            info = f"服务已启动!\n\n"
            info += f"本机地址: http://{local_ip}:{port}\n"
            info += f"本地地址: http://127.0.0.1:{port}\n\n"
            info += f"客户端配置: 在设置中填入上述地址"
            
            self.info_text.config(state='normal')
            self.info_text.delete('1.0', 'end')
            self.info_text.insert('1.0', info)
            self.info_text.config(state='disabled')
            
            add_log(f"服务器启动成功，监听端口: {port}")
            
        except Exception as e:
            messagebox.showerror("错误", f"启动服务器失败: {str(e)}")
            add_log(f"服务器启动失败: {str(e)}")
    
    def run_server(self):
        while self.running:
            self.server.handle_request()
    
    def stop_server(self):
        self.running = False
        if self.server:
            self.server.shutdown()
            self.server = None
        
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.port_entry.config(state='normal')
        self.status_label.config(text="状态: 已停止", foreground='red')
        
        self.info_text.config(state='normal')
        self.info_text.delete('1.0', 'end')
        self.info_text.insert('1.0', "服务未启动\n\n客户端配置说明:\n1. 在客户端设置中填入服务器地址\n2. 格式: http://服务器IP:端口\n3. 例如: http://192.168.1.100:8899")
        self.info_text.config(state='disabled')
        
        add_log("服务器已停止")
    
    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def add_account(self):
        global accounts
        
        username = self.new_username.get().strip()
        password = self.new_password.get()
        
        if not username or not password:
            messagebox.showerror("错误", "用户名和密码不能为空")
            return
        
        if len(username) < 3:
            messagebox.showerror("错误", "用户名至少3个字符")
            return
        
        if len(password) < 6:
            messagebox.showerror("错误", "密码至少6个字符")
            return
        
        if username in accounts:
            messagebox.showerror("错误", "用户名已存在")
            return
        
        salt = generate_salt()
        password_hash = hash_password(password, salt)
        
        accounts[username] = {
            'salt': salt,
            'password_hash': password_hash,
            'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'enabled': True
        }
        save_accounts()
        
        self.new_username.delete(0, 'end')
        self.new_password.delete(0, 'end')
        
        self.update_accounts_list()
        add_log(f"添加账号: {username}")
        messagebox.showinfo("成功", f"账号 {username} 创建成功")
    
    def delete_account(self):
        global accounts
        
        selected = self.accounts_tree.selection()
        if not selected:
            messagebox.showwarning("警告", "请先选择要删除的账号")
            return
        
        username = self.accounts_tree.item(selected[0])['values'][0]
        
        if messagebox.askyesno("确认", f"确定要删除账号 {username} 吗?"):
            if username in accounts:
                del accounts[username]
                save_accounts()
                self.update_accounts_list()
                add_log(f"删除账号: {username}")
                messagebox.showinfo("成功", f"账号 {username} 已删除")
    
    def toggle_account(self):
        global accounts
        
        selected = self.accounts_tree.selection()
        if not selected:
            messagebox.showwarning("警告", "请先选择账号")
            return
        
        username = self.accounts_tree.item(selected[0])['values'][0]
        
        if username in accounts:
            accounts[username]['enabled'] = not accounts[username].get('enabled', True)
            save_accounts()
            self.update_accounts_list()
            status = "启用" if accounts[username]['enabled'] else "禁用"
            add_log(f"账号 {username} 已{status}")
    
    def update_accounts_list(self):
        global accounts
        
        for item in self.accounts_tree.get_children():
            self.accounts_tree.delete(item)
        
        for username, info in accounts.items():
            status = "启用" if info.get('enabled', True) else "禁用"
            self.accounts_tree.insert('', 'end', values=(
                username,
                info.get('created', ''),
                status
            ))
    
    def update_log(self):
        global server_log
        
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.insert('1.0', '\n'.join(server_log))
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        
        self.root.after(1000, self.update_log)
    
    def clear_log(self):
        global server_log
        server_log = []
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.config(state='disabled')
    
    def on_closing(self):
        if self.running:
            if messagebox.askyesno("确认", "服务器正在运行，确定要退出吗?"):
                self.stop_server()
                self.root.destroy()
        else:
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
    
    app = ServerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
