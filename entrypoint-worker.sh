#!/bin/bash

# Fix SSH permissions if mounted
if [ -d /tmp/.ssh_bind ]; then
    mkdir -p /root/.ssh
    cp -r /tmp/.ssh_bind/* /root/.ssh/ 2>/dev/null || true
    chown -R root:root /root/.ssh
    chmod 700 /root/.ssh
    chmod 600 /root/.ssh/* 2>/dev/null || true
fi

echo "🚀 Checking database state..."
cd /app

# Check if processing_jobs table already exists
python << 'EOF'
import os
from sqlalchemy import create_engine, inspect

db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://transkribator:transkribator@postgres:5432/transkribator")
try:
    engine = create_engine(db_url, echo=False)
    with engine.connect() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        if "processing_jobs" in tables:
            print("✅ Database already initialized (processing_jobs table exists)")
            exit(0)
        else:
            print("⚠️ Database not initialized yet, will run migrations...")
            exit(1)
except Exception as e:
    print(f"⚠️ Could not check database state: {e}")
    print("Will attempt to run migrations...")
    exit(1)
EOF

DB_CHECK=$?

if [ $DB_CHECK -eq 0 ]; then
    echo "Skipping migrations (already applied)"
else
    echo "🔧 Applying database migrations..."
    python -m alembic upgrade heads
    if [ $? -ne 0 ]; then
        echo "❌ Migration failed!"
        exit 1
    fi
    echo "✅ Migrations applied successfully"
fi

echo "🔄 Starting worker..."
exec "$@"
