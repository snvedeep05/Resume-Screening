from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from api.jobs import router as jobs_router
from api.screening import router as screening_router
import os

app = FastAPI(title="Resume Screening Backend")

# -------------------------------
# Middleware: Password Protection
# -------------------------------
@app.middleware("http")
async def password_protect(request: Request, call_next):
    # The frontend must send this header in requests
    password = request.headers.get("x-api-key")

    # Compare with environment variable
    if password != os.getenv("BACKEND_PASSWORD"):
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
        )

    # Continue to the route if password is correct
    response = await call_next(request)
    return response

# -------------------------------
# Include existing routers
# -------------------------------
app.include_router(jobs_router, prefix="/jobs")
app.include_router(screening_router)
