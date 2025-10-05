# 🤖 AI-Powered Email Support Agent

An intelligent customer support email system powered by Claude AI (Sonnet 4.5) that automatically classifies, processes, and generates replies to customer support emails.

## ✨ Features

- **Automatic Email Fetching** - Connects to your email via IMAP
- **AI Classification** - Categorizes emails (billing, technical, sales, etc.)
- **Smart Reply Generation** - AI generates contextual responses
- **Human-in-the-Loop** - Review and approve AI suggestions before sending
- **Escalation Management** - Automatically flags complex issues
- **Analytics Dashboard** - Track performance, automation rate, time saved
- **RESTful API** - Full API for integrations
- **Real-time Processing** - Celery-powered async processing

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional)

### Option 1: Docker (Recommended)
```bash
# Clone repository
git clone <your-repo>
cd email_support_agent

# Copy environment file
cp .env.example .env

# Edit .env with your credentials
nano .env

# Start services
docker-compose up -d

# Access the application
# Dashboard: http://localhost:8000
# Admin: http://localhost:8000/admin (admin/admin123)
# API Docs: http://localhost:8000/api/docs/
# Flower (Celery): http://localhost:5555