# ==========================================
# STAGE 1: BUILDER (Heavy Lifting)
# ==========================================
FROM debian:bookworm-slim AS builder

USER root

# 1. Install HEAVY Build Deps (GCC, Git, Headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git ca-certificates \
    libldap2-dev libpq-dev libsasl2-dev \
    libxml2-dev libxslt1-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python
ENV UV_COMPILE_BYTECODE=1

# 3. Build the Environment
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

# 4. Download Odoo Source
RUN git clone --depth 1 --branch 18.0 https://github.com/odoo/odoo.git /app/odoo-src \
    && uv pip install -r /app/odoo-src/requirements.txt \
    && uv pip install -e /app/odoo-src
# ==========================================
# STAGE 2: DEV (Tools Only - NO CODE COPY)
# ==========================================
FROM builder AS dev

RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH"

# 2. Setup User
RUN useradd -m -d /var/lib/odoo -s /bin/bash odoo
COPY --chown=odoo:odoo ./entrypoint.sh /app/entrypoint.sh

USER odoo

# ==========================================
# STAGE 3: PROD (Starts Fresh)
# ==========================================
# We switch back to a clean Debian image.
FROM debian:bookworm-slim AS prod

# 1. Install ONLY Runtime Deps (Shared Libraries)
#    Notice: libpq5 instead of libpq-dev
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libldap-2.5-0 libpq5 libsasl2-2 \
    && rm -rf /var/lib/apt/lists/*

# 2. COPY artifacts from Builder
#    We take only what we built, leaving the compilers behind.
COPY --from=builder /opt/python /opt/python
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/odoo-src /app/odoo-src

# 3. Setup User & Config
RUN useradd -m -d /var/lib/odoo -s /bin/bash odoo
COPY --chown=odoo:odoo ./modules /app/modules
COPY --chown=odoo:odoo ./config /app/config
COPY --chown=odoo:odoo ./entrypoint.sh /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"\