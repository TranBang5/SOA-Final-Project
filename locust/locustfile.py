import random
import string
from locust import HttpUser, task, between

class PasteServiceUser(HttpUser):
    # Wait between 1 and 5 seconds between tasks to simulate realistic user behavior
    wait_time = between(1, 5)
    
    # Store created paste URLs to simulate viewing
    created_pastes = []

    @task(3)  # Weight: Create pastes more frequently
    def create_paste(self):
        # Generate random paste content (10-50 characters)
        content = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(10, 50)))
        # Random expiration (1 hour, 1 day, or none)
        expires_in = random.choice([60, 1440, None])
        
        payload = {
            "content": content,
            "expires_in": expires_in
        }
        
        # Send POST request to create a paste
        response = self.client.post(
            "/pastes/",
            json=payload,
            headers={"Content-Type": "application/json"},
            name="Create Paste"
        )
        
        if response.status_code == 201:
            # Store the paste URL for viewing
            data = response.json()
            if "url" in data:
                self.created_pastes.append(data["url"])
                self.environment.events.request_success.fire(
                    request_type="POST",
                    name="Create Paste Success",
                    response_time=response.elapsed.total_seconds() * 1000,
                    response_length=len(response.text)
                )
            else:
                self.environment.events.request_failure.fire(
                    request_type="POST",
                    name="Create Paste Failure",
                    response_time=response.elapsed.total_seconds() * 1000,
                    exception="No URL in response"
                )
        else:
            self.environment.events.request_failure.fire(
                request_type="POST",
                name="Create Paste Failure",
                response_time=response.elapsed.total_seconds() * 1000,
                exception=f"Status code: {response.status_code}"
            )

    @task(7)  # Weight: View pastes more frequently
    def view_paste(self):
        if not self.created_pastes:
            return  # Skip if no pastes have been created
        
        # Randomly select a paste URL to view
        short_url = random.choice(self.created_pastes)
        
        # Send GET request to view the paste
        response = self.client.get(
            f"/paste/{short_url}",
            name="View Paste"
        )
        
        if response.status_code == 200:
            self.environment.events.request_success.fire(
                request_type="GET",
                name="View Paste Success",
                response_time=response.elapsed.total_seconds() * 1000,
                response_length=len(response.text)
            )
        else:
            self.environment.events.request_failure.fire(
                request_type="GET",
                name="View Paste Failure",
                response_time=response.elapsed.total_seconds() * 1000,
                exception=f"Status code: {response.status_code}"
            )

    def on_start(self):
        # Set host to view service for viewing pastes
        # We'll override the host for create_paste in tasks
        self.client.base_url = "http://view-service:5002"
        
        # Create an initial paste to ensure there’s something to view
        self.client.base_url = "http://paste-service:5000"
        self.create_paste()
        self.client.base_url = "http://view-service:5002"