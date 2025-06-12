#!/bin/bash

# Exit on any error
set -e

echo "Setting up GRCResponder Environment for MAC..."

# Install system dependencies
echo "Installing system dependencies..."

# Check for Homebrew
if ! command -v brew &> /dev/null; then
  echo "Homebrew not found. Installing..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
  echo "Homebrew found."
fi

# Install dependencies
brew install python@3.11 postgresql

# Start PostgreSQL service
brew services start postgresql

# Create database and user (skip if already created)
createuser -s adminuser || echo "user adminuser may already exist"
createdb -O adminuser accenture || echo "database may already exist"

cd server/backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip and install backend requirements
pip install --upgrade pip
pip install -r requirements.txt

echo "Initializing database tables..."
python << END
from models import Base, engine
Base.metadata.create_all(bind=engine)
print("Database tables created.")
END

deactivate
cd ../../

echo "Setting up React frontend..."

cd client

# Install Node.js dependencies
npm install

cd ..

echo "Setup complete! To start your app:"
echo "1. run ./run.sh"
