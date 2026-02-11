
# ==============================================================================
# FILE: run.sh (Startup script for Linux/Mac)
# ==============================================================================
#!/bin/bash

echo "🚀 Starting Rancher Release Bot..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please copy .env.example to .env and fill in your API keys"
    exit 1
fi

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install/upgrade dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Run the bot
echo "✅ Starting bot..."
python main.py
