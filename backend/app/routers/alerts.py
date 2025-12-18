from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AlertConfig, Server
from app.schemas import AlertConfigCreate, AlertConfigUpdate, AlertConfigResponse

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=List[AlertConfigResponse])
def get_alerts(db: Session = Depends(get_db)):
    """获取所有告警配置"""
    alerts = db.query(AlertConfig).all()
    result = []
    for alert in alerts:
        data = AlertConfigResponse.model_validate(alert)
        if alert.server_id:
            server = db.query(Server).filter(Server.id == alert.server_id).first()
            data.server_name = server.name if server else None
        result.append(data)
    return result


@router.get("/{alert_id}", response_model=AlertConfigResponse)
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """获取单个告警配置"""
    alert = db.query(AlertConfig).filter(AlertConfig.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert config not found")
    data = AlertConfigResponse.model_validate(alert)
    if alert.server_id:
        server = db.query(Server).filter(Server.id == alert.server_id).first()
        data.server_name = server.name if server else None
    return data


@router.post("/", response_model=AlertConfigResponse)
def create_alert(alert_data: AlertConfigCreate, db: Session = Depends(get_db)):
    """创建告警配置"""
    # 验证 metric_type
    valid_types = ["cpu", "memory", "disk", "gpu_memory", "gpu_util"]
    if alert_data.metric_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid metric_type. Must be one of: {valid_types}")
    
    # 验证 server_id
    if alert_data.server_id:
        server = db.query(Server).filter(Server.id == alert_data.server_id).first()
        if not server:
            raise HTTPException(status_code=400, detail="Server not found")
    
    alert = AlertConfig(**alert_data.model_dump())
    db.add(alert)
    db.commit()
    db.refresh(alert)
    
    data = AlertConfigResponse.model_validate(alert)
    if alert.server_id:
        server = db.query(Server).filter(Server.id == alert.server_id).first()
        data.server_name = server.name if server else None
    return data


@router.put("/{alert_id}", response_model=AlertConfigResponse)
def update_alert(alert_id: int, alert_data: AlertConfigUpdate, db: Session = Depends(get_db)):
    """更新告警配置"""
    alert = db.query(AlertConfig).filter(AlertConfig.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert config not found")
    
    update_data = alert_data.model_dump(exclude_unset=True)
    
    # 验证 metric_type
    if "metric_type" in update_data:
        valid_types = ["cpu", "memory", "disk", "gpu_memory", "gpu_util"]
        if update_data["metric_type"] not in valid_types:
            raise HTTPException(status_code=400, detail=f"Invalid metric_type. Must be one of: {valid_types}")
    
    # 验证 server_id
    if "server_id" in update_data and update_data["server_id"]:
        server = db.query(Server).filter(Server.id == update_data["server_id"]).first()
        if not server:
            raise HTTPException(status_code=400, detail="Server not found")
    
    for key, value in update_data.items():
        setattr(alert, key, value)
    
    db.commit()
    db.refresh(alert)
    
    data = AlertConfigResponse.model_validate(alert)
    if alert.server_id:
        server = db.query(Server).filter(Server.id == alert.server_id).first()
        data.server_name = server.name if server else None
    return data


@router.delete("/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """删除告警配置"""
    alert = db.query(AlertConfig).filter(AlertConfig.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert config not found")
    
    db.delete(alert)
    db.commit()
    return {"success": True}


@router.post("/{alert_id}/test")
def test_alert(alert_id: int, db: Session = Depends(get_db)):
    """测试告警通知"""
    alert = db.query(AlertConfig).filter(AlertConfig.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert config not found")
    
    from app.notifier import send_bark_notification
    
    success, message = send_bark_notification(
        url=alert.bark_url,
        title="SpaceFleet 告警测试",
        body=f"这是一条来自规则「{alert.name}」的测试通知",
        sound=alert.bark_sound
    )
    
    return {"success": success, "message": message}

