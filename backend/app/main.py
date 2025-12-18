import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from sqlalchemy import text

# 过滤 paramiko 的 TripleDES 弃用警告
warnings.filterwarnings("ignore", message=".*TripleDES.*")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import engine, Base
from app.routers import servers, disks, alerts
from app.scheduler import start_scheduler, stop_scheduler


def _ensure_sqlite_schema():
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(servers)")).fetchall()]
        if "enabled" not in cols:
            conn.execute(text("ALTER TABLE servers ADD COLUMN enabled INTEGER DEFAULT 1"))
            conn.execute(text("UPDATE servers SET enabled=1 WHERE enabled IS NULL"))
        if "sudoer" not in cols:
            conn.execute(text("ALTER TABLE servers ADD COLUMN sudoer INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE servers SET sudoer=0 WHERE sudoer IS NULL"))
        # server_metrics.gpu_info 列兼容处理
        sm_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(server_metrics)")).fetchall()]
        if "gpu_info" not in sm_cols:
            conn.execute(text("ALTER TABLE server_metrics ADD COLUMN gpu_info TEXT"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Startup
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="Space Manager",
    description="多服务器磁盘空间管理工具",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(servers.router, prefix="/api")
app.include_router(disks.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")

# 静态文件目录
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

# 挂载静态资源目录
if (FRONTEND_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
if (FRONTEND_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/")
def root():
    """返回前端首页"""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Space Manager API", "version": "1.0.0"}


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
