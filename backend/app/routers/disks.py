from datetime import datetime, timedelta
from typing import List, Optional
import json

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from sqlalchemy.exc import IntegrityError

from app.database import get_db, SessionLocal
from app.models import Server, DiskUsage, UserDiskUsage, AnalysisCache, ServerMetrics
from app.schemas import (
    DiskUsageResponse, 
    UserDiskUsageResponse,
    DiskSummary,
    ServerDiskSummary,
    DiskTrend,
    UserUsageSummary,
    FileTypeStats,
    LargeFileInfo,
    FileTypeAnalysisResponse,
    LargeFilesAnalysisResponse,
    ServerMetricsResponse,
    ServerMetricsSummary,
)
from app.config import settings
from app.collector import collect_server_data, collect_all_servers, get_file_type_stats, get_top_large_files
from app.ssh_client import SSHClient

router = APIRouter(prefix="/disks", tags=["disks"])


@router.get("/summary", response_model=List[DiskSummary])
def get_disk_summary(db: Session = Depends(get_db)):
    """
    获取所有服务器磁盘概览（最新数据）
    """
    # 获取每个服务器每个挂载点的最新记录
    subquery = (
        db.query(
            DiskUsage.server_id,
            DiskUsage.mount_point,
            func.max(DiskUsage.collected_at).label('latest')
        )
        .group_by(DiskUsage.server_id, DiskUsage.mount_point)
        .subquery()
    )
    
    latest_disks = (
        db.query(DiskUsage, Server.name)
        .join(Server)
        .filter(Server.enabled == True)
        .join(
            subquery,
            (DiskUsage.server_id == subquery.c.server_id) &
            (DiskUsage.mount_point == subquery.c.mount_point) &
            (DiskUsage.collected_at == subquery.c.latest)
        )
        .all()
    )
    
    result = []
    for disk, server_name in latest_disks:
        result.append(DiskSummary(
            server_name=server_name,
            server_id=disk.server_id,
            mount_point=disk.mount_point,
            total_gb=disk.total_gb,
            used_gb=disk.used_gb,
            free_gb=disk.free_gb,
            use_percent=disk.use_percent,
            is_alert=disk.use_percent >= settings.ALERT_THRESHOLD_PERCENT,
        ))
    
    # 按使用率降序排列，告警优先
    result.sort(key=lambda x: (-x.is_alert, -x.use_percent))
    return result


@router.get("/alerts", response_model=List[DiskSummary])
def get_disk_alerts(db: Session = Depends(get_db)):
    """获取超过告警阈值的磁盘"""
    summary = get_disk_summary(db)
    return [d for d in summary if d.is_alert]


@router.get("/server/{server_id}", response_model=List[DiskUsageResponse])
def get_server_disks(
    server_id: int,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db)
):
    """获取指定服务器的磁盘历史数据"""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    disks = (
        db.query(DiskUsage)
        .filter(DiskUsage.server_id == server_id)
        .order_by(desc(DiskUsage.collected_at))
        .limit(limit)
        .all()
    )
    return disks


@router.get("/trend/{server_id}/{mount_point:path}", response_model=List[DiskTrend])
def get_disk_trend(
    server_id: int,
    mount_point: str,
    days: int = Query(default=30, le=365),
    db: Session = Depends(get_db)
):
    """获取指定磁盘的趋势数据"""
    since = datetime.utcnow() - timedelta(days=days)
    
    # mount_point 需要加上前导斜杠
    if not mount_point.startswith('/'):
        mount_point = '/' + mount_point
    
    records = (
        db.query(DiskUsage)
        .filter(
            DiskUsage.server_id == server_id,
            DiskUsage.mount_point == mount_point,
            DiskUsage.collected_at >= since
        )
        .order_by(DiskUsage.collected_at)
        .all()
    )
    
    return [
        DiskTrend(
            date=r.collected_at,
            use_percent=r.use_percent,
            used_gb=r.used_gb,
        )
        for r in records
    ]


