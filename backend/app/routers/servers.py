from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Server
from app.schemas import ServerCreate, ServerUpdate, ServerResponse
from app.ssh_client import SSHClient

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("/", response_model=List[ServerResponse])
def list_servers(db: Session = Depends(get_db)):
    """获取所有服务器列表"""
    return db.query(Server).all()


@router.get("/{server_id}", response_model=ServerResponse)
def get_server(server_id: int, db: Session = Depends(get_db)):
    """获取单个服务器信息"""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@router.post("/", response_model=ServerResponse)
def create_server(server: ServerCreate, db: Session = Depends(get_db)):
    """创建新服务器"""
    # 检查名称是否重复
    existing = db.query(Server).filter(Server.name == server.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Server name already exists")
    
    db_server = Server(**server.model_dump())
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    return db_server


@router.put("/{server_id}", response_model=ServerResponse)
def update_server(server_id: int, server: ServerUpdate, db: Session = Depends(get_db)):
    """更新服务器信息"""
    db_server = db.query(Server).filter(Server.id == server_id).first()
    if not db_server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    update_data = server.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_server, key, value)
    
    db.commit()
    db.refresh(db_server)
    return db_server


@router.delete("/{server_id}")
def delete_server(server_id: int, db: Session = Depends(get_db)):
    """删除服务器"""
    db_server = db.query(Server).filter(Server.id == server_id).first()
    if not db_server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    db.delete(db_server)
    db.commit()
    return {"message": "Server deleted"}


@router.post("/{server_id}/test")
def test_server_connection(server_id: int, db: Session = Depends(get_db)):
    """测试服务器 SSH 连接"""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    ssh = SSHClient(
        host=server.host,
        port=server.port,
        username=server.username,
        password=server.password,
        private_key_path=server.private_key_path,
    )
    
    success, message = ssh.test_connection()
    return {"success": success, "message": message}


@router.post("/{server_id}/test-sudo")
def test_server_sudo(server_id: int, db: Session = Depends(get_db)):
    """测试服务器 sudo 是否可用（需要配置 NOPASSWD），使用 sudo -n 非交互方式"""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    ssh = SSHClient(
        host=server.host,
        port=server.port,
        username=server.username,
        password=server.password,
        private_key_path=server.private_key_path,
    )

    try:
        with ssh:
            # `sudo -n true` 会在需要密码时立刻失败（退出码通常为 1）
            stdout, stderr, code = ssh.execute("sudo -n true")
            if code == 0:
                who_stdout, who_stderr, who_code = ssh.execute("sudo -n whoami")
            else:
                who_stdout, who_stderr, who_code = "", "", code

        return {
            "success": code == 0,
            "exit_code": code,
            "stdout": stdout,
            "stderr": stderr,
            "sudo_whoami": (who_stdout or "").strip() if code == 0 else None,
            "message": "sudo available" if code == 0 else "sudo not available (NOPASSWD not configured or sudo missing)",
        }
    except Exception as e:
        return {
            "success": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "sudo_whoami": None,
            "message": str(e),
        }
