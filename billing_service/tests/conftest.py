import os

os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "aegra")
os.environ.setdefault("PADDLE_API_KEY", "test-paddle-api-key")
os.environ.setdefault("PADDLE_WEBHOOK_SECRET", "test-paddle-webhook-secret")
os.environ.setdefault("INTERNAL_API_SECRET", "test-internal-api-secret")
