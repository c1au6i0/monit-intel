#!/bin/bash

BASE="http://localhost:8000/mother/chat"
AUTH=$(echo -n 'admin:RobaDaMatti' | base64)

test_service() {
    local name=$1
    local query=$2
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    curl -s -X POST "$BASE" \
      -H "Content-Type: application/json" \
      -H "Authorization: Basic $AUTH" \
      -d "{\"query\": \"$query\"}" | jq -r '.response'
    
    echo ""
}

echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║         Testing All 7 Services with Direct Log Access                 ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"

test_service "1️⃣  SYSTEM_BACKUP (file)" "What was the backup speed and speedup ratio?"
test_service "2️⃣  NORDVPN_CONNECTED (file)" "What VPN servers has nordvpn_connected used recently?"
test_service "3️⃣  NORDVPND (journalctl)" "Show nordvpnd service logs - any connection issues?"
test_service "4️⃣  TAILSCALED (journalctl)" "What does the tailscaled service journal show recently?"
test_service "5️⃣  SANOID_ERRORS (journalctl)" "Show sanoid service logs - any errors?"
test_service "6️⃣  ZFS-ZED (journalctl)" "What zfs-zed events have been processed recently?"

echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║         Testing Docker Service (Should Explain No Access)             ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

test_service "7️⃣  JELLYFIN_RUNNING (Docker)" "What do the jellyfin logs show?"

echo ""
echo "✅ All tests completed!"