@router.get("/users/{server_id}/{mount_point:path}", response_model=List[UserUsageSummary])
def get_user_usage(
    server_id: int,
    mount_point: str,
    db: Session = Depends(get_db)
):
    """获取指定挂载点下各目录/用户的空间占用（最新数据）"""
    if not mount_point.startswith('/'):
        mount_point = '/' + mount_point
    
    # 获取最新的采集时间
    latest = (
        db.query(func.max(UserDiskUsage.collected_at))
        .filter(
            UserDiskUsage.server_id == server_id,
            UserDiskUsage.mount_point == mount_point
        )
        .scalar()
    )
    
    if not latest:
        return []
    
    # 获取该时间点的数据
    records = (
        db.query(UserDiskUsage)
        .filter(
            UserDiskUsage.server_id == server_id,
            UserDiskUsage.mount_point == mount_point,
            UserDiskUsage.collected_at == latest
        )
        .order_by(desc(UserDiskUsage.used_gb))
        .all()
    )
    
    # 获取磁盘总大小以计算百分比
    disk = (
        db.query(DiskUsage)
        .filter(
            DiskUsage.server_id == server_id,
            DiskUsage.mount_point == mount_point
        )
        .order_by(desc(DiskUsage.collected_at))
        .first()
    )
    
    total_gb = disk.total_gb if disk else 1
    
    return [
        UserUsageSummary(
            directory=r.directory,
            owner=r.owner,
            used_gb=r.used_gb,
            percent_of_disk=round(r.used_gb / total_gb * 100, 2),
        )
        for r in records
    ]


