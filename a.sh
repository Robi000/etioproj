#!/usr/bin/env bash

cd "/c/Users/rabeb/OneDrive/Desktop/personalV1"

source venv/Scripts/activate

echo ""
echo "Starting Cloudflare Tunnel..."
echo ""

cloudflared tunnel --url http://localhost:8000
