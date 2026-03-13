#!/bin/bash
# Startup script for user-specific backend container

# Set user-specific environment variables
export USER_ID=${USER_ID:-default}
export SESSION_TOKEN=${SESSION_TOKEN:-default}
export CUSTOM_CONFIG_PATH="/configs/${USER_ID}.json"

# Create user-specific config if it doesn't exist
mkdir -p /configs
if [ ! -f "$CUSTOM_CONFIG_PATH" ]; then
  echo '{"user_id":"'$USER_ID'", "created_at":"'$(date -I)'"}' > "$CUSTOM_CONFIG_PATH"
fi

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port 8000