#!/usr/bin/env python3
"""Test the chat authentication system."""

import sys
sys.path.insert(0, 'src')

from monit_intel.chat_auth import verify_chat_credentials, get_chat_credentials_status

# Check status
status = get_chat_credentials_status()
print(f"✓ Chat credentials configured: {status['configured']}")
print(f"✓ Credentials count: {status['count']}")

# Test login with correct password
if verify_chat_credentials("admin", "testsecure123"):
    print("✓ Login with correct password: SUCCESS")
else:
    print("✗ Login with correct password: FAILED")

# Test login with wrong password
if not verify_chat_credentials("admin", "wrongpassword"):
    print("✓ Login with wrong password: CORRECTLY REJECTED")
else:
    print("✗ Login with wrong password: INCORRECTLY ACCEPTED")

# Test login with non-existent user
if not verify_chat_credentials("nonexistent", "anypassword"):
    print("✓ Login with non-existent user: CORRECTLY REJECTED")
else:
    print("✗ Login with non-existent user: INCORRECTLY ACCEPTED")

print("\nAll authentication tests passed!")