@router.post("/collect")
def trigger_collection(
    server_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    手动触发数据采集
    - 不指定 server_id: 采集所有服务器
    - 指定 server_id: 只采集该服务器
    """
    if server_id:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        if not server.enabled:
            raise HTTPException(status_code=400, detail="Server is disabled")
        result = collect_server_data(db, server)
        return {"results": [result]}
    else:
        results = collect_all_servers(db)
        return {"results": results}



def _get_or_create_cache(db: Session, server_id: int, mount_point: str, kind: str) -> AnalysisCache:
    cache = (
        db.query(AnalysisCache)
        .filter(
            AnalysisCache.server_id == server_id,
            AnalysisCache.mount_point == mount_point,
            AnalysisCache.kind == kind,
        )
        .first()
    )
    if cache:
        return cache
    cache = AnalysisCache(server_id=server_id, mount_point=mount_point, kind=kind, refreshing=False)
    db.add(cache)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        cache = (
            db.query(AnalysisCache)
            .filter(
                AnalysisCache.server_id == server_id,
                AnalysisCache.mount_point == mount_point,
                AnalysisCache.kind == kind,
            )
            .first()
        )
        if cache:
            return cache
        raise
    db.refresh(cache)
    return cache


def _refresh_analysis_cache(server_id: int, mount_point: str, kind: str) -> None:
    db = SessionLocal()
    try:
        cache = _get_or_create_cache(db, server_id, mount_point, kind)
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            cache.refreshing = False
            cache.error = "Server not found"
            db.commit()
            return
        if not server.enabled:
            cache.refreshing = False
            cache.error = "Server is disabled"
            db.commit()
            return

        ssh = SSHClient(
            host=server.host,
            port=server.port,
            username=server.username,
            password=server.password,
            private_key_path=server.private_key_path,
        )

        with ssh:
            if kind == "filetypes":
                data = get_file_type_stats(ssh, mount_point, use_sudo=bool(getattr(server, 'sudoer', False)))
            elif kind == "largefiles":
                data = get_top_large_files(ssh, mount_point, 50, use_sudo=bool(getattr(server, 'sudoer', False)))
            else:
                data = []

        cache.data_json = json.dumps(data, ensure_ascii=False)
        cache.collected_at = datetime.utcnow()
        cache.refreshing = False
        cache.error = None
        db.commit()
    except Exception as e:
        try:
            cache = _get_or_create_cache(db, server_id, mount_point, kind)
            cache.refreshing = False
            cache.error = str(e)
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.get("/filetypes/{server_id}/{mount_point:path}", response_model=FileTypeAnalysisResponse)
def get_file_types(
    server_id: int,
    mount_point: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    if not mount_point.startswith('/'):
        mount_point = '/' + mount_point

    cache = _get_or_create_cache(db, server_id, mount_point, "filetypes")
    ttl = timedelta(days=settings.ANALYSIS_CACHE_TTL_DAYS)
    is_stale = (cache.collected_at is None) or (datetime.utcnow() - cache.collected_at > ttl)

    if force:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        try:
            ssh = SSHClient(
                host=server.host,
                port=server.port,
                username=server.username,
                password=server.password,
                private_key_path=server.private_key_path,
            )
            with ssh:
                data = get_file_type_stats(ssh, mount_point, use_sudo=bool(getattr(server, 'sudoer', False)))
            cache.data_json = json.dumps(data, ensure_ascii=False)
            cache.collected_at = datetime.utcnow()
            cache.refreshing = False
            cache.error = None
            db.commit()
            return {
                "items": [FileTypeStats(**s) for s in data],
                "collected_at": cache.collected_at,
                "is_stale": False,
                "refreshing": False,
                "error": None,
            }
        except Exception as e:
            cache.refreshing = False
            cache.error = str(e)
            db.commit()
            raise HTTPException(status_code=500, detail=str(e))

    if is_stale and not cache.refreshing:
        cache.refreshing = True
        cache.error = None
        db.commit()
        background_tasks.add_task(_refresh_analysis_cache, server_id, mount_point, "filetypes")

    items = []
    if cache.data_json:
        try:
            raw = json.loads(cache.data_json)
            items = [FileTypeStats(**s) for s in raw]
        except Exception:
            items = []

    return {
        "items": items,
        "collected_at": cache.collected_at,
        "is_stale": is_stale,
        "refreshing": bool(cache.refreshing),
        "error": cache.error,
    }


@router.get("/largefiles/{server_id}/{mount_point:path}", response_model=LargeFilesAnalysisResponse)
def get_large_files(
    server_id: int,
    mount_point: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    if not mount_point.startswith('/'):
        mount_point = '/' + mount_point

    cache = _get_or_create_cache(db, server_id, mount_point, "largefiles")
    ttl = timedelta(days=settings.ANALYSIS_CACHE_TTL_DAYS)
    is_stale = (cache.collected_at is None) or (datetime.utcnow() - cache.collected_at > ttl)

    if force:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        try:
            ssh = SSHClient(
                host=server.host,
                port=server.port,
                username=server.username,
                password=server.password,
                private_key_path=server.private_key_path,
            )
            with ssh:
                data = get_top_large_files(ssh, mount_point, 50, use_sudo=bool(getattr(server, 'sudoer', False)))
            cache.data_json = json.dumps(data, ensure_ascii=False)
            cache.collected_at = datetime.utcnow()
            cache.refreshing = False
            cache.error = None
            db.commit()
            return {
                "items": [LargeFileInfo(**f) for f in data],
                "collected_at": cache.collected_at,
                "is_stale": False,
                "refreshing": False,
                "error": None,
            }
        except Exception as e:
            cache.refreshing = False
            cache.error = str(e)
            db.commit()
            raise HTTPException(status_code=500, detail=str(e))

    if is_stale and not cache.refreshing:
        cache.refreshing = True
        cache.error = None
        db.commit()
        background_tasks.add_task(_refresh_analysis_cache, server_id, mount_point, "largefiles")

    items = []
    if cache.data_json:
        try:
            raw = json.loads(cache.data_json)
            items = [LargeFileInfo(**f) for f in raw]
        except Exception:
            items = []

    return {
        "items": items,
        "collected_at": cache.collected_at,
        "is_stale": is_stale,
        "refreshing": bool(cache.refreshing),
        "error": cache.error,
    }


@router.get("/metrics/summary", response_model=List[ServerMetricsSummary])
def get_metrics_summary(db: Session = Depends(get_db)):
    """
    获取所有服务器的CPU、内存和GPU指标概览（最新数据）
    """
    # 获取每个服务器的最新指标记录
    subquery = (
        db.query(
            ServerMetrics.server_id,
            func.max(ServerMetrics.collected_at).label('latest')
        )
        .group_by(ServerMetrics.server_id)
        .subquery()
    )
    
    latest_metrics = (
        db.query(ServerMetrics, Server.name)
        .join(Server)
        .filter(Server.enabled == True)
        .join(
            subquery,
            (ServerMetrics.server_id == subquery.c.server_id) &
            (ServerMetrics.collected_at == subquery.c.latest)
        )
        .all()
    )
    
    result = []
    for metric, server_name in latest_metrics:
        # 解析GPU信息
        gpu_info = None
        if metric.gpu_info:
            try:
                gpu_info = json.loads(metric.gpu_info)
            except Exception:
                gpu_info = None
        
        result.append(ServerMetricsSummary(
            server_id=metric.server_id,
            server_name=server_name,
            cpu_percent=metric.cpu_percent,
            memory_total_gb=metric.memory_total_gb,
            memory_used_gb=metric.memory_used_gb,
            memory_free_gb=metric.memory_free_gb,
            memory_percent=metric.memory_percent,
            gpu_info=gpu_info,
            collected_at=metric.collected_at,
        ))
    
    # 按服务器ID排序
    result.sort(key=lambda x: x.server_id)
    return result


@router.get("/metrics/server/{server_id}", response_model=List[ServerMetricsResponse])
def get_server_metrics(
    server_id: int,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db)
):
    """获取指定服务器的指标历史数据"""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    metrics = (
        db.query(ServerMetrics)
        .filter(ServerMetrics.server_id == server_id)
        .order_by(desc(ServerMetrics.collected_at))
        .limit(limit)
        .all()
    )
    return metrics
