"""
Slack bot integration
Handles slash commands and notifications
FIXED: Event loop compatibility with FastAPI
"""

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from typing import Dict
import asyncio

class SlackBot:
    def __init__(self, config: dict, db, ai_analyzer):
        self.config = config
        self.db = db
        self.ai = ai_analyzer
        
        self.app = AsyncApp(
            token=config['bot_token'],
            signing_secret=config['signing_secret']
        )
        
        # Create FastAPI handler
        self.handler = AsyncSlackRequestHandler(self.app)
        
        self._setup_commands()
    
    def _setup_commands(self):
        """Setup Slack command handlers"""
        
        @self.app.command("/rancher-release")
        async def handle_release(ack, command, say):
            await ack()
            
            version = command.get('text', '').strip() or 'latest'
            
            print(f"📝 Slack command: /rancher-release {version}")
            
            if version == 'latest':
                release = await self.db.get_latest_release()
            else:
                release = await self.db.get_release(version)
            
            if not release:
                await say(f"❌ Release `{version}` not found in database.\n"
                         f"Try `/rancher-release latest` or check available versions.")
                return
            
            blocks = self._format_release_blocks(release)
            await say(blocks=blocks)
        
        @self.app.command("/rancher-compare")
        async def handle_compare(ack, command, say):
            await ack()
            
            versions = command['text'].strip().split()
            
            if len(versions) != 2:
                await say(
                    "❌ *Usage:* `/rancher-compare <version1> <version2>`\n"
                    "*Example:* `/rancher-compare v2.12.0 v2.13.0`"
                )
                return
            
            print(f"📊 Slack command: /rancher-compare {versions[0]} {versions[1]}")
            
            # Show loading message
            await say(f"⏳ Comparing {versions[0]} and {versions[1]}...")
            
            comparison = await self.ai.compare_versions(versions[0], versions[1])
            blocks = self._format_comparison_blocks(comparison, versions[0], versions[1])
            await say(blocks=blocks)
        
        @self.app.command("/rancher-search")
        async def handle_search(ack, command, say):
            await ack()
            
            query = command['text'].strip()
            
            if not query:
                await say(
                    "❌ *Usage:* `/rancher-search <keyword>`\n"
                    "*Example:* `/rancher-search security` or `/rancher-search v2.13`"
                )
                return
            
            print(f"🔍 Slack command: /rancher-search {query}")
            
            results = await self.db.search_releases(query)
            
            if not results:
                await say(f"❌ No releases found matching: `{query}`")
                return
            
            blocks = self._format_search_results(results, query)
            await say(blocks=blocks)
        
        @self.app.event("app_mention")
        async def handle_mention(event, say):
            """Handle @mentions of the bot"""
            text = event.get('text', '').lower()
            
            if 'latest' in text:
                release = await self.db.get_latest_release()
                if release:
                    blocks = self._format_release_blocks(release)
                    await say(blocks=blocks)
            elif 'help' in text:
                await say(self._get_help_message())
            else:
                await say(
                    "👋 Hi! I'm the Rancher Release Bot.\n"
                    "Try `/rancher-release latest` or `/rancher-search <keyword>`\n"
                    "Type `@Rancher Bot help` for more commands."
                )
    
    async def start(self):
        """Start the Slack bot - FIXED for FastAPI compatibility"""
        # Don't start a separate server - FastAPI will handle it
        print("✅ Slack bot initialized (will use FastAPI endpoints)")
    
    async def stop(self):
        """Stop the Slack bot"""
        # No separate server to stop
        pass
    
    def get_fastapi_handler(self):
        """Get the FastAPI handler for Slack events"""
        return self.handler
    
    async def notify_new_release(self, version: str, analysis: Dict):
        """Send notification about new release"""
        
        severity = analysis.get('severity', 'normal')
        
        # Determine channel based on severity
        if severity == 'critical':
            channel = self.config['channels']['critical']
            emoji = "🚨"
            prefix = "CRITICAL"
        elif severity == 'important':
            channel = self.config['channels']['releases']
            emoji = "⚠️"
            prefix = "IMPORTANT"
        else:
            channel = self.config['channels']['releases']
            emoji = "📦"
            prefix = "NEW RELEASE"
        
        blocks = self._format_release_blocks({
            'version': version,
            'analysis': analysis
        }, is_notification=True)
        
        text = f"{emoji} {prefix}: Rancher {version}"
        
        try:
            await self.app.client.chat_postMessage(
                channel=channel,
                blocks=blocks,
                text=text
            )
            
            # Record notification
            await self.db.record_notification(version, channel)
            
            print(f"✅ Sent notification to {channel}")
            
        except Exception as e:
            print(f"❌ Failed to send Slack notification: {e}")
    
    async def notify_error(self, error: str):
        """Notify about errors"""
        try:
            await self.app.client.chat_postMessage(
                channel=self.config['channels']['team'],
                text=f"⚠️ *Rancher Bot Error*\n```{error}```"
            )
        except Exception as e:
            print(f"❌ Failed to send error notification: {e}")
    
    def _format_release_blocks(
        self, 
        release: Dict, 
        is_notification: bool = False
    ) -> list:
        """Format release data as Slack blocks"""
        
        analysis = release.get('analysis', {})
        version = release.get('version', 'Unknown')
        severity = analysis.get('severity', 'normal')
        
        # Header with severity indicator
        severity_emoji = {
            'critical': '🚨',
            'important': '⚠️',
            'normal': '📦',
            'low': 'ℹ️'
        }
        
        emoji = severity_emoji.get(severity, '📦')
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Rancher {version}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Type:* {analysis.get('release_type', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:* {severity.title()}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary:*\n{analysis.get('summary', 'No summary available')}"
                }
            },
            {"type": "divider"}
        ]
        
        # New Features
        features = analysis.get('new_features', [])
        if features:
            features_text = "\n\n".join([
                f"*{i+1}. {f['title']}*\n{f.get('description', '')}"
                for i, f in enumerate(features[:3])
            ])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🎉 New Features:*\n{features_text}"
                }
            })
        
        # Critical Bug Fixes
        bugs = analysis.get('bug_fixes', [])
        critical_bugs = [b for b in bugs if b.get('severity') in ['critical', 'high']]
        if critical_bugs:
            bugs_text = "\n".join([
                f"• {b['issue']}"
                for b in critical_bugs[:3]
            ])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🐛 Critical Bug Fixes:*\n{bugs_text}"
                }
            })
        
        # Breaking Changes
        breaking = analysis.get('breaking_changes', [])
        if breaking:
            breaking_text = "\n\n".join([
                f"*{b['change']}*\n_{b.get('impact', 'N/A')}_"
                for b in breaking[:2]
            ])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*⚠️ Breaking Changes:*\n{breaking_text}"
                }
            })
        
        # Security Updates
        security = analysis.get('security_updates', [])
        if security:
            security_text = "\n".join([
                f"• *{s.get('severity', 'unknown').upper()}:* {s.get('description', 'N/A')}"
                for s in security[:3]
            ])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🔒 Security Updates:*\n{security_text}"
                }
            })
        
        # Recommended Actions
        actions = analysis.get('recommended_actions', [])
        if actions:
            actions_text = "\n".join([
                f"{i+1}. {a}" 
                for i, a in enumerate(actions[:5])
            ])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*📋 Recommended Actions:*\n{actions_text}"
                }
            })
        
        # Resources
        resources = analysis.get('resources', {})
        if resources and not resources.get('error'):
            docs = resources.get('documentation', [])[:2]
            videos = resources.get('videos', [])[:2]
            
            resource_lines = []
            for doc in docs:
                resource_lines.append(f"• <{doc['url']}|{doc['title']}>")
            for video in videos:
                resource_lines.append(f"• 🎥 <{video['url']}|{video['title']}>")
            
            if resource_lines:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📚 Resources:*\n" + "\n".join(resource_lines)
                    }
                })
        
        return blocks
    
    def _format_comparison_blocks(
        self, 
        comparison: Dict, 
        version1: str, 
        version2: str
    ) -> list:
        """Format version comparison as Slack blocks"""
        
        if 'error' in comparison:
            return [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"❌ *Error:* {comparison['error']}"
                    }
                }
            ]
        
        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 Comparison: {version1} → {version2}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary:*\n{comparison.get('summary', 'No summary available')}"
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Complexity:*\n{comparison.get('upgrade_complexity', 'Unknown').title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Risk Level:*\n{comparison.get('risk_level', 'Unknown').title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Estimated Time:*\n{comparison.get('migration_time', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Breaking Changes:*\n{comparison.get('breaking_changes_count', 0)}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommended Path:*\n{comparison.get('recommended_path', 'Not specified')}"
                }
            }
        ]
    
    def _format_search_results(self, results: list, query: str) -> list:
        """Format search results as Slack blocks"""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔍 Found {len(results)} releases matching '{query}'"
                }
            }
        ]
        
        for r in results[:10]:
            severity_emoji = {
                'critical': '🚨',
                'important': '⚠️',
                'normal': '📦',
                'low': 'ℹ️'
            }
            emoji = severity_emoji.get(r.get('severity', 'normal'), '📦')
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{r['version']}*\n_{r.get('summary', 'No summary')[:150]}_"
                }
            })
        
        if len(results) > 10:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_Showing first 10 of {len(results)} results_"
                    }
                ]
            })
        
        return blocks
    
    def _get_help_message(self) -> str:
        """Get help message"""
        return """*Rancher Release Bot - Commands*

*Available Commands:*
• `/rancher-release latest` - Get the latest release
• `/rancher-release <version>` - Get specific version details
• `/rancher-compare <v1> <v2>` - Compare two versions
• `/rancher-search <keyword>` - Search releases

*Examples:*
• `/rancher-release v2.13.0`
• `/rancher-compare v2.12.0 v2.13.0`
• `/rancher-search security`

*Notifications:*
• Critical releases → #rancher-critical
• Normal releases → #rancher-releases

*Need help?* Contact your DevOps team."""