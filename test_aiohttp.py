import aiohttp
import asyncio

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get('https://openrouter.ai') as r:
            print(r.status)

asyncio.run(main())
