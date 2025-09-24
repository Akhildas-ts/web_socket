from pydantic import BaseSettings
from typing import List

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Fraud Detection API"
    DEBUG: bool = True
    VERSION: str = "1.0.0"
    
    # Security
    SECRET_KEY: str = "your-fraud-detection-secret-key-change-in-production"
    API_KEYS: List[str] = [
        "fraud-api-key-123",
        "admin-key-456", 
        "test-key-789"
    ]
    
    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_DECODE_RESPONSES: bool = True
    
    # ML Model Settings
    MODEL_PATH: str = "models/fraud_model.pkl"
    SCALER_PATH: str = "models/fraud_scaler.pkl"
    
    # Risk Thresholds
    HIGH_RISK_THRESHOLD: float = 70.0
    CRITICAL_RISK_THRESHOLD: float = 85.0
    
    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE: int = 100
    MAX_TRANSACTIONS_PER_USER_PER_DAY: int = 50
    
    # Alert Settings
    ENABLE_ALERTS: bool = True
    ALERT_WEBHOOK_URL: str = ""
    
    class Config:
        env_file = ".env"

settings = Settings()