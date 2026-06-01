#!/bin/sh
set -e

# On first run, seed data if the data file does not exist or is empty
if [ ! -s "$TICKET_DATA_FILE" ]; then
    echo "No data found, running seed script..."
    python seed.py
else
    echo "Existing data found, skipping seed."
fi

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
