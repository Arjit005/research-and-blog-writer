from locust import HttpUser, task, between

class Visitor(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def health_check(self):
        self.client.get("/health")
