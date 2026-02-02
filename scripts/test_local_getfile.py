import asyncio
import os
import json
from transkribator_modules.utils.large_file_downloader import get_file_info


async def main():
    bot_token = os.environ.get("BOT_TOKEN")
    file_id = os.environ.get("FILE_ID")
    if not bot_token or not file_id:
        print("ERR: set BOT_TOKEN and FILE_ID env vars")
        return
    info = await get_file_info(bot_token, file_id)
    print(json.dumps(info or {}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

