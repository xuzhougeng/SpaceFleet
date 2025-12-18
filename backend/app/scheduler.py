from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal
from app.collector import collect_all_servers, collect_all_servers_metrics


scheduler = BackgroundScheduler()


def scheduled_collection():
    """定时采集任务（磁盘数据）"""
    print("Starting scheduled disk collection...")
    db = SessionLocal()
    try:
        results = collect_all_servers(db)
        success_count = sum(1 for r in results if r['success'])
        print(f"Disk collection completed: {success_count}/{len(results)} servers successful")
        for r in results:
            if not r['success']:
                print(f"  Failed: {r['server_name']} - {r['error']}")
    finally:
        db.close()


def scheduled_metrics_collection():
    """定时采集任务（CPU和内存指标，每1分钟）"""
    print("Starting scheduled metrics collection...")
    db = SessionLocal()
    try:
        results = collect_all_servers_metrics(db)
        success_count = sum(1 for r in results if r['success'])
        print(f"Metrics collection completed: {success_count}/{len(results)} servers successful")
        for r in results:
            if not r['success']:
                print(f"  Failed: {r['server_name']} - {r['error']}")
    finally:
        db.close()


def start_scheduler():
    """启动定时任务调度器"""
    # 每天指定时间执行磁盘采集
    scheduler.add_job(
        scheduled_collection,
        trigger=CronTrigger(
            hour=settings.COLLECTION_HOUR,
            minute=settings.COLLECTION_MINUTE,
        ),
        id="daily_collection",
        replace_existing=True,
    )
    
    # 每1分钟执行CPU和内存指标采集
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler.add_job(
        scheduled_metrics_collection,
        trigger=IntervalTrigger(minutes=1),
        id="metrics_collection",
        replace_existing=True,
    )
    
    scheduler.start()
    print(f"Scheduler started. Daily disk collection at {settings.COLLECTION_HOUR:02d}:{settings.COLLECTION_MINUTE:02d}")
    print("Metrics collection (CPU/Memory) every 1 minute")


def stop_scheduler():
    """停止调度器"""
    scheduler.shutdown()
