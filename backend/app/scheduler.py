from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal
from app.collector import collect_all_servers


scheduler = BackgroundScheduler()


def scheduled_collection():
    """定时采集任务"""
    print("Starting scheduled disk collection...")
    db = SessionLocal()
    try:
        results = collect_all_servers(db)
        success_count = sum(1 for r in results if r['success'])
        print(f"Collection completed: {success_count}/{len(results)} servers successful")
        for r in results:
            if not r['success']:
                print(f"  Failed: {r['server_name']} - {r['error']}")
    finally:
        db.close()


def start_scheduler():
    """启动定时任务调度器"""
    # 每天指定时间执行采集
    scheduler.add_job(
        scheduled_collection,
        trigger=CronTrigger(
            hour=settings.COLLECTION_HOUR,
            minute=settings.COLLECTION_MINUTE,
        ),
        id="daily_collection",
        replace_existing=True,
    )
    
    scheduler.start()
    print(f"Scheduler started. Daily collection at {settings.COLLECTION_HOUR:02d}:{settings.COLLECTION_MINUTE:02d}")


def stop_scheduler():
    """停止调度器"""
    scheduler.shutdown()
