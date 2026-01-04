#!/usr/bin/env python
import requests

auth = ("admin", "monit")

response = requests.post("http://localhost:8000/mother/chat", 
    auth=auth,
    json={"query": "What about CPU usage in the last 30 days? Show me the trends."}
)

print("Response status:", response.status_code)
print("\nAgent Response:")
print(response.json()["response"])
