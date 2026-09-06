from fastapi.testclient import TestClient
from src.api.routes import app
import traceback

client = TestClient(app)

print("\n3. Testing POST /api/qa")
try:
    response = client.post("/api/qa", json={"query": "test", "mode": "hybrid", "top_k": 5})
    print(response.status_code)
    if response.status_code == 500:
        print(response.json())
except Exception as e:
    traceback.print_exc()

print("\n4. Testing POST /api/upload")
try:
    with open("sample_data/system_overview.txt", "rb") as f:
        response = client.post("/api/upload", files={"file": ("system_overview.txt", f, "text/plain")})
    print(response.status_code)
    if response.status_code == 500:
        print(response.json())
except Exception as e:
    traceback.print_exc()
