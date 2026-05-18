from dotenv import load_dotenv
load_dotenv()
from max_bot.api_client import MaxAPI

api = MaxAPI()
try:
    res = api.send_message(chat_id="id632523990270_bot", text="*Бот* [ссылка](https://google.com)", reply_markup=None)
    print("res", res)
except Exception as e:
    print(e)
