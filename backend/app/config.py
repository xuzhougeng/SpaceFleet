from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./space_manager.db"
    
    # Disk collection settings
    MIN_DISK_SIZE_GB: int = 250  # Only collect disks >= 250GB
    ALERT_THRESHOLD_PERCENT: int = 80  # Alert when usage >= 80%
    
    # Scheduler settings
    COLLECTION_HOUR: int = 2  # Run daily at 2:00 AM
    COLLECTION_MINUTE: int = 0

    ANALYSIS_CACHE_TTL_DAYS: int = 7
    
    class Config:
        env_file = ".env"


settings = Settings()
