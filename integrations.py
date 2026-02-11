"""
External integrations (Jira, ServiceNow, etc.)
Creates tickets and manages external system updates
"""

from typing import Dict
import aiohttp
import json
from datetime import datetime

class IntegrationManager:
    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
    
    async def create_ticket(self, version: str, analysis: Dict):
        """Create ticket in configured systems for critical releases"""
        
        # Try Jira first
        if self.config.get('jira', {}).get('enabled'):
            await self._create_jira_ticket(version, analysis)
        
        # Try ServiceNow
        if self.config.get('servicenow', {}).get('enabled'):
            await self._create_servicenow_ticket(version, analysis)
    
    async def _create_jira_ticket(self, version: str, analysis: Dict):
        """Create Jira ticket for release"""
        
        jira_config = self.config['jira']
        
        # Build ticket summary
        summary = f"Rancher {version} - {analysis.get('severity', 'Normal').title()} Release"
        
        # Build description
        description = self._build_ticket_description(version, analysis)
        
        # Jira API payload
        payload = {
            "fields": {
                "project": {
                    "key": jira_config['project_key']
                },
                "summary": summary,
                "description": description,
                "issuetype": {
                    "name": "Task"
                },
                "priority": {
                    "name": self._get_jira_priority(analysis.get('severity', 'normal'))
                },
                "labels": [
                    "rancher",
                    "release",
                    version,
                    analysis.get('severity', 'normal')
                ]
            }
        }
        
        # API call
        url = f"{jira_config['url']}/rest/api/2/issue"
        auth = aiohttp.BasicAuth(
            jira_config['email'],
            jira_config['api_token']
        )
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    auth=auth,
                    headers={'Content-Type': 'application/json'}
                ) as resp:
                    if resp.status == 201:
                        result = await resp.json()
                        ticket_key = result['key']
                        print(f"✅ Created Jira ticket: {ticket_key}")
                        return ticket_key
                    else:
                        error_text = await resp.text()
                        print(f"❌ Failed to create Jira ticket: {resp.status}")
                        print(f"   Error: {error_text}")
        except Exception as e:
            print(f"❌ Jira integration error: {e}")
        
        return None
    
    async def _create_servicenow_ticket(self, version: str, analysis: Dict):
        """Create ServiceNow ticket for release"""
        
        snow_config = self.config['servicenow']
        
        # Build ticket payload
        payload = {
            "short_description": f"Rancher {version} Release - Action Required",
            "description": self._build_ticket_description(version, analysis),
            "urgency": self._get_snow_urgency(analysis.get('severity', 'normal')),
            "impact": self._get_snow_impact(analysis.get('severity', 'normal')),
            "category": "Software",
            "subcategory": "Infrastructure"
        }
        
        # API call
        url = f"https://{snow_config['instance']}/api/now/table/incident"
        auth = aiohttp.BasicAuth(
            snow_config['username'],
            snow_config['password']
        )
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    auth=auth,
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                ) as resp:
                    if resp.status == 201:
                        result = await resp.json()
                        ticket_number = result['result']['number']
                        print(f"✅ Created ServiceNow ticket: {ticket_number}")
                        return ticket_number
                    else:
                        print(f"❌ Failed to create ServiceNow ticket: {resp.status}")
        except Exception as e:
            print(f"❌ ServiceNow integration error: {e}")
        
        return None
    
    def _build_ticket_description(self, version: str, analysis: Dict) -> str:
        """Build ticket description from analysis"""
        
        description = f"""Rancher {version} has been released.

SEVERITY: {analysis.get('severity', 'Normal').upper()}
TYPE: {analysis.get('release_type', 'Unknown').title()}

SUMMARY:
{analysis.get('summary', 'No summary available')}

NEW FEATURES:
"""
        
        # Add features
        features = analysis.get('new_features', [])
        for i, feature in enumerate(features[:5], 1):
            description += f"\n{i}. {feature['title']}\n   {feature.get('description', '')}\n"
        
        # Add breaking changes
        breaking = analysis.get('breaking_changes', [])
        if breaking:
            description += "\n\nBREAKING CHANGES:\n"
            for change in breaking[:3]:
                description += f"\n- {change['change']}\n  Impact: {change.get('impact', 'N/A')}\n"
        
        # Add security updates
        security = analysis.get('security_updates', [])
        if security:
            description += "\n\nSECURITY UPDATES:\n"
            for sec in security[:3]:
                description += f"\n- {sec.get('description', 'N/A')}\n"
        
        # Add recommended actions
        actions = analysis.get('recommended_actions', [])
        if actions:
            description += "\n\nRECOMMENDED ACTIONS:\n"
            for i, action in enumerate(actions[:5], 1):
                description += f"{i}. {action}\n"
        
        # Add upgrade notes
        upgrade_notes = analysis.get('upgrade_notes', {})
        if upgrade_notes:
            description += f"\n\nUPGRADE NOTES:\n"
            description += f"Estimated Downtime: {upgrade_notes.get('estimated_downtime', 'Unknown')}\n"
            
            known_issues = upgrade_notes.get('known_issues', [])
            if known_issues:
                description += "\nKnown Issues:\n"
                for issue in known_issues[:3]:
                    description += f"- {issue}\n"
        
        description += f"\n\nCreated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        description += f"\nSource: Rancher Release Bot"
        
        return description
    
    def _get_jira_priority(self, severity: str) -> str:
        """Map severity to Jira priority"""
        mapping = {
            'critical': 'Highest',
            'important': 'High',
            'normal': 'Medium',
            'low': 'Low'
        }
        return mapping.get(severity, 'Medium')
    
    def _get_snow_urgency(self, severity: str) -> str:
        """Map severity to ServiceNow urgency"""
        mapping = {
            'critical': '1',  # High
            'important': '2',  # Medium
            'normal': '3',     # Low
            'low': '3'
        }
        return mapping.get(severity, '3')
    
    def _get_snow_impact(self, severity: str) -> str:
        """Map severity to ServiceNow impact"""
        mapping = {
            'critical': '1',  # High - affects multiple users/systems
            'important': '2',  # Medium - affects department
            'normal': '3',     # Low - affects individual
            'low': '3'
        }
        return mapping.get(severity, '3')
    
    async def send_email_notification(
        self, 
        version: str, 
        analysis: Dict,
        recipients: list
    ):
        """Send email notification (placeholder for email integration)"""
        
        # This would integrate with your email service (SendGrid, SES, etc.)
        print(f"📧 Email notification for {version} to {len(recipients)} recipients")
        print(f"   (Email integration not implemented - add your SMTP/API here)")
        
        # Example implementation with SMTP would go here
        # import smtplib
        # from email.mime.text import MIMEText
        # ...
    
    async def create_github_issue(
        self, 
        version: str, 
        analysis: Dict
    ):
        """Create GitHub issue for tracking (optional)"""
        
        # Could create an issue in your internal tracking repo
        print(f"📝 Would create GitHub issue for {version}")
        # Implementation depends on your GitHub setup
    
    async def post_to_webhook(
        self, 
        webhook_url: str, 
        version: str, 
        analysis: Dict
    ):
        """Post to generic webhook (Teams, Discord, etc.)"""
        
        payload = {
            "version": version,
            "severity": analysis.get('severity'),
            "summary": analysis.get('summary'),
            "url": f"https://github.com/rancher/rancher/releases/tag/{version}"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                ) as resp:
                    if resp.status == 200:
                        print(f"✅ Posted to webhook: {webhook_url}")
                    else:
                        print(f"❌ Webhook failed: {resp.status}")
        except Exception as e:
            print(f"❌ Webhook error: {e}")