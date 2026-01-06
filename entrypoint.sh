#!/bin/bash

ODOO_BIN="odoo-src/odoo-bin"
CONFIG_FILE="config/odoo.conf"

refresh_config() {
    echo "Generating Odoo configuration..."
    python config/generate_config.py
    if [ $? -ne 0 ]; then
        echo "Error: Configuration refresh failed" >&2
        exit 1
    fi
}

# Check for app directory
if [ ! -d "/app" ]; then
    echo "Error: /app directory does not exist" >&2
    exit 1
fi

cd /app/ || exit

# Skip initialization if config exists, but ensure it is current
if [ -f "$CONFIG_FILE" ]; then
    echo "Odoo configuration found. Skipping initialization."
    refresh_config
    exec $ODOO_BIN --conf $CONFIG_FILE "$@"
    exit 0
fi

# Wait for PostgreSQL to become available
echo "Waiting for PostgreSQL..."
while ! (timeout 1 bash -c "</dev/tcp/$POSTGRES_HOST/$POSTGRES_PORT") >/dev/null 2>&1; do
    echo "  - Database not ready yet..."
    sleep 1
done
echo "PostgreSQL started"

# Generate configuration
refresh_config

# Initialize the Odoo database
# We include 'base' and 'hrmis_registry' to ensure the core environment is ready
echo "Initializing Odoo Database..."
$ODOO_BIN -c $CONFIG_FILE -d $POSTGRES_DB -i base -i hrmis_registry --no-http --stop-after-init --db_user=$POSTGRES_USER --db_password=$POSTGRES_PASSWORD

if [ $? -ne 0 ]; then
    echo "Error: Database initialization failed." >&2
    exit 1
fi

# Set the admin password via Odoo shell
echo "Setting Odoo Admin Password..."
$ODOO_BIN shell -c $CONFIG_FILE -d $POSTGRES_DB <<EOF
admin_user = env['res.users'].search([('login', '=', 'admin')], limit=1)
if admin_user:
    admin_user.password = '$ODOO_PASSWORD'
    env.cr.commit()
    print("Admin password changed successfully.")
else:
    print("Error: Admin user not found!")
    exit(1)
EOF

# Start the Odoo Server
exec $ODOO_BIN --conf $CONFIG_FILE "$@"