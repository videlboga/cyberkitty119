import sys
import logging
from max_bot.api_client import MaxAPI

logging.basicConfig(level=logging.DEBUG)

token = "f9LHodD0cOIazRdjSjn-sR8uuDHBo2QgSd-4B5YschVf38u0XKdAIAedZQoGMeMOKfUFOAvcnShzhjvU4kas"
url = "https://platform-api.max.ru"
api = MaxAPI(token, base_url=url)

with open("test.txt", "wb") as f:
    f.write(b"File content testing")

with open("test.txt", "rb") as f:
    try:
        res = api.send_document("233211983", f, "test.txt", caption="test")
        print("Success:", res)
    except Exception as e:
        print("Exception:", e)
