from fastapi import FastAPI

from transkribator_modules.bot.yukassa_webhook import setup_yukassa_webhook


def create_app() -> FastAPI:
    app = FastAPI(title="YooKassa Webhook")
    setup_yukassa_webhook(app)
    return app


app = create_app()
