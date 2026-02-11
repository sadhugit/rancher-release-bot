"""
Rancher Release Intelligence Bot - Main Application
FastAPI application that orchestrates all components
"""

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
import uvicorn
import asyncio
from datetime import datetime

# Import our modules
from github_monitor import RancherMonitor
from ai_analyzer import AIAnalyzer
from slack_bot import SlackBot
from database import Database
from integrations import IntegrationManager
from config import load_config

# Global instances
config = load_config()
db = Database(config['database'])
monitor = RancherMonitor(config['github'], db)
ai_analyzer = AIAnalyzer(config['gemini'], db)
slack_bot = SlackBot(config['slack'], db, ai_analyzer)
integrations = IntegrationManager(config['integrations'], db)

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("🚀 Starting Rancher Release Intelligence Bot...")
    
    # Initialize database
    await db.init_db()
    
    # Initialize Slack bot (no separate server)
    await slack_bot.start()
    
    # Schedule monitoring job
    scheduler.add_job(
        monitor_and_process,
        'interval',
        hours=config['github']['check_interval_hours'],
        id='rancher_monitor',
        replace_existing=True
    )
    scheduler.start()
    
    # Run initial check
    asyncio.create_task(monitor_and_process())
    
    print("✅ Bot is running!")
    print(f"📊 Dashboard: http://localhost:8000")
    print(f"💬 Slack commands: /rancher-release, /rancher-compare, /rancher-search")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down...")
    scheduler.shutdown()
    await slack_bot.stop()
    await db.close()

app = FastAPI(
    title="Rancher Release Bot",
    description="AI-powered Rancher release monitoring and analysis",
    version="1.0.0",
    lifespan=lifespan
)

async def monitor_and_process():
    """Main monitoring workflow"""
    try:
        print(f"🔍 Checking for new releases... [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        
        # Check GitHub for new releases
        new_releases = await monitor.check_for_new_releases()
        
        if not new_releases:
            print("✓ No new releases found")
            return
        
        for release in new_releases:
            version = release['tag_name']
            print(f"🆕 Processing new release: {version}")
            
            # AI Analysis
            print(f"🤖 Analyzing {version} with Claude AI...")
            analysis = await ai_analyzer.analyze_release(release)
            
            # Store in database
            await db.store_release(version, release, analysis)
            print(f"💾 Stored {version} in database")
            
            # Send Slack notification
            print(f"📢 Sending Slack notification for {version}...")
            await slack_bot.notify_new_release(version, analysis)
            
            # Create tickets if critical
            if analysis.get('severity') == 'critical':
                print(f"🎫 Creating ticket for critical release {version}...")
                await integrations.create_ticket(version, analysis)
            
            print(f"✅ Successfully processed {version}")
            print("-" * 60)
            
    except Exception as e:
        print(f"❌ Error in monitoring: {e}")
        import traceback
        traceback.print_exc()
        await slack_bot.notify_error(str(e))

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Rancher Release Bot",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "health": "/",
            "releases": "/releases",
            "release_detail": "/releases/{version}",
            "webhook": "/webhook/github",
            "force_analyze": "/analyze/{version}"
        }
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        # Check database
        releases_count = len(await db.get_all_releases())
        
        return JSONResponse(content={
            "status": "healthy",
            "database": "connected",
            "releases_tracked": releases_count,
            "slack_bot": "running",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )

@app.get("/releases")
async def list_releases():
    """List all tracked releases"""
    try:
        releases = await db.get_all_releases()
        return JSONResponse(content={
            "count": len(releases),
            "releases": releases
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/releases/{version}")
async def get_release(version: str):
    """Get details for a specific release"""
    try:
        release = await db.get_release(version)
        if not release:
            return JSONResponse(
                status_code=404,
                content={"error": f"Release {version} not found"}
            )
        return JSONResponse(content=release)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/webhook/github")
async def github_webhook(background_tasks: BackgroundTasks):
    """GitHub webhook endpoint for instant notifications"""
    print("📨 Received GitHub webhook - triggering release check")
    background_tasks.add_task(monitor_and_process)
    return {"status": "processing", "message": "Release check triggered"}

@app.post("/analyze/{version}")
async def force_analyze(version: str):
    """Force re-analysis of a specific version"""
    try:
        print(f"🔄 Force analyzing {version}...")
        
        # Fetch from GitHub
        release = await monitor.fetch_release(version)
        if not release:
            return JSONResponse(
                status_code=404,
                content={"error": f"Version {version} not found on GitHub"}
            )
        
        # Analyze with AI
        analysis = await ai_analyzer.analyze_release(release)
        
        # Store
        await db.store_release(version, release, analysis)
        
        print(f"✅ Successfully re-analyzed {version}")
        
        return JSONResponse(content={
            "status": "success",
            "version": version,
            "analysis": analysis
        })
    except Exception as e:
        print(f"❌ Error analyzing {version}: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/stats")
async def get_stats():
    """Get bot statistics"""
    try:
        releases = await db.get_all_releases()
        
        # Calculate stats
        total = len(releases)
        critical = sum(1 for r in releases if r.get('analysis', {}).get('severity') == 'critical')
        
        return JSONResponse(content={
            "total_releases": total,
            "critical_releases": critical,
            "latest_release": releases[0] if releases else None,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/slack/events")
async def slack_events(req: Request):
    """Handle Slack events and commands"""
    return await slack_bot.get_fastapi_handler().handle(req)

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║         Rancher Release Intelligence Bot v1.0.0             ║
    ║                   AI-Powered Release Monitoring              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )