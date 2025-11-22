from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    REDIS_URL: str = Field(..., env="REDIS_URL")
    USER_JWT_SECRET: str = Field(..., env="USER_JWT_SECRET")
    ADMIN_JWT_SECRET: str = Field(..., env="ADMIN_JWT_SECRET")
    USER_SESSION_EXPIRE_SECONDS: int = Field(3600, env="USER_SESSION_EXPIRE_SECONDS")
    ADMIN_SESSION_EXPIRE_SECONDS: int = Field(600, env="ADMIN_SESSION_EXPIRE_SECONDS")
    DISCOUNT_TTL_SECONDS: int = Field(300, env="DISCOUNT_TTL_SECONDS")
    NTH_ORDER: int = Field(5, env="NTH_ORDER")
    
    # should ideally be read from encrypted AWS Parameter store during runtime
    ADMIN_API_KEY: str = Field("admin-secret-key", env="ADMIN_API_KEY")
    RATE_LIMIT_REQUESTS: int = Field(100, env="RATE_LIMIT_REQUESTS")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(60, env="RATE_LIMIT_WINDOW_SECONDS")
    LOG_FILE: str = Field("logs/app.log", env="LOG_FILE")
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
