#!/bin/bash

ENV_FILE=".env"
COMPOSE_FILES="-f compose.yml -f compose.override.yml"
MODE="DEVELOPMENT"

# Check for the --prod flag
for arg in "$@"
do
    if [ "$arg" == "--prod" ]; then
        ENV_FILE=".env.prod"
        # In Prod, we use the specific prod override
        COMPOSE_FILES="-f compose.yml -f compose.prod.yml"
        MODE="PRODUCTION"
    fi
done

# Visual Confirmation
echo "----------------------------------------------------"
echo "🚀 Launching Sindh HRMIS in [$MODE] mode"
echo "📂 Using Environment: $ENV_FILE"
echo "----------------------------------------------------"

# Check if the env file actually exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: Configuration file '$ENV_FILE' not found!"
    echo "   Please create it based on the template provided."
    exit 1
fi

# The Command
# 1. Load the env file exports so Docker Compose CLI sees them
# 2. Run the compose command with the selected files
# 3. --build forces a rebuild of the image (crucial for Odoo changes)
# 4. -d runs in detached mode (background)
set -a
source "$ENV_FILE"
docker compose $COMPOSE_FILES up -d --build --remove-orphans

# Post-launch logic
if [ $? -eq 0 ]; then
    echo "✅ System is running!"
    if [ "$MODE" == "DEVELOPMENT" ]; then
        echo "   📝 Logs: docker compose logs -f odoo"
        echo "   🌍 Web:  http://localhost:8069"
    else
        echo "   🔒 Production Mode active."
    fi
else
    echo "❌ Failed to start Docker Compose."
fi

