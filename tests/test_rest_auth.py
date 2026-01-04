#!/usr/bin/env python3
"""Test REST API authentication with new chat credentials."""

import base64
import json
import time

# Wait for server to be ready
time.sleep(2)

# Test cases
test_cases = [
    {
        "name": "✓ Correct chat credentials",
        "username": "admin",
        "password": "testsecure123",
        "expected": "success",
    },
    {
        "name": "✗ Wrong password",
        "username": "admin",
        "password": "wrongpassword",
        "expected": "fail",
    },
    {
        "name": "✗ Non-existent user",
        "username": "unknown",
        "password": "anypassword",
        "expected": "fail",
    },
]

import subprocess

for test in test_cases:
    username = test["username"]
    password = test["password"]
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    
    result = subprocess.run(
        [
            "pixi", "run", "curl",
            "-s", "-w", "\n%{http_code}",
            "-H", f"Authorization: Basic {credentials}",
            "http://localhost:8000/health"
        ],
        cwd="/home/heverz/py_projects/monit-intel",
        capture_output=True,
        text=True
    )
    
    output = result.stdout.strip().split('\n')
    http_code = output[-1]
    
    if test["expected"] == "success":
        if http_code == "200":
            print(f"{test['name']}: HTTP {http_code}")
        else:
            print(f"{test['name']}: FAILED (got {http_code}, expected 200)")
    else:
        if http_code == "401":
            print(f"{test['name']}: HTTP {http_code}")
        else:
            print(f"{test['name']}: FAILED (got {http_code}, expected 401)")

print("\nREST API authentication tests completed!")
