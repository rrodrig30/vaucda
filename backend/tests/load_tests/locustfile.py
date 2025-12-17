"""
VAUCDA Load Testing Suite
Simulates realistic clinical workflow patterns

Usage:
    # Baseline: 10 concurrent users
    locust -f tests/load_tests/locustfile.py --users 10 --spawn-rate 2 --host http://localhost:8000

    # Target: 500 concurrent users
    locust -f tests/load_tests/locustfile.py --users 500 --spawn-rate 10 --host http://localhost:8000 --run-time 10m

    # Stress test: 1000 users
    locust -f tests/load_tests/locustfile.py --users 1000 --spawn-rate 20 --host http://localhost:8000 --run-time 5m

    # Headless mode with CSV output
    locust -f tests/load_tests/locustfile.py --headless --users 500 --spawn-rate 10 \
           --run-time 10m --html=report.html --csv=results
"""

import random
import json
import time
from locust import HttpUser, task, between, events
from locust.exception import StopUser


class VAUCDAUser(HttpUser):
    """
    Simulates a VA urologist using VAUCDA

    User behavior distribution:
    - 50% Note generation (most common)
    - 30% Calculator usage
    - 15% Knowledge base search
    - 5% Settings/admin
    """

    # Think time between requests (1-3 seconds)
    wait_time = between(1, 3)

    # Token storage
    token = None
    user_id = None

    def on_start(self):
        """Called when a user starts - performs login"""
        self.login()

    def on_stop(self):
        """Called when a user stops - performs logout"""
        if self.token:
            self.logout()

    def login(self):
        """Authenticate and get JWT token"""
        # Use test credentials (should be created in test database)
        test_users = [
            {"email": f"loadtest{i}@va.gov", "password": "LoadTest123!@#"}
            for i in range(1, 101)  # 100 test users
        ]

        credentials = random.choice(test_users)

        with self.client.post(
            "/api/v1/auth/login",
            json=credentials,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.user_id = data.get("user_id")
                response.success()
            elif response.status_code == 401:
                # User doesn't exist, try to register
                self.register(credentials)
            else:
                response.failure(f"Login failed with status {response.status_code}")
                raise StopUser()

    def register(self, credentials):
        """Register new user if doesn't exist"""
        with self.client.post(
            "/api/v1/auth/register",
            json={
                "email": credentials["email"],
                "password": credentials["password"],
                "full_name": f"Load Test User"
            },
            catch_response=True
        ) as response:
            if response.status_code == 201:
                response.success()
                # Login after registration
                self.login()
            else:
                response.failure(f"Registration failed: {response.text}")
                raise StopUser()

    def logout(self):
        """Logout and invalidate token"""
        if not self.token:
            return

        self.client.post(
            "/api/v1/auth/logout",
            headers=self.get_auth_header()
        )

    def get_auth_header(self):
        """Get authorization header with JWT token"""
        return {"Authorization": f"Bearer {self.token}"}

    @task(10)
    def generate_clinic_note(self):
        """
        Generate clinic note (most common operation)
        Weight: 10 (50% of tasks)
        """
        if not self.token:
            return

        # Sample clinical data (realistic but fictional)
        clinical_inputs = [
            "65yo male with PSA 7.2, BPH symptoms (IPSS 18), considering TURP",
            "72yo male with elevated PSA 12.5, Gleason 4+3=7, discussed radical prostatectomy vs radiation",
            "58yo female with stress urinary incontinence, failed pelvic floor therapy, considering midurethral sling",
            "45yo male with 8mm kidney stone, severe pain, planning ureteroscopy",
            "61yo male with BCG-unresponsive NMIBC, discussed cystectomy options",
            "70yo male post-TURP, doing well, PSA stable at 2.1",
            "38yo male with infertility, semen analysis shows oligospermia, referred to fertility specialist",
            "55yo male with Peyronie's disease, stable plaque, discussing treatment options",
        ]

        payload = {
            "input_text": random.choice(clinical_inputs),
            "note_type": random.choice(["clinic", "consult", "follow_up"]),
            "llm_provider": random.choice(["ollama", "anthropic", "openai"]),
            "use_rag": random.choice([True, False]),
            "include_calculators": random.choice([True, False])
        }

        with self.client.post(
            "/api/v1/notes/generate",
            headers=self.get_auth_header(),
            json=payload,
            catch_response=True,
            name="Generate Note (Clinic)"
        ) as response:
            if response.status_code == 200:
                # Check response time
                if response.elapsed.total_seconds() > 10:
                    response.failure(f"Note generation too slow: {response.elapsed.total_seconds()}s")
                else:
                    response.success()
            else:
                response.failure(f"Note generation failed: {response.status_code}")

    @task(3)
    def generate_procedure_note(self):
        """
        Generate procedure note (less common)
        Weight: 3 (15% of tasks)
        """
        if not self.token:
            return

        procedure_inputs = [
            "Cystoscopy performed, no masses seen, mild trabeculation",
            "TURP completed, 45g tissue removed, minimal bleeding",
            "Ureteroscopy with laser lithotripsy, stone fragmented",
            "Vasectomy performed without complications",
            "Midurethral sling placement, excellent positioning on cystoscopy",
        ]

        payload = {
            "input_text": random.choice(procedure_inputs),
            "note_type": "procedure",
            "llm_provider": "ollama",
            "use_rag": True
        }

        with self.client.post(
            "/api/v1/notes/generate",
            headers=self.get_auth_header(),
            json=payload,
            catch_response=True,
            name="Generate Note (Procedure)"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed: {response.status_code}")

    @task(6)
    def run_calculator(self):
        """
        Execute clinical calculator
        Weight: 6 (30% of tasks)
        """
        if not self.token:
            return

        # Different calculators with realistic inputs
        calculators = [
            {
                "name": "ipss",
                "inputs": {
                    "incomplete_emptying": random.randint(0, 5),
                    "frequency": random.randint(0, 5),
                    "intermittency": random.randint(0, 5),
                    "urgency": random.randint(0, 5),
                    "weak_stream": random.randint(0, 5),
                    "straining": random.randint(0, 5),
                    "nocturia": random.randint(0, 5)
                }
            },
            {
                "name": "capra",
                "inputs": {
                    "age": random.randint(50, 80),
                    "psa": round(random.uniform(4.0, 20.0), 1),
                    "gleason_primary": random.choice([3, 4, 5]),
                    "gleason_secondary": random.choice([3, 4, 5]),
                    "clinical_stage": random.choice(["T1c", "T2a", "T2b", "T3a"]),
                    "percent_positive_cores": random.randint(10, 100)
                }
            },
            {
                "name": "eortc_recurrence",
                "inputs": {
                    "number_of_tumors": random.choice([1, 2, 5, 8]),
                    "tumor_size_cm": round(random.uniform(1.0, 5.0), 1),
                    "recurrence_rate": random.choice(["primary", "1_per_year", "gt_1_per_year"]),
                    "category": random.choice(["Ta", "T1"]),
                    "grade": random.choice(["G1", "G2", "G3"]),
                    "cis": random.choice([True, False])
                }
            },
            {
                "name": "stone_score",
                "inputs": {
                    "stone_size_mm": random.randint(3, 15),
                    "location": random.choice(["lower", "middle", "upper"]),
                    "number_of_stones": random.randint(1, 4),
                    "hounsfield_units": random.randint(500, 1500)
                }
            },
        ]

        calc = random.choice(calculators)

        with self.client.post(
            f"/api/v1/calculators/{calc['name']}/calculate",
            headers=self.get_auth_header(),
            json={"inputs": calc['inputs']},
            catch_response=True,
            name=f"Calculator: {calc['name']}"
        ) as response:
            if response.status_code == 200:
                # Calculators should be fast
                if response.elapsed.total_seconds() > 0.5:
                    response.failure(f"Calculator too slow: {response.elapsed.total_seconds()}s")
                else:
                    response.success()
            else:
                response.failure(f"Calculator failed: {response.status_code}")

    @task(3)
    def search_knowledge_base(self):
        """
        Search RAG knowledge base
        Weight: 3 (15% of tasks)
        """
        if not self.token:
            return

        queries = [
            "prostate cancer treatment options",
            "bladder cancer staging",
            "kidney stone management guidelines",
            "BPH medical management",
            "stress incontinence surgical options",
            "testicular torsion diagnosis",
            "erectile dysfunction treatment",
            "vasectomy complications",
        ]

        payload = {
            "query": random.choice(queries),
            "limit": random.choice([5, 10, 20])
        }

        with self.client.post(
            "/api/v1/rag/search",
            headers=self.get_auth_header(),
            json=payload,
            catch_response=True,
            name="RAG Search"
        ) as response:
            if response.status_code == 200:
                # RAG search should be fast
                if response.elapsed.total_seconds() > 0.2:
                    response.failure(f"RAG search too slow: {response.elapsed.total_seconds()}s")
                else:
                    response.success()
            else:
                response.failure(f"RAG search failed: {response.status_code}")

    @task(1)
    def get_user_settings(self):
        """
        Retrieve user settings
        Weight: 1 (5% of tasks)
        """
        if not self.token:
            return

        with self.client.get(
            "/api/v1/settings",
            headers=self.get_auth_header(),
            catch_response=True,
            name="Get Settings"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 501:
                # Settings endpoint not implemented yet
                response.success()
            else:
                response.failure(f"Get settings failed: {response.status_code}")

    @task(1)
    def update_user_settings(self):
        """
        Update user preferences
        Weight: 1 (5% of tasks)
        """
        if not self.token:
            return

        settings = {
            "preferred_llm": random.choice(["ollama", "anthropic", "openai"]),
            "default_note_type": random.choice(["clinic", "consult", "procedure"]),
            "enable_rag": random.choice([True, False]),
            "theme": random.choice(["light", "dark"])
        }

        with self.client.put(
            "/api/v1/settings",
            headers=self.get_auth_header(),
            json=settings,
            catch_response=True,
            name="Update Settings"
        ) as response:
            if response.status_code in [200, 501]:
                # 501 = not implemented yet
                response.success()
            else:
                response.failure(f"Update settings failed: {response.status_code}")

    @task(1)
    def health_check(self):
        """
        Health check endpoint (monitoring)
        Weight: 1 (5% of tasks)
        """
        with self.client.get(
            "/api/v1/health",
            catch_response=True,
            name="Health Check"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    response.success()
                else:
                    response.failure(f"System unhealthy: {data}")
            else:
                response.failure(f"Health check failed: {response.status_code}")


class HeavyUser(VAUCDAUser):
    """
    Power user - generates many notes with RAG enabled
    Represents 10% of users but 40% of load
    """
    wait_time = between(0.5, 1.5)  # Faster

    @task(15)
    def generate_complex_note(self):
        """Generate complex notes with RAG and calculators"""
        if not self.token:
            return

        payload = {
            "input_text": "72yo male, PSA 15.2, DRE firm nodule, MRI shows PI-RADS 5 lesion 2.5cm. " +
                          "Biopsy Gleason 4+4=8. Bone scan negative. Discussing treatment options. " +
                          "IPSS score 22, AUA symptom score severe.",
            "note_type": "consult",
            "llm_provider": "anthropic",  # Premium provider
            "use_rag": True,
            "include_calculators": True,
            "calculators": ["capra", "d_amico", "nccn_risk"]
        }

        with self.client.post(
            "/api/v1/notes/generate",
            headers=self.get_auth_header(),
            json=payload,
            catch_response=True,
            name="Generate Complex Note"
        ) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() > 15:
                    response.failure(f"Complex note too slow: {response.elapsed.total_seconds()}s")
                else:
                    response.success()
            else:
                response.failure(f"Failed: {response.status_code}")


# Event listeners for custom metrics
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Print test configuration when test starts"""
    print("\n" + "="*60)
    print("VAUCDA Load Test Starting")
    print("="*60)
    print(f"Target: {environment.host}")
    print(f"Users: {environment.runner.user_count if hasattr(environment.runner, 'user_count') else 'N/A'}")
    print("="*60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print summary when test stops"""
    print("\n" + "="*60)
    print("VAUCDA Load Test Complete")
    print("="*60)
    stats = environment.stats
    print(f"Total requests: {stats.total.num_requests}")
    print(f"Failures: {stats.total.num_failures}")
    print(f"Median response time: {stats.total.median_response_time}ms")
    print(f"95th percentile: {stats.total.get_response_time_percentile(0.95)}ms")
    print(f"Average response time: {stats.total.avg_response_time}ms")
    print(f"Requests/sec: {stats.total.total_rps}")
    print("="*60 + "\n")


# Custom task set for spike testing
class SpikeTestUser(VAUCDAUser):
    """
    Simulates sudden spike in traffic (e.g., training session)
    """
    wait_time = between(0.1, 0.5)  # Very fast

    @task(20)
    def rapid_note_generation(self):
        """Rapid-fire note generation"""
        if not self.token:
            return

        payload = {
            "input_text": "Quick note",
            "note_type": "clinic",
            "llm_provider": "ollama",
            "use_rag": False
        }

        with self.client.post(
            "/api/v1/notes/generate",
            headers=self.get_auth_header(),
            json=payload,
            catch_response=True,
            name="Rapid Note"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                # Rate limited - expected behavior
                response.success()
            else:
                response.failure(f"Failed: {response.status_code}")


# Custom shape for realistic load pattern
class RealisticLoadShape:
    """
    Simulates realistic usage pattern:
    - 8 AM: Clinic starts (ramp up)
    - 12 PM: Lunch (drop)
    - 1 PM: Afternoon clinic (ramp up)
    - 5 PM: End of day (ramp down)
    """

    def tick(self):
        """Returns (user_count, spawn_rate) tuples"""
        run_time = self.get_run_time()

        # Morning ramp (0-2 hours)
        if run_time < 7200:  # 2 hours
            return (int(run_time / 14.4), 5)  # 0 to 500 users

        # Morning peak (2-4 hours)
        elif run_time < 14400:
            return (500, 5)

        # Lunch dip (4-5 hours)
        elif run_time < 18000:
            return (250, 10)

        # Afternoon ramp (5-6 hours)
        elif run_time < 21600:
            return (int((run_time - 18000) / 14.4 + 250), 5)

        # Afternoon peak (6-8 hours)
        elif run_time < 28800:
            return (500, 5)

        # End of day (8-9 hours)
        else:
            return (int(500 - (run_time - 28800) / 14.4), 10)
