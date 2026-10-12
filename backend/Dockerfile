# --- étape 1 : compile le module Rust (roue abi3 : valable pour tout Python >= 3.10)
FROM python:3.12-slim AS rust-build
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"
RUN pip install --no-cache-dir maturin
WORKDIR /build
COPY planning_rs ./planning_rs
RUN cd planning_rs && cargo test --lib && maturin build --release -o /wheels

# --- étape 2 : image finale (sans compilateur)
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=rust-build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && gunicorn taskflow.wsgi:application -b 0.0.0.0:8000"]
