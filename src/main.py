from fastapi import FastAPI

from .api.auth import router as auth_router

app = FastAPI(title="Ticket Service")
app.include_router(auth_router)
