from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

# Импортируем роутеры нового Ядра
from core_api.api.v1 import system
from core_api.api.v1 import agent
from core_api.api.v1 import memory
from core_api.api.v1 import ingest
from core_api.api.v1 import transcribe
from core_api.api.v1 import internal_bot
from core_api.api.v1 import payments

app = FastAPI(
    title="Second Brain Core API",
    version="2.0.0",
    description="Headless API для управления персональной памятью и когнитивным агентом. "
                "Точка входа для Web UI, Telegram-ботов и внешних клиентов."
)

# CORS для вызовов с фронтенда (MiniApp / Web UI)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В проде настроим на список доменов
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Монтируем модули API
app.include_router(system.router, prefix="/api/v1/system")
app.include_router(agent.router, prefix="/api/v1/agent")
app.include_router(memory.router, prefix="/api/v1/memory")
app.include_router(ingest.router, prefix="/api/v1/ingest")
app.include_router(transcribe.router, prefix="/api/v1/ingest")
app.include_router(internal_bot.router, prefix="/api/v1/internal_bot")
app.include_router(payments.router, prefix="/api/v1")

@app.get("/")
async def root_overview():
    """Карта API для разработчиков и клиентов"""
    return {
        "service": "Second Brain Core API",
        "docs": "/docs",
        "health": "/api/v1/system/health"
    }

if __name__ == "__main__":
    # Запуск нового Ядра
    # Вы можете запустить его параллельно старому (на другом порту, например 8001), 
    # чтобы тестировать, не ломая бой.
    uvicorn.run(
        "core_api.main:app",
        host="0.0.0.0",
        port=8002,  
        reload=True
    )
