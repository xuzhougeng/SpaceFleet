from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ============ Server Schemas ============

class ServerBase(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    auth_type: str = "key"  # password 或 key
    private_key_path: Optional[str] = None
    password: Optional[str] = None
    os_type: str = "ubuntu"
    description: Optional[str] = None
    scan_mounts: Optional[str] = None  # 要扫描的挂载点，逗号分隔，空表示全部
    enabled: bool = True
    sudoer: bool = False


class ServerCreate(ServerBase):
    pass


class ServerUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    auth_type: Optional[str] = None
    private_key_path: Optional[str] = None
    password: Optional[str] = None
    os_type: Optional[str] = None
    description: Optional[str] = None
    scan_mounts: Optional[str] = None
    enabled: Optional[bool] = None
    sudoer: Optional[bool] = None


class ServerResponse(ServerBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ============ DiskUsage Schemas ============

class DiskUsageBase(BaseModel):
    device: Optional[str] = None
    filesystem: Optional[str] = None
    mount_point: str
    total_gb: float
    used_gb: float
    free_gb: float
    use_percent: float


class DiskUsageResponse(DiskUsageBase):
    id: int
    server_id: int
    collected_at: datetime
    
    class Config:
        from_attributes = True


class DiskUsageWithServer(DiskUsageResponse):
    server: ServerResponse


# ============ UserDiskUsage Schemas ============

class UserDiskUsageBase(BaseModel):
    mount_point: str
    directory: str
    owner: Optional[str] = None
    used_gb: float


class UserDiskUsageResponse(UserDiskUsageBase):
    id: int
    server_id: int
    collected_at: datetime
    
    class Config:
        from_attributes = True


# ============ Dashboard Schemas ============

class DiskSummary(BaseModel):
    """单个磁盘概览"""
    server_name: str
    server_id: int
    mount_point: str
    total_gb: float
    used_gb: float
    free_gb: float
    use_percent: float
    is_alert: bool  # 是否超过告警阈值


class ServerDiskSummary(BaseModel):
    """服务器磁盘概览"""
    server: ServerResponse
    disks: List[DiskSummary]
    latest_collection: Optional[datetime] = None


class DiskTrend(BaseModel):
    """磁盘趋势数据点"""
    date: datetime
    use_percent: float
    used_gb: float


class UserUsageSummary(BaseModel):
    """用户占用汇总"""
    directory: str
    owner: Optional[str]
    used_gb: float
    percent_of_disk: float  # 占所在磁盘的百分比


class FileTypeStats(BaseModel):
    """文件类型统计"""
    extension: str
    size_gb: float
    file_count: int
    percent: float  # 占总量百分比


class LargeFileInfo(BaseModel):
    """大文件信息"""
    filepath: str
    filename: str
    extension: str
    size_gb: float
    owner: str
    modified: str


class AnalysisResponseBase(BaseModel):
    collected_at: Optional[datetime] = None
    is_stale: bool
    refreshing: bool
    error: Optional[str] = None


class FileTypeAnalysisResponse(AnalysisResponseBase):
    items: List[FileTypeStats]


class LargeFilesAnalysisResponse(AnalysisResponseBase):
    items: List[LargeFileInfo]


# ============ Server Metrics Schemas ============

class GpuInfo(BaseModel):
    """单个GPU信息"""
    index: int
    name: str
    memory_total_mb: float
    memory_used_mb: float
    memory_percent: float
    gpu_util_percent: float
    temperature: float


class ServerMetricsBase(BaseModel):
    cpu_percent: float
    memory_total_gb: float
    memory_used_gb: float
    memory_free_gb: float
    memory_percent: float
    gpu_info: Optional[List[GpuInfo]] = None


class ServerMetricsResponse(ServerMetricsBase):
    id: int
    server_id: int
    collected_at: datetime
    
    class Config:
        from_attributes = True


class ServerMetricsSummary(BaseModel):
    """服务器指标概览（最新数据）"""
    server_id: int
    server_name: str
    cpu_percent: float
    memory_total_gb: float
    memory_used_gb: float
    memory_free_gb: float
    memory_percent: float
    gpu_info: Optional[List[GpuInfo]] = None
    collected_at: datetime