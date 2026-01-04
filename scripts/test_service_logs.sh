#!/bin/bash

BASE="http://localhost:8000/mother/chat"
AUTH=$(echo -n 'admin:RobaDaMatti' | base64)

test_service() {
    local num=$1
    local name=$2
    local query=$3
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "$num $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    response=$(curl -s -X POST "$BASE" \
      -H "Content-Type: application/json" \
      -H "Authorization: Basic $AUTH" \
      -d "{\"query\": \"$query\"}")
    
    echo "$response" | jq -r '.response' | head -20
    echo ""
}

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        Service Log Testing - Verifying No Cross-Talk           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

test_service "1️⃣ " "SYSTEM_BACKUP" "What was the backup speed?"
test_service "2️⃣ " "NORDVPN_CONNECTED" "What VPN servers has nordvpn used?"
test_service "3️⃣ " "NORDVPND" "Show nordvpnd service activity"
test_service "4️⃣ " "TAILSCALED" "What does tailscaled show?"
test_service "5️⃣ " "SANOID_ERRORS" "Show sanoid snapshot info"
test_service "6️⃣ " "ZFS-ZED" "What zfs-zed events?"
test_service "7️⃣ " "JELLYFIN" "What jellyfin logs show?"

