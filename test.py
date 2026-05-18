import urllib.request
try:
    urllib.request.urlopen("https://openrouter.ai")
except Exception as e:
    print(e.read())
