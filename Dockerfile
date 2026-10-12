# Image unique (Railway, un seul service) : nginx sert le front et relaie /api vers gunicorn, dans le même conteneur.
# Pour des services séparés, voir backend/Dockerfile et frontend/Dockerfile (docker-compose.yml).

# --- étape 1 : compile le module Rust
FROM python:3.12-slim AS rust-build
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"
RUN pip install --no-cache-dir maturin
WORKDIR /build
COPY backend/planning_rs ./planning_rs
RUN cd planning_rs && cargo test --lib && maturin build --release -o /wheels

# --- étape 2 : image finale
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=8080
RUN apt-get update && apt-get install -y --no-install-recommends nginx gettext-base \
    && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=rust-build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY backend/ .
COPY frontend/ /usr/share/nginx/html/
RUN echo 'window.TASKFLOW_API = "/api";' > /usr/share/nginx/html/config.js
COPY deploy/nginx.conf.template /etc/nginx/templates/site.conf.template
COPY deploy/start.sh /start.sh
CMD ["bash", "/start.sh"]
