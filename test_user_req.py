import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://127.0.0.1:8000/api/v1/agent/chat",
            json={
                "telegram_id": 190,
                "text": "Привет"
            },
            timeout=20.0
        )
        print(resp.status_code)
        print(resp.text)

asyncio.run(main())
