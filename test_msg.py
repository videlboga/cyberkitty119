from max_bot.api_client import MaxAPI

api = MaxAPI()
chat_id = "233211983"
res = api.send_message(chat_id, "Test debug")
print("RESULT IS:")
print(res)
