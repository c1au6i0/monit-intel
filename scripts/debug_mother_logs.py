#!/usr/bin/env python3
"""Debug script to trace what logs Mother is retrieving."""

import sys
sys.path.insert(0, 'src')

from monit_intel.agent.mother import Mother

# Create Mother instance
mother = Mother()

# Get service context
service_context = mother.get_service_context()

# Extract services from query
query = "Tell me about the backup service"
mentioned_services = mother._extract_services(query, service_context)
print(f"✓ Mentioned services: {mentioned_services}")

# Try to build context
if mentioned_services:
    for service in mentioned_services:
        print(f"\n=== Service: {service} ===")
        
        # Get logs directly
        logs = mother.get_service_logs(service)
        print(f"Logs returned: {len(logs)} chars")
        if logs:
            print(f"First 200 chars: {logs[:200]}")
            print(f"Last 200 chars: {logs[-200:]}")
        else:
            print("❌ No logs returned!")
        
        # Check if in context
        if service in service_context:
            info = service_context[service]
            print(f"Status: {info['healthy']}")
            print(f"Last checked: {info['last_checked']}")

# Build full context
context_info = mother._build_context_info(mentioned_services, service_context)
print(f"\n=== Full context_info ({len(context_info)} chars) ===")
print(context_info)

# Get historical trends
historical_info = mother.get_historical_trends(services=mentioned_services, days=30)
print(f"\n=== Historical info ({len(historical_info)} chars) ===")
print(historical_info)
