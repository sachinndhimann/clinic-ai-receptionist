from fastapi import FastAPI

from app.webhooks.staff import router as staff_router
from app.webhooks.whatsapp import router as whatsapp_router

app = FastAPI(title="Clinic AI Receptionist")

app.include_router(whatsapp_router)
app.include_router(staff_router)


@app.get("/health")
def health():
    return {"status": "ok"}
