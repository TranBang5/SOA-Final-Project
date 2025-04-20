import requests
import json

VIEW_SERVICE_URL = "http://localhost:5002/api/paste"

sample_pastes = [
    {
        "paste_id": 1,
        "short_url": "abc123",
        "content": "Hello world from paste #1!",
        "expires_at": "2025-05-01T12:00:00"
    },
    {
        "paste_id": 2,
        "short_url": "noexpire",
        "content": "This paste never expires.",
        "expires_at": None
    },
    {
        "paste_id": 3,
        "short_url": "expired1",
        "content": "You should see an 'expired' message for this one.",
        "expires_at": "2023-01-01T00:00:00"
    }
]

for paste in sample_pastes:
    try:
        response = requests.post(VIEW_SERVICE_URL, json=paste)
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} Sent paste '{paste['short_url']}' — Response: {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to send paste '{paste['short_url']}': {str(e)}")
