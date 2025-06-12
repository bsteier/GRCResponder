#!/bin/bash

# Exit immediately if any command fails
set -e

echo "Starting GRCResponder backend and frontend..."

# Start backend
echo "Starting backend..."
cd server
source venv/bin/activate
cd backend
uvicorn main:app --reload &

# Capture backend PID
BACKEND_PID=$!
cd ../../

# Start frontend
echo "Starting frontend..."
cd client
npm start &

# Capture frontend PID
FRONTEND_PID=$!
cd ..

# Wait for both processes
echo "Backend PID: $BACKEND_PID, Frontend PID: $FRONTEND_PID"
echo "Press Ctrl+C to stop both servers."

# Wait on both to keep the script alive
wait $BACKEND_PID $FRONTEND_PID
