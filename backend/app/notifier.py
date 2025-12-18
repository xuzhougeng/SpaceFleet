"""告警通知模块"""
import json
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any, Optional
import urllib.request
import urllib.parse
import urllib.error

from sqlalchemy.orm import Session

from app.models import AlertConfig, Server, ServerMetrics, DiskUsage


def send_bark_notification(
    url: str,
    title: str,
    body: str,
    sound: Optional[str] = None
) -> Tuple[bool, str]:
    """
    发送 Bark 推送通知
    
    Args:
        url: Bark URL (e.g. https://api.day.app/YOUR_KEY)
        title: 通知标题
        body: 通知内容
        sound: 提示音名称（可选）
    
    Returns:
        (success, message) 元组
    """
    try:
        # 构建请求 URL
        params = {
            "title": title,
            "body": body,
        }
        if sound:
            params["sound"] = sound
        
        # Bark 支持 GET 和 POST，这里使用 GET
        query = urllib.parse.urlencode(params)
        full_url = f"{url.rstrip('/')}?{query}"
        
        req = urllib.request.Request(full_url, method="GET")
        req.add_header("User-Agent", "SpaceFleet/1.0")
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("code") == 200:
                return True, "通知发送成功"
            return False, f"Bark 返回错误: {result.get('message', 'Unknown')}"
    except urllib.error.URLError as e:
        return False, f"网络错误: {e.reason}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP 错误: {e.code}"
    except Exception as e:
        return False, f"发送失败: {str(e)}"


def check_and_notify(db: Session):
    """
    检查所有告警规则，触发符合条件的通知
    在指标采集后调用
    """
    # 获取所有启用的告警配置
    alerts = db.query(AlertConfig).filter(AlertConfig.enabled == True).all()
    if not alerts:
        return
    
    now = datetime.utcnow()
    
    for alert in alerts:
        # 检查冷却时间
        if alert.last_triggered_at:
            cooldown = timedelta(minutes=alert.cooldown_minutes)
            if now - alert.last_triggered_at < cooldown:
                continue
        
        # 获取要检查的服务器
        if alert.server_id:
            servers = db.query(Server).filter(
                Server.id == alert.server_id,
                Server.enabled == True
            ).all()
        else:
            servers = db.query(Server).filter(Server.enabled == True).all()
        
        triggered_servers: List[Dict[str, Any]] = []
        
        for server in servers:
            exceeded, current_value = _check_metric(db, server, alert.metric_type, alert.threshold)
            if exceeded:
                triggered_servers.append({
                    "server_name": server.name,
                    "current_value": current_value,
                })
        
        if triggered_servers:
            _send_alert(db, alert, triggered_servers, now)


def _check_metric(
    db: Session,
    server: Server,
    metric_type: str,
    threshold: float
) -> Tuple[bool, float]:
    """
    检查指定服务器的指标是否超过阈值
    
    Returns:
        (exceeded, current_value) 元组
    """
    if metric_type == "cpu":
        metrics = db.query(ServerMetrics).filter(
            ServerMetrics.server_id == server.id
        ).order_by(ServerMetrics.collected_at.desc()).first()
        if metrics:
            return metrics.cpu_percent >= threshold, metrics.cpu_percent
    
    elif metric_type == "memory":
        metrics = db.query(ServerMetrics).filter(
            ServerMetrics.server_id == server.id
        ).order_by(ServerMetrics.collected_at.desc()).first()
        if metrics:
            return metrics.memory_percent >= threshold, metrics.memory_percent
    
    elif metric_type == "disk":
        # 检查所有磁盘，任一超标则告警
        from sqlalchemy import func
        subq = db.query(
            DiskUsage.mount_point,
            func.max(DiskUsage.collected_at).label("max_at")
        ).filter(
            DiskUsage.server_id == server.id
        ).group_by(DiskUsage.mount_point).subquery()
        
        latest_disks = db.query(DiskUsage).join(
            subq,
            (DiskUsage.mount_point == subq.c.mount_point) &
            (DiskUsage.collected_at == subq.c.max_at)
        ).filter(DiskUsage.server_id == server.id).all()
        
        for disk in latest_disks:
            if disk.use_percent >= threshold:
                return True, disk.use_percent
    
    elif metric_type in ("gpu_memory", "gpu_util"):
        metrics = db.query(ServerMetrics).filter(
            ServerMetrics.server_id == server.id
        ).order_by(ServerMetrics.collected_at.desc()).first()
        
        if metrics and metrics.gpu_info:
            try:
                gpus = json.loads(metrics.gpu_info)
                for gpu in gpus:
                    if metric_type == "gpu_memory":
                        if gpu.get("memory_percent", 0) >= threshold:
                            return True, gpu["memory_percent"]
                    else:  # gpu_util
                        if gpu.get("gpu_util_percent", 0) >= threshold:
                            return True, gpu["gpu_util_percent"]
            except json.JSONDecodeError:
                pass
    
    return False, 0.0


def _send_alert(
    db: Session,
    alert: AlertConfig,
    triggered_servers: List[Dict[str, Any]],
    now: datetime
):
    """发送告警通知并更新触发时间"""
    metric_names = {
        "cpu": "CPU 使用率",
        "memory": "内存使用率",
        "disk": "磁盘使用率",
        "gpu_memory": "GPU 显存",
        "gpu_util": "GPU 算力",
    }
    metric_name = metric_names.get(alert.metric_type, alert.metric_type)
    
    # 构建通知内容
    title = f"⚠️ {alert.name}"
    lines = [f"指标: {metric_name} >= {alert.threshold}%"]
    for srv in triggered_servers[:5]:  # 最多显示5个
        lines.append(f"• {srv['server_name']}: {srv['current_value']:.1f}%")
    if len(triggered_servers) > 5:
        lines.append(f"...等 {len(triggered_servers)} 台服务器")
    body = "\n".join(lines)
    
    success, msg = send_bark_notification(
        url=alert.bark_url,
        title=title,
        body=body,
        sound=alert.bark_sound
    )
    
    if success:
        alert.last_triggered_at = now
        db.commit()
        print(f"Alert sent: {alert.name} -> {len(triggered_servers)} servers")
    else:
        print(f"Alert failed: {alert.name} -> {msg}")

