import os
import sys
from string import Template

# --- Configuration ---
ENV_FILE_PATH = ".env"  # Path to your secret file
TEMPLATE_PATH = "config/odoo.conf.template"
CONFIG_PATH = "config/odoo.conf"

def load_env_into_dict(filepath: str) -> dict[str, str]:
    """
    Parses a .env file and returns a dictionary of variables.
    """
    env_vars = {}
    if os.path.exists(filepath):
        print(f"Loading variables from {filepath}...")
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove surrounding quotes
                    if (value.startswith('"') and value.endswith('"')) or \
                            (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]

                    env_vars[key] = value
    else:
        print(f"No .env file found at {filepath}. Using system env only.")

    return env_vars

# --- Main Execution ---

# 1. Start with System Environment Variables
# We copy them so we can update this dict without affecting the actual OS environment if we wanted to
full_environment = dict(os.environ)

# 2. Load .env file and merge (System Env takes priority)
file_vars = load_env_into_dict(ENV_FILE_PATH)
for key, value in file_vars.items():
    if key not in full_environment:
        full_environment[key] = value

# 3. Read Template
if not os.path.exists(TEMPLATE_PATH):
    print(f"Error: Template not found at {TEMPLATE_PATH}")
    sys.exit(1)

with open(TEMPLATE_PATH, "r") as template_file:
    template_content = template_file.read()

# 4. Strict Substitution
try:
    # Template(text).substitute(mapping) raises KeyError if a placeholder is missing in the mapping
    # Note: Use $VAR or ${VAR} in your template file.
    t = Template(template_content)
    final_content = t.substitute(full_environment)

    # 5. Write Result
    with open(CONFIG_PATH, "w") as config_file:
        config_file.write(final_content)

    print(f"Success: Generated {CONFIG_PATH}")

except KeyError as e:
    # The error message 'e' will contain the name of the missing variable (e.g., 'DB_PASSWORD')
    print(f"\n[CRITICAL ERROR] Missing environment variable: {e}")
    print("The template requires this variable, but it was not found in the system env or .env file.")
    print("Aborting Odoo startup to prevent misconfiguration.\n")
    sys.exit(1)

except Exception as e:
    print(f"Unexpected error: {e}")
    sys.exit(1)