#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')
from monit_intel.agent.mother import Mother

mother = Mother()
service_context = mother.get_service_context()
mentioned = mother._extract_services('Did the zfs_sanoid service restart?', service_context)
print(f'Mentioned services: {mentioned}')

if mentioned:
    context_info = mother._build_context_info(mentioned, service_context)
    print(f'\nContext info:\n{context_info}')
    
    for service in mentioned:
        logs = mother.get_service_logs(service)
        if logs:
            print(f'\nLogs for {service} (first 1000 chars):\n{logs[:1000]}')
        else:
            print(f'\nNo logs for {service}')
else:
    print("No services mentioned in query")
