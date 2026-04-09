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

config = load_config()
db = Database(config['database'])
monitor = RancherMonitor(config['github'], db)
ai_analyzer = AIAnalyzer(config['gemini'], db)
slack_bot = SlackBot(config['slack'], db, ai_analyzer)
integrations = IntegrationManager(config['integrations'], db)

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Rancher Release Intelligence Bot...")
    
    await db.init_db()
    await slack_bot.start()
    
    scheduler.add_job(
        monitor_and_process,
        'interval',
        hours=config['github']['check_interval_hours'],
        id='rancher_monitor',
        replace_existing=True
    )
    scheduler.start()
    
    asyncio.create_task(monitor_and_process())
    
    print("✅ Bot is running!")
    print(f"📊 Dashboard: http://localhost:8000")
    print(f"💬 Slack commands: /rancher-release, /rancher-compare, /rancher-search")
    
    yield
    
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
    """
    Main monitoring workflow.
    Runs on schedule. For each release from GitHub:
      - Already in DB → skip entirely (no AI, no reprocessing)
      - Not in DB     → analyze with Gemini → store → notify Slack
    """
    try:
        print(f"🔍 Checking for new releases... [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        
        new_releases = await monitor.check_for_new_releases()
        
        if not new_releases:
            print("✓ No new releases found")
            return
        
        for release in new_releases:
            version = release['tag_name']

            # ✅ Already in DB — skip completely, no AI involved
            if await db.release_exists(version):
                print(f"✓ {version} already in DB — skipping")
                continue

            # Genuinely new — process it
            print(f"🆕 New release: {version}")
            print(f"🤖 Analyzing {version} with Gemini...")
            analysis = await ai_analyzer.analyze_release(release)
            
            await db.store_release(version, release, analysis)
            print(f"💾 Stored {version} in database")
            
            print(f"📢 Sending Slack notification for {version}...")
            await slack_bot.notify_new_release(version, analysis)
            
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
    return {
        "service": "Rancher Release Bot",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "health": "/health",
            "releases": "/releases",
            "release_detail": "/releases/{version}",
            "webhook": "/webhook/github",
            "force_analyze": "/analyze/{version}",
            "scheduler": "/scheduler/status"
        }
    }

@app.get("/health")
async def health_check():
    try:
        releases_count = len(await db.get_all_releases())
        return JSONResponse(content={
            "status": "healthy",
            "database": "connected",
            "releases_tracked": releases_count,
            "slack_bot": "running",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})

@app.get("/releases")
async def list_releases():
    try:
        releases = await db.get_all_releases()
        return JSONResponse(content={"count": len(releases), "releases": releases})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/releases/{version}")
async def get_release(version: str):
    try:
        release = await db.get_release(version)
        if not release:
            return JSONResponse(status_code=404, content={"error": f"Release {version} not found"})
        return JSONResponse(content=release)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/webhook/github")
async def github_webhook(background_tasks: BackgroundTasks):
    """GitHub webhook — instant trigger when a new release is published"""
    print("📨 Received GitHub webhook - triggering release check")
    background_tasks.add_task(monitor_and_process)
    return {"status": "processing", "message": "Release check triggered"}

@app.post("/analyze/{version}")
async def force_analyze(version: str):
    """
    Force analyze a specific version.
    ✅ Checks DB first — if already stored, returns from DB with no Gemini call.
    Use this for versions the scheduled job may have missed.
    """
    try:
        # ✅ DB-first even on manual trigger
        existing = await db.get_release(version)
        if existing:
            print(f"✓ {version} already in DB — returning stored analysis")
            return JSONResponse(content={
                "status": "from_db",
                "version": version,
                "analysis": existing['analysis']
            })

        print(f"🔄 Force analyzing {version} — not in DB...")
        release = await monitor.fetch_release(version)
        if not release:
            return JSONResponse(status_code=404, content={"error": f"Version {version} not found on GitHub"})

        analysis = await ai_analyzer.analyze_release(release)
        await db.store_release(version, release, analysis)

        print(f"✅ {version} analyzed and stored")
        return JSONResponse(content={"status": "analyzed", "version": version, "analysis": analysis})

    except Exception as e:
        print(f"❌ Error analyzing {version}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/stats")
async def get_stats():
    try:
        stats = await db.get_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# @app.post("/slack/events")
# async def slack_events(req: Request):
#     return await slack_bot.get_fastapi_handler().handle(req)


@app.get("/scheduler/status")
async def scheduler_status():
    jobs = scheduler.get_jobs()
    return JSONResponse(content={
        "jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
            for job in jobs
        ]
    })

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║         Rancher Release Intelligence Bot v1.0.0             ║
    ║                   AI-Powered Release Monitoring              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
    