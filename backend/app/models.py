from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, UniqueConstraint
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
    enabled = Column(Boolean, default=True)  # 是否启用采集
    sudoer = Column(Boolean, default=False)  # 是否具备免密 sudo 权限
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    disk_usages = relationship("DiskUsage", back_populates="server", cascade="all, delete-orphan")
    user_disk_usages = relationship("UserDiskUsage", back_populates="server", cascade="all, delete-orphan")
    server_metrics = relationship("ServerMetrics", back_populates="server", cascade="all, delete-orphan")


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


class ServerMetrics(Base):
    """服务器性能指标（CPU、内存、GPU）"""
    __tablename__ = "server_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False, index=True)
    cpu_percent = Column(Float, nullable=False)  # CPU 使用率百分比
    memory_total_gb = Column(Float, nullable=False)  # 总内存 GB
    memory_used_gb = Column(Float, nullable=False)  # 已使用内存 GB
    memory_free_gb = Column(Float, nullable=False)  # 空闲内存 GB
    memory_percent = Column(Float, nullable=False)  # 内存使用率百分比
    # GPU 信息（JSON格式存储多块GPU）
    gpu_info = Column(Text, nullable=True)  # JSON: [{name, index, memory_total_mb, memory_used_mb, memory_percent, gpu_util_percent, temperature}]
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    server = relationship("Server", back_populates="server_metrics")


class AnalysisCache(Base):
    """耗时统计缓存（文件类型/大文件 TopN）"""

    __tablename__ = "analysis_cache"
    __table_args__ = (
        UniqueConstraint("server_id", "mount_point", "kind", name="uq_analysis_cache"),
    )

    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False, index=True)
    mount_point = Column(String(255), nullable=False)
    kind = Column(String(50), nullable=False)  # filetypes / largefiles
    data_json = Column(Text, nullable=True)
    collected_at = Column(DateTime, nullable=True, index=True)
    refreshing = Column(Boolean, default=False)
    error = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertConfig(Base):
    """告警配置"""
    __tablename__ = "alert_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # 规则名称
    metric_type = Column(String(20), nullable=False)  # cpu / memory / disk / gpu_memory / gpu_util
    threshold = Column(Float, nullable=False)  # 阈值百分比
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)  # 指定服务器，null 表示全部
    enabled = Column(Boolean, default=True)  # 是否启用
    bark_url = Column(String(500), nullable=False)  # Bark 推送 URL
    bark_sound = Column(String(50), nullable=True)  # Bark 提示音
    cooldown_minutes = Column(Integer, default=30)  # 告警冷却时间（分钟）
    last_triggered_at = Column(DateTime, nullable=True)  # 上次触发时间
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    server = relationship("Server")