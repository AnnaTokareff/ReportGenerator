#!/usr/bin/env python3
"""
Usage:
    python run_pipeline.py --file meeting.mp3 --title "Team Meeting"
    python run_pipeline.py --file meeting.mp4 --title "Video Meeting" --username testuser
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import httpx


class MeetingPipeline:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client(timeout=300.0)
        self.token: Optional[str] = None
        self.username: Optional[str] = None

    def register(self, username: str, password: str) -> bool:
        print(f"Registering user: {username}...")
        try:
            response = self.client.post(
                f"{self.base_url}/auth/signup",
                json={"username": username, "password": password},
            )

            if response.status_code == 201:
                print("User registered successfully")
                return True

            if response.status_code == 400:
                print("User already exists, continuing")
                return True

            print(f"Registration failed: {response.status_code} - {response.text}")
            return False

        except Exception as e:
            print(f"Registration error: {e}")
            return False

    def login(self, username: str, password: str) -> bool:
        print(f"Logging in as {username}...")
        try:
            response = self.client.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password},
            )

            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.username = username
                print("Login successful")
                return True

            print(f"Login failed: {response.status_code} - {response.text}")
            return False

        except Exception as e:
            print(f"Login error: {e}")
            return False

    def upload_file(self, file_path: str, title: str) -> Optional[int]:
        """Upload audio or video file"""
        file = Path(file_path)
        if not file.exists():
            print(f"File not found: {file_path}")
            return None

        size_mb = file.stat().st_size / (1024 * 1024)
        print(f"Uploading file: {file.name} ({size_mb:.2f} MB)")

        if size_mb > 25:
            print("Warning: file size exceeds 25 MB Whisper API limit")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != "y":
                return None

        try:
            with open(file, "rb") as f:
                response = self.client.post(
                    f"{self.base_url}/meetings/upload",
                    headers={"Authorization": f"Bearer {self.token}"},
                    files={"file": (file.name, f, "application/octet-stream")},
                    data={"title": title},
                )

            if response.status_code == 201:
                meeting_id = response.json().get("id")
                print(f"Upload successful, meeting id: {meeting_id}")
                return meeting_id

            print(f"Upload failed: {response.status_code} - {response.text}")
            return None

        except Exception as e:
            print(f"Upload error: {e}")
            return None

    def wait_for_completion(self, meeting_id: int, interval: int = 5) -> bool:
        print(f"Waiting for processing to complete (meeting {meeting_id})")

        headers = {"Authorization": f"Bearer {self.token}"}
        start_time = time.time()

        while True:
            try:
                response = self.client.get(
                    f"{self.base_url}/meetings/{meeting_id}/status",
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")
                    message = data.get("message", "")
                    elapsed = int(time.time() - start_time)

                    print(f"[{elapsed}s] Status: {status} {message}")

                    if status == "completed":
                        print("Processing completed successfully")
                        return True

                    if status == "failed":
                        print(f"Processing failed: {data.get('error_message')}")
                        return False

                time.sleep(interval)

            except KeyboardInterrupt:
                print("Interrupted by user")
                return False

            except Exception as e:
                print(f"Status check error: {e}")
                time.sleep(interval)

    def get_results(self, meeting_id: int) -> Optional[dict]:
        print(f"Fetching results for meeting {meeting_id}")

        try:
            response = self.client.get(
                f"{self.base_url}/meetings/{meeting_id}",
                headers={"Authorization": f"Bearer {self.token}"},
            )

            if response.status_code == 200:
                print("Results received")
                return response.json()

            print(f"Failed to get results: {response.status_code}")
            return None

        except Exception as e:
            print(f"Results error: {e}")
            return None

    def generate_report(self, meeting_id: int, output_file: Optional[str] = None) -> bool:
        """Generate markdown report."""
        print(f"Generating report for meeting {meeting_id}")

        try:
            response = self.client.post(
                f"{self.base_url}/meetings/{meeting_id}/report",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json={
                    "include_transcription": True,
                    "include_timestamps": False,
                },
            )

            if response.status_code != 200:
                print(f"Report generation failed: {response.status_code}")
                return False

            content = response.json().get("content", "")
            filename = output_file or f"meeting_{meeting_id}_report.md"
            Path(filename).write_text(content, encoding="utf-8")

            print(f"Report saved to {filename}")
            return True

        except Exception as e:
            print(f"Report error: {e}")
            return False

    def print_summary(self, results: dict):
        """Print short summary."""
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        if results.get("topics"):
            print(f"Topics: {len(results['topics'])}")

        if results.get("decisions"):
            print(f"Decisions: {len(results['decisions'])}")

        if results.get("action_items"):
            print(f"Action items: {len(results['action_items'])}")

        print("=" * 60)

    def run_full_pipeline(
        self,
        file_path: str,
        title: str,
        username: str,
        password: str,
        output_file: Optional[str] = None,
    ) -> bool:
        """Run full pipeline."""
        print("Starting meeting processing pipeline")
        print("=" * 60)

        if not self.register(username, password):
            return False

        if not self.login(username, password):
            return False

        meeting_id = self.upload_file(file_path, title)
        if not meeting_id:
            return False

        if not self.wait_for_completion(meeting_id):
            return False

        results = self.get_results(meeting_id)
        if not results:
            return False

        self.print_summary(results)

        if not self.generate_report(meeting_id, output_file):
            return False

        print("Pipeline completed successfully")
        return True


def main():
    parser = argparse.ArgumentParser(description="Meeting processing pipeline")

    parser.add_argument("--file", required=True, help="Path to audio or video file")
    parser.add_argument("--title", required=True, help="Meeting title")
    parser.add_argument("--username", default="testuser")
    parser.add_argument("--password", default="testpass123")
    parser.add_argument("--output", help="Output report file")
    parser.add_argument("--url", default="http://localhost:8000")

    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"File not found: {args.file}")
        sys.exit(1)

    pipeline = MeetingPipeline(base_url=args.url)
    success = pipeline.run_full_pipeline(
        file_path=args.file,
        title=args.title,
        username=args.username,
        password=args.password,
        output_file=args.output,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
