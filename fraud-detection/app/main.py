from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging

from core.config import settings
from api.endpoints import transactions, alerts, users, security
from ml.models import load_fraud_model
from utils.cache import get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global variables
fraud_model = None
scaler = None
redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    global fraud_model, scaler, redis_client
    
    logger.info("Starting Fraud Detection API...")
    
    # Initialize Redis client
    redis_client = get_redis_client()
    app.state.redis = redis_client
    
    # Load ML model
    fraud_model, scaler = load_fraud_model()
    app.state.fraud_model = fraud_model
    app.state.scaler = scaler
    
    logger.info("Fraud Detection API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Fraud Detection API...")
    if redis_client:
        try:
            redis_client.close()
        except:
            pass

app = FastAPI(
    title=settings.APP_NAME,
    description="Real-time fraud detection system with ML-based risk scoring",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(
    transactions.router,
    prefix="/transactions", 
    tags=["transactions"]
)
app.include_router(
    alerts.router,
    prefix="/alerts",
    tags=["alerts"]
)
app.include_router(
    users.router,
    prefix="/users",
    tags=["users"]
)
app.include_router(
    security.router,
    prefix="/security",
    tags=["security"]
)

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Fraud Detection API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "transactions": "/transactions/analyze",
            "alerts": "/alerts",
            "users": "/users"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": "2025-01-01T00:00:00Z",
        "model_loaded": app.state.fraud_model is not None,
        "redis_connected": app.state.redis is not None,
        "version": "1.0.0"
    }

@app.get("/stats")
async def get_system_stats():
    """Get basic system statistics"""
    # In a real app, these would come from database
    return {
        "total_transactions_analyzed": 0,
        "high_risk_transactions": 0,
        "active_alerts": 0,
        "system_uptime": "Running",
        "model_version": "1.0"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )