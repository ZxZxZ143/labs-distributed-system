"""Optional equivalent workload; the submitted measurements use load_test.py."""
from locust import HttpUser, task, between


class ApiUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def get_time(self):
        self.client.get("/time")

    @task(1)
    def create_record(self):
        self.client.post("/records", json={"text": "load"})
