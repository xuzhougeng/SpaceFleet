from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Server(Base):
    """服务器配置"""
    __tablename__ = "servers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)  # 服务器名称
    host = Column(String(255), nullable=False)  # IP 或域名
    port = Column(Integer, default=22)  # SSH 端口
    username = Column(String(100), nullable=False)  # SSH 用户名
    auth_type = Column(String(20), default="key")  # password 或 key
    private_key_path = Column(String(500), nullable=True)  # SSH 私钥路径
    password = Column(String(255), nullable=True)  # SSH 密码 (加密存储)
    os_type = Column(String(20), default="ubuntu")  # ubuntu / centos
    description = Column(Text, nullable=True)  # 服务器描述
    scan_mounts = Column(Text, nullable=True)  # 要扫描的挂载点，逗号分隔，空表示全部
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    disk_usages = relationship("DiskUsage", back_populates="server", cascade="all, delete-orphan")
    user_disk_usages = relationship("UserDiskUsage", back_populates="server", cascade="all, delete-orphan")


class DiskUsage(Base):
    """磁盘使用记录"""
    __tablename__ = "disk_usages"
    
    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    device = Column(String(100))  # 设备名 /dev/sdb1
    filesystem = Column(String(50))  # 文件系统类型 ext4, xfs
    mount_point = Column(String(255), nullable=False)  # 挂载点 /, /data
    total_gb = Column(Float, nullable=False)  # 总容量 GB
    used_gb = Column(Float, nullable=False)  # 已使用 GB
    free_gb = Column(Float, nullable=False)  # 剩余 GB
    use_percent = Column(Float, nullable=False)  # 使用百分比
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    server = relationship("Server", back_populates="disk_usages")


class UserDiskUsage(Base):
    """用户/目录空间占用"""
    __tablename__ = "user_disk_usages"
    
    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    mount_point = Column(String(255), nullable=False)  # 所属挂载点
    directory = Column(String(500), nullable=False)  # 目录路径
    owner = Column(String(100))  # 目录所有者
    used_gb = Column(Float, nullable=False)  # 占用空间 GB
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    server = relationship("Server", back_populates="user_disk_usages")
