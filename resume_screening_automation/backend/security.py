import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

# Read API key from environment variable
API_KEY = os.getenv("API_KEY")

# Header name
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    if API_KEY is None:
        raise HTTPException(status_code=500, detail="API key not configured")

    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )
