import os

os.environ.setdefault("NEO4J_PASSWORD", "test-neo4j-password")
os.environ.setdefault("SALESFORCE_CLIENT_ID", "test-salesforce-client-id")
os.environ.setdefault("SALESFORCE_PRIVATE_KEY_PATH", "graph_service/certs/salesforce/AxesRev.key")
os.environ.setdefault("SALESFORCE_LOGIN_URL", "https://login.salesforce.com")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "aegra")
