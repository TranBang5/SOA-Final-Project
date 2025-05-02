import random
import string
import time
from locust import HttpUser, task, between
from locust import events
from locust.clients import HttpSession

class PasteServiceUser(HttpUser):
    wait_time = between(2, 10)
    network_timeout = 30.0
    connection_timeout = 30.0
    created_pastes = []

    @task(1)
    def create_paste(self):
        content = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(10, 50)))
        expires_in = random.choice([60, 1440, None])
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
                if response.status_code == 201:
                    data = response.json()
                    if "url" in data:
                        short_url = data["url"].split("/")[-1]  # Extract the short_url (e.g., abc123)
                        print(f"Created paste with short_url: {short_url}")
                        self.created_pastes.append(short_url)
                        response.success()
                        time.sleep(2)
        except Exception as e:
            self.environment.events.request.fire(
                request_type="POST",
                name="Create Paste",
                response_time=0,
                response_length=0,
                response=None,
                exception=str(e),
                success=False
            )

    @task(10)
    def view_paste(self):
        if not self.created_pastes:
            return
        short_url = random.choice(self.created_pastes)
        try:
            with self.view_client.get(
                f"/paste/{short_url}",
                name="View Paste",
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Status code: {response.status_code}")
        except Exception as e:
            self.environment.events.request.fire(
                request_type="GET",
                name="View Paste",
                response_time=0,
                response_length=0,
                response=None,
                exception=str(e),
                success=False
            )

    def on_start(self):
        self.paste_service_url = "http://paste-service:5000"
        self.view_service_url = "http://view-haproxy:80"
        self.client.base_url = self.paste_service_url
        self.view_client = HttpSession(
            base_url=self.view_service_url,
            request_event=self.environment.events.request,
            user=self,
            headers={"Connection": "keep-alive"}
        )
        self.create_paste()

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
    
    for entry_name in ["Create Paste", "View Paste"]:
        entry = stats.get(entry_name, "GET" if "View Paste" in entry_name else "POST")
        if entry.num_requests > 0:
            print(f"\nMetrics for {entry_name}:")
            print(f"  Requests: {entry.num_requests}")
            print(f"  Failures: {entry.num_failures}")
            print(f"  Error Rate: {(entry.num_failures / entry.num_requests * 100):.2f}%")
            print(f"  p99 Response Time: {entry.get_response_time_percentile(0.99):.2f} ms")
            print(f"  Avg Response Time: {entry.avg_response_time:.2f} ms")
