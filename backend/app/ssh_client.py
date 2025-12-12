import paramiko
from typing import Optional, Tuple
from pathlib import Path


class SSHClient:
    """SSH 连接管理器"""
    
    def __init__(
        self,
        host: str,
        username: str,
        port: int = 22,
        password: Optional[str] = None,
        private_key_path: Optional[str] = None,
    ):
        self.host = host
        self.username = username
        self.port = port
        self.password = password
        self.private_key_path = private_key_path
        self._client: Optional[paramiko.SSHClient] = None
    
    def connect(self) -> None:
        """建立 SSH 连接"""
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        connect_kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": 30,
        }
        
        if self.private_key_path:
            # 使用私钥认证
            key_path = Path(self.private_key_path).expanduser()
            connect_kwargs["key_filename"] = str(key_path)
        elif self.password:
            # 使用密码认证
            connect_kwargs["password"] = self.password
        else:
            # 尝试使用默认私钥
            default_key = Path.home() / ".ssh" / "id_rsa"
            if default_key.exists():
                connect_kwargs["key_filename"] = str(default_key)
        
        self._client.connect(**connect_kwargs)
    
    def disconnect(self) -> None:
        """关闭 SSH 连接"""
        if self._client:
            self._client.close()
            self._client = None
    
    def execute(self, command: str) -> Tuple[str, str, int]:
        """
        执行远程命令
        
        Returns:
            (stdout, stderr, exit_code)
        """
        if not self._client:
            raise RuntimeError("SSH client not connected")
        
        stdin, stdout, stderr = self._client.exec_command(command, timeout=300)
        exit_code = stdout.channel.recv_exit_status()
        
        return (
            stdout.read().decode("utf-8", errors="ignore"),
            stderr.read().decode("utf-8", errors="ignore"),
            exit_code,
        )
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        测试 SSH 连接
        
        Returns:
            (success, message)
        """
        try:
            self.connect()
            stdout, stderr, code = self.execute("echo 'OK'")
            self.disconnect()
            if code == 0 and "OK" in stdout:
                return True, "Connection successful"
            return False, f"Command failed: {stderr}"
        except Exception as e:
            return False, str(e)
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
