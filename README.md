# ==============================================================================
# FILE: README.md
# ==============================================================================
# 🚀 Rancher Release Intelligence Bot

AI-powered Slack bot that monitors Rancher releases and provides actionable insights.

## Quick Start

### 1. Setup

```bash
# Clone and install
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### 2. Get API Keys

- **GitHub**: https://github.com/settings/tokens (scope: `repo`)
- **Claude**: https://console.anthropic.com/settings/keys
- **Slack**: https://api.slack.com/apps (scopes: `chat:write`, `commands`)

### 3. Run

```bash
# Local
python main.py

# Docker
docker-compose up -d
```

### 4. Test

```bash
# Health check
curl http://localhost:8000/health

# Slack commands
/rancher-release latest
/rancher-compare v2.12.0 v2.13.0
/rancher-search security
```

## Features

- ✅ Automatic release monitoring (every 2 hours)
- ✅ AI-powered analysis with Gemini
- ✅ Smart Slack notifications
- ✅ Interactive slash commands
- ✅ Jira/ServiceNow integration
- ✅ Knowledge base linking

## Architecture

```
GitHub → Monitor → Claude AI → Database → Slack
                        ↓
                   Jira/ServiceNow
```

## API Endpoints

- `GET /` - Health check
- `GET /releases` - List all releases
- `GET /releases/{version}` - Get specific release
- `POST /webhook/github` - GitHub webhook
- `POST /analyze/{version}` - Force analysis

## Configuration

Edit `config.yaml`:

```yaml
github:
  check_interval_hours: 2  # Monitoring frequency
  
slack:
  channels:
    releases: "#rancher-releases"
    critical: "#rancher-critical"
```

## Troubleshooting

**Bot not starting:**
```bash
# Check environment
cat .env | grep -v "^#"

# Verify Python version
python --version  # Should be 3.9+
```

**Slack commands not working:**
- Verify Request URL in Slack app settings
- Check bot is invited to channels
- Confirm slash commands are configured

## Support

- GitHub Issues: [https://github.com/rancher/rancher]
- Slack: #rancher-bot-support


