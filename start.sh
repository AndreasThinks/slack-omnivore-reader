#!/bin/bash

# Run the worker process
python summariser/newsletter_creator.py

# Wait for 3 minutes
echo "Waiting for 90 seconds..."
sleep 90

# Start the web process
uvicorn app:app --host=0.0.0.0 --port=$PORT