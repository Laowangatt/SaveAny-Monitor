#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SaveAny-Monitor 认证模块
提供账号密码的加密、验证和授权文件管理功能
"""

import os
import json
import hashlib
import base64
import hmac
import secrets
from datetime import datetime
from typing import Optional, Tuple, Dict, List

# 加密密钥（用于 HMAC 签名）
SECRET_KEY = b'SaveAny-Monitor-Auth-Key-2024-Secure'

# 授权文件名
LICENSE_FILE = 'license.dat'
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
        100000  # 迭代次数
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
    """加密数据（简单的混淆加密）"""
    json_str = json.dumps(data, ensure_ascii=False)
    # 添加签名
    signature = create_signature(json_str)
    full_data = {'data': data, 'signature': signature}
    # Base64 编码
    encoded = base64.b64encode(json.dumps(full_data, ensure_ascii=False).encode('utf-8'))
    # 简单混淆
    result = []
    for i, b in enumerate(encoded):
        result.append(b ^ (i % 256))
    return base64.b64encode(bytes(result)).decode('utf-8')


def decrypt_data(encrypted: str) -> Optional[dict]:
    """解密数据"""
    try:
        # 反混淆
        data = base64.b64decode(encrypted.encode('utf-8'))
        result = []
        for i, b in enumerate(data):
            result.append(b ^ (i % 256))
        # Base64 解码
        decoded = base64.b64decode(bytes(result))
        full_data = json.loads(decoded.decode('utf-8'))
        # 验证签名
        json_str = json.dumps(full_data['data'], ensure_ascii=False)
        if not verify_signature(json_str, full_data['signature']):
            return None
        return full_data['data']
    except Exception:
        return None


class AccountManager:
    """账号管理器（服务端使用）"""
    
    def __init__(self, accounts_file: str = ACCOUNTS_FILE):
        self.accounts_file = accounts_file
        self.accounts: Dict[str, dict] = {}
        self.load_accounts()
    
    def load_accounts(self):
        """加载账号数据"""
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    encrypted = f.read()
                data = decrypt_data(encrypted)
                if data:
                    self.accounts = data.get('accounts', {})
            except Exception:
                self.accounts = {}
    
    def save_accounts(self):
        """保存账号数据"""
        data = {'accounts': self.accounts, 'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        encrypted = encrypt_data(data)
        with open(self.accounts_file, 'w', encoding='utf-8') as f:
            f.write(encrypted)
    
    def add_account(self, username: str, password: str) -> Tuple[bool, str]:
        """添加账号"""
        if not username or not password:
            return False, "用户名和密码不能为空"
        if len(username) < 3:
            return False, "用户名至少3个字符"
        if len(password) < 6:
            return False, "密码至少6个字符"
        if username in self.accounts:
            return False, "用户名已存在"
        
        salt = generate_salt()
        password_hash = hash_password(password, salt)
        
        self.accounts[username] = {
            'salt': salt,
            'password_hash': password_hash,
            'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'enabled': True
        }
        self.save_accounts()
        return True, "账号创建成功"
    
    def delete_account(self, username: str) -> Tuple[bool, str]:
        """删除账号"""
        if username not in self.accounts:
            return False, "账号不存在"
        del self.accounts[username]
        self.save_accounts()
        return True, "账号删除成功"
    
    def verify_account(self, username: str, password: str) -> Tuple[bool, str]:
        """验证账号密码"""
        if username not in self.accounts:
            return False, "账号不存在"
        
        account = self.accounts[username]
        if not account.get('enabled', True):
            return False, "账号已禁用"
        
        password_hash = hash_password(password, account['salt'])
        if password_hash != account['password_hash']:
            return False, "密码错误"
        
        return True, "验证成功"
    
    def list_accounts(self) -> List[dict]:
        """列出所有账号"""
        result = []
        for username, info in self.accounts.items():
            result.append({
                'username': username,
                'created': info.get('created', ''),
                'enabled': info.get('enabled', True)
            })
        return result
    
    def toggle_account(self, username: str) -> Tuple[bool, str]:
        """启用/禁用账号"""
        if username not in self.accounts:
            return False, "账号不存在"
        self.accounts[username]['enabled'] = not self.accounts[username].get('enabled', True)
        self.save_accounts()
        status = "启用" if self.accounts[username]['enabled'] else "禁用"
        return True, f"账号已{status}"
    
    def generate_license(self, username: str, password: str) -> Tuple[bool, str, str]:
        """生成授权文件内容"""
        success, msg = self.verify_account(username, password)
        if not success:
            return False, msg, ""
        
        license_data = {
            'username': username,
            'password_hash': self.accounts[username]['password_hash'],
            'salt': self.accounts[username]['salt'],
            'issued': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'machine_id': get_machine_id()
        }
        license_content = encrypt_data(license_data)
        return True, "授权文件生成成功", license_content


class LicenseManager:
    """授权管理器（客户端使用）"""
    
    def __init__(self, license_file: str = LICENSE_FILE):
        self.license_file = license_file
        self.license_data: Optional[dict] = None
        self.load_license()
    
    def load_license(self) -> bool:
        """加载授权文件"""
        if os.path.exists(self.license_file):
            try:
                with open(self.license_file, 'r', encoding='utf-8') as f:
                    encrypted = f.read()
                self.license_data = decrypt_data(encrypted)
                return self.license_data is not None
            except Exception:
                return False
        return False
    
    def save_license(self, license_content: str) -> bool:
        """保存授权文件"""
        try:
            with open(self.license_file, 'w', encoding='utf-8') as f:
                f.write(license_content)
            return True
        except Exception:
            return False
    
    def is_licensed(self) -> bool:
        """检查是否已授权"""
        return self.license_data is not None
    
    def get_username(self) -> str:
        """获取授权用户名"""
        if self.license_data:
            return self.license_data.get('username', '')
        return ''
    
    def verify_offline(self, username: str, password: str) -> Tuple[bool, str]:
        """离线验证账号密码（使用本地授权文件）"""
        if not self.license_data:
            return False, "未找到授权文件"
        
        if self.license_data.get('username') != username:
            return False, "用户名不匹配"
        
        salt = self.license_data.get('salt', '')
        stored_hash = self.license_data.get('password_hash', '')
        
        password_hash = hash_password(password, salt)
        if password_hash != stored_hash:
            return False, "密码错误"
        
        return True, "验证成功"
    
    def create_license_from_login(self, username: str, password: str, accounts_data: str) -> Tuple[bool, str]:
        """从登录信息创建授权（需要账号数据）"""
        try:
            data = decrypt_data(accounts_data)
            if not data:
                return False, "账号数据无效"
            
            accounts = data.get('accounts', {})
            if username not in accounts:
                return False, "账号不存在"
            
            account = accounts[username]
            if not account.get('enabled', True):
                return False, "账号已禁用"
            
            password_hash = hash_password(password, account['salt'])
            if password_hash != account['password_hash']:
                return False, "密码错误"
            
            # 创建授权数据
            license_data = {
                'username': username,
                'password_hash': account['password_hash'],
                'salt': account['salt'],
                'issued': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'machine_id': get_machine_id()
            }
            license_content = encrypt_data(license_data)
            
            if self.save_license(license_content):
                self.license_data = license_data
                return True, "授权成功"
            else:
                return False, "保存授权文件失败"
        except Exception as e:
            return False, f"授权失败: {str(e)}"


def get_machine_id() -> str:
    """获取机器标识（用于绑定授权）"""
    try:
        import platform
        import uuid
        machine_info = f"{platform.node()}-{platform.machine()}-{uuid.getnode()}"
        return hashlib.md5(machine_info.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


if __name__ == '__main__':
    # 测试代码
    print("测试加密模块...")
    
    # 测试加密解密
    test_data = {'username': 'test', 'password': '123456'}
    encrypted = encrypt_data(test_data)
    print(f"加密后: {encrypted[:50]}...")
    decrypted = decrypt_data(encrypted)
    print(f"解密后: {decrypted}")
    
    # 测试账号管理
    manager = AccountManager('test_accounts.dat')
    success, msg = manager.add_account('admin', 'admin123')
    print(f"添加账号: {msg}")
    
    success, msg = manager.verify_account('admin', 'admin123')
    print(f"验证账号: {msg}")
    
    # 清理测试文件
    if os.path.exists('test_accounts.dat'):
        os.remove('test_accounts.dat')
