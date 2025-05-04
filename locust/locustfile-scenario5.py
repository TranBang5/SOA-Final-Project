from datetime import datetime, timedelta
import random
import string
import time
from locust import HttpUser, task, between
from locust import events
from locust.clients import HttpSession
import json

class PasteServiceUser(HttpUser):
    wait_time = between(2, 10)
    network_timeout = 30.0
    connection_timeout = 30.0
    created_pastes = []  # Store tuples of (short_url, expires_at, paste_id)

    @task(1)  # 10% write (POST)
    def create_paste(self):
        content = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(10, 50)))
        expires_in = random.choice([300, 1440, None])  # In seconds
        payload = {
            "content": content,
            "expires_in": expires_in
        }
        try:
            with self.client.post(
                "/pastes/",
                json=payload,
                headers={"Content-Type": "application/json"},
                name="Create Paste",
                catch_response=True
            ) as response:
                print(f"Create Paste response: status={response.status_code}, body={response.text[:200]}")
                if response.status_code == 201:
                    try:
                        data = response.json()
                        if "data" in data and "short_url" in data["data"] and "paste_id" in data["data"]:
                            short_url = data["data"]["short_url"]
                            paste_id = data["data"]["paste_id"]
                            expires_at = None
                            if expires_in:
                                expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                            print(f"Created paste: short_url={short_url}, paste_id={paste_id}, expires_at={expires_at}")
                            self.created_pastes.append((short_url, expires_at, paste_id))
                            response.success()
                            time.sleep(2)
                        else:
                            print(f"Invalid JSON structure: {data}")
                            response.failure("Missing data.short_url or data.paste_id")
                    except json.decoder.JSONDecodeError as e:
                        print(f"JSON parse error: {str(e)}, body={response.text[:200]}")
                        response.failure(f"JSON decode error: {str(e)}")
                else:
                    response.failure(f"Status code: {response.status_code}")
        except Exception as e:
            print(f"Create Paste exception: {str(e)}")
            self.environment.events.request.fire(
                request_type="POST",
                name="Create Paste",
                response_time=0,
                response_length=0,
                response=None,
                exception=str(e),
                success=False
            )

    @task(9)  # 90% read (GET), 9:1 ratio
    def view_paste(self):
        valid_pastes = [
            (short_url, expires_at, paste_id)
            for short_url, expires_at, paste_id in self.created_pastes
            if expires_at is None or expires_at > datetime.utcnow()
        ]
        if not valid_pastes:
            print("No valid pastes available to view")
            return
        short_url, _, paste_id = random.choice(valid_pastes)
        try:
            with self.view_client.get(
                f"/paste/{short_url}",
                headers={"Connection": "keep-alive", "Accept": "application/json"},
                name="View Paste",
                catch_response=True
            ) as response:
                print(f"View Paste response: status={response.status_code}, url=/paste/{short_url}, content-type={response.headers.get('Content-Type')}, body={response.text[:200]}")
                if response.status_code == 200:
                    view_count = 0
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'application/json' in content_type:
                        try:
                            data = response.json()
                            view_count = data.get("view_count", 0)
                        except json.decoder.JSONDecodeError as e:
                            print(f"JSON parse error in View Paste: {str(e)}, body={response.text[:200]}")
                            response.failure(f"JSON decode error: {str(e)}")
                            # Proceed with view_count=0 to trigger analytics
                    else:
                        print(f"Non-JSON response: Content-Type={content_type}, assuming view_count=0")
                        # Optionally fetch view_count via /api/views/<paste_id>
                        try:
                            with self.view_client.get(
                                f"/api/views/{paste_id}",
                                headers={"Connection": "keep-alive"},
                                name="Get View Count",
                                catch_response=True
                            ) as vc_response:
                                if vc_response.status_code == 200:
                                    vc_data = vc_response.json()
                                    view_count = vc_data.get("view_count", 0)
                                    print(f"Fetched view_count={view_count} from /api/views/{paste_id}")
                                else:
                                    print(f"Failed to fetch view_count: status={vc_response.status_code}")
                        except Exception as vc_e:
                            print(f"Get View Count exception: {str(vc_e)}")
                    # Send analytics write after successful read
                    self.send_analytics(short_url, paste_id, view_count)
                    response.success()
                else:
                    response.failure(f"Status code: {response.status_code}")
        except Exception as e:
            print(f"View Paste exception: {str(e)}")
            self.environment.events.request.fire(
                request_type="GET",
                name="View Paste",
                response_time=0,
                response_length=0,
                response=None,
                exception=str(e),
                success=False
            )

    def send_analytics(self, short_url, paste_id, view_count):
        """Send analytics write after each successful read"""
        payload = {
            "paste_id": paste_id,
            "short_url": short_url,
            "view_count": view_count
        }
        try:
            with self.analytics_client.post(
                "/api/track-view",
                json=payload,
                headers={"Content-Type": "application/json"},
                name="Analytics Write",
                catch_response=True
            ) as response:
                print(f"Analytics Write response: status={response.status_code}, body={response.text[:200]}")
                if response.status_code in [200, 201]:
                    response.success()
                else:
                    response.failure(f"Status code: {response.status_code}")
        except Exception as e:
            print(f"Analytics Write exception: {str(e)}")
            self.environment.events.request.fire(
                request_type="POST",
                name="Analytics Write",
                response_time=0,
                response_length=0,
                response=None,
                exception=str(e),
                success=False
            )

    def on_start(self):
        self.paste_service_url = "http://paste-haproxy:80"
        self.view_service_url = "http://view-haproxy:80"
        self.analytic_service_url = "http://analytics-service:5003"
        self.client.base_url = self.paste_service_url
        self.view_client = HttpSession(
            base_url=self.view_service_url,
            request_event=self.environment.events.request,
            user=self
        )
        self.analytics_client = HttpSession(
            base_url=self.analytic_service_url,
            request_event=self.environment.events.request,
            user=self
        )
        self.create_paste()

    def on_stop(self):
        self.created_pastes.clear()

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats
    total_requests = stats.total.num_requests
    total_failures = stats.total.num_failures
    error_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0
    
    print("\nTest Summary:")
    print(f"Total Requests: {total_requests}")
    print(f"Total Failures: {total_failures}")
    print(f"Error Rate: {error_rate:.2f}%")
    
    print("\nAvailable stat entries:", list(stats.entries.keys()))
    for entry_name in ["Create Paste", "View Paste", "Analytics Write", "Get View Count"]:
        entry = stats.get(entry_name, "GET" if entry_name in ["View Paste", "Get View Count"] else "POST")
        if entry.num_requests > 0:
            print(f"\nMetrics for {entry_name}:")
            print(f"  Requests: {entry.num_requests}")
            print(f"  Failures: {entry.num_failures}")
            print(f"  Error Rate: {(entry.num_failures / entry.num_requests * 100):.2f}%")
            print(f"  p99 Response Time: {entry.get_response_time_percentile(0.99):.2f} ms")
            print(f"  Avg Response Time: {entry.avg_response_time:.2f} ms")
        else:
            print(f"\nNo metrics for {entry_name}: No requests recorded")
