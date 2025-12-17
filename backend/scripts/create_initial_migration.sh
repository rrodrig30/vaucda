#!/bin/bash
# Create initial Alembic migration for VAUCDA backend

set -e

echo "Creating initial Alembic migration for VAUCDA SQLite database..."

# Navigate to backend directory
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Create initial migration
echo "Generating initial migration..."
alembic revision --autogenerate -m "Initial database schema"

# Apply migration
echo "Applying migration..."
alembic upgrade head

echo "Migration complete!"
echo ""
echo "Database created at: $(grep SQLITE_DATABASE_URL .env | cut -d= -f2)"
echo ""
echo "To view migration history:"
echo "  alembic history"
echo ""
echo "To rollback migration:"
echo "  alembic downgrade -1"
