from locust import HttpUser, task, between
import random
import string

class PastebinUser(HttpUser):
    wait_time = between(1, 5)  # Wait between 1 and 5 seconds between tasks
    token = None

    def on_start(self):
        # Register a new user and get token
        username = ''.join(random.choices(string.ascii_lowercase, k=8))
        email = f"{username}@test.com"
        password = "test123"
        
        # Register
        self.client.post("/auth/register", json={
            "username": username,
            "email": email,
            "password": password
        })
        
        # Login
        response = self.client.post("/auth/login", json={
            "username": username,
            "password": password
        })
        self.token = response.json()["access_token"]

    @task(3)
    def create_paste(self):
        # Create a new paste
        headers = {"Authorization": f"Bearer {self.token}"}
        content = ''.join(random.choices(string.ascii_letters + string.digits, k=100))
        self.client.post("/paste/create", 
                        json={"content": content},
                        headers=headers)

    @task(5)
    def read_paste(self):
        # Read a random paste
        paste_id = random.randint(1, 1000)
        self.client.get(f"/paste/{paste_id}")

    @task(2)
    def update_paste(self):
        # Update an existing paste
        headers = {"Authorization": f"Bearer {self.token}"}
        paste_id = random.randint(1, 1000)
        content = ''.join(random.choices(string.ascii_letters + string.digits, k=100))
        self.client.put(f"/paste/{paste_id}", 
                       json={"content": content},
                       headers=headers)

    @task(1)
    def delete_paste(self):
        # Delete a paste
        headers = {"Authorization": f"Bearer {self.token}"}
        paste_id = random.randint(1, 1000)
        self.client.delete(f"/paste/{paste_id}", headers=headers)

    @task(4)
    def view_analytics(self):
        # View analytics for a paste
        headers = {"Authorization": f"Bearer {self.token}"}
        paste_id = random.randint(1, 1000)
        self.client.get(f"/analytics/{paste_id}", headers=headers) 