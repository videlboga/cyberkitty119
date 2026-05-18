import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        # First send an active note request
        r = await client.post(
            "http://127.0.0.1:8000/api/v1/agent/active_note",
            json={
                "telegram_id": 190,
                "note_id": 1
            }
        )
        print("Active note:", r.status_code, r.text)
        
        # Then send a chat message
        r2 = await client.post(
            "http://127.0.0.1:8000/api/v1/agent/chat",
            json={
                "telegram_id": 190,
                "text": "какая суть?"
            },
            timeout=120.0
        )
        print("Chat response:", r2.status_code)
        print(r2.text)

if __name__ == "__main__":
    asyncio.run(main())
