"""
AI-powered analysis using Google Gemini API
Clean, complete, tested version
"""

import google.generativeai as genai
import json
from typing import Dict
import re

class AIAnalyzer:
    def __init__(self, config: dict, db):
        self.config = config
        self.db = db
        
        # Configure Gemini
        genai.configure(api_key=config['api_key'])
        
        # Use Gemini model
        self.model = genai.GenerativeModel(config.get('model', 'gemini-pro'))
        self.max_tokens = config.get('max_tokens', 4000)
    
    async def analyze_release(self, release: Dict) -> Dict:
        """Main analysis function using Gemini"""
        
        version = release['tag_name']
        release_notes = release.get('body', '')
        build_yaml = release.get('build_yaml', '')
        changelog = release.get('changelog', '')
        
        print(f"  🤖 Sending to Gemini for analysis...")
        
        # Construct prompt
        prompt = self._build_analysis_prompt(version, release_notes, build_yaml, changelog)
        
        try:
            # Call Gemini API
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=0.7,
                )
            )
            
            # Parse response
            analysis_text = response.text
            analysis = self._parse_json_response(analysis_text)
            
            print(f"  ✓ Analysis complete for {version}")
            
            # Add resources
            analysis['resources'] = await self._find_resources(version, analysis)
            
            return analysis
            
        except Exception as e:
            print(f"  ❌ Gemini API error: {e}")
            return self._create_error_response(version, str(e))
    
    def _build_analysis_prompt(self, version: str, notes: str, build_yaml: str, changelog: str) -> str:
        """Build analysis prompt for Gemini"""
        
        return f"""You are a DevOps analyst. Analyze Rancher release {version}.

RELEASE NOTES:
{notes[:2500] if notes else 'Not available'}

BUILD CONFIG:
{build_yaml[:800] if build_yaml else 'Not available'}

Return ONLY valid JSON (no markdown, no extra text):

{{
  "version": "{version}",
  "release_type": "major|minor|patch",
  "severity": "critical|important|normal|low",
  "summary": "2-3 sentence overview in simple terms",
  "new_features": [
    {{
      "title": "Feature name",
      "description": "Simple explanation (max 150 chars)",
      "impact": "How this affects deployments"
    }}
  ],
  "bug_fixes": [
    {{
      "issue": "What was fixed",
      "severity": "critical|high|medium|low",
      "description": "Impact and resolution"
    }}
  ],
  "breaking_changes": [
    {{
      "change": "What changed",
      "impact": "Who is affected",
      "migration_steps": "How to adapt"
    }}
  ],
  "security_updates": [
    {{
      "severity": "critical|high|medium|low",
      "description": "What was fixed",
      "recommendation": "Action required"
    }}
  ],
  "recommended_actions": [
    "Action 1",
    "Action 2",
    "Action 3"
  ],
  "upgrade_notes": {{
    "prerequisites": ["What to check before upgrading"],
    "known_issues": ["List of known issues"],
    "estimated_downtime": "Expected downtime"
  }}
}}

Keep descriptions concise. Include top 5 items per category. Respond with valid JSON only."""

    def _parse_json_response(self, text: str) -> Dict:
        """Parse Gemini's JSON response with error handling"""
        try:
            # Clean up response
            text = text.strip()
            
            # Remove markdown code blocks
            text = re.sub(r'```json\n?', '', text)
            text = re.sub(r'```\n?', '', text)
            text = text.strip()
            
            # Parse JSON
            analysis = json.loads(text)
            return analysis
            
        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON parsing error: {e}")
            
            # Try to fix common issues
            try:
                # Remove trailing incomplete content
                if not text.endswith('}'):
                    # Find last complete closing brace
                    last_brace = text.rfind('}')
                    if last_brace > 0:
                        text = text[:last_brace + 1]
                
                # Try parsing again
                analysis = json.loads(text)
                print(f"  ✓ Fixed and parsed JSON")
                return analysis
                
            except Exception as fix_error:
                print(f"  ❌ Could not fix JSON: {fix_error}")
                print(f"  Raw response (first 500 chars): {text[:500]}")
                
                # Return minimal structure
                return {
                    "version": "unknown",
                    "release_type": "unknown",
                    "severity": "normal",
                    "summary": "Failed to parse analysis. Please check logs.",
                    "new_features": [],
                    "bug_fixes": [],
                    "breaking_changes": [],
                    "security_updates": [],
                    "recommended_actions": ["Review release manually"],
                    "upgrade_notes": {
                        "prerequisites": [],
                        "known_issues": [],
                        "estimated_downtime": "Unknown"
                    },
                    "error": str(e)
                }
    
    async def _find_resources(self, version: str, analysis: Dict) -> Dict:
        """Find relevant resources using Gemini"""
        
        features = [f.get('title', '') for f in analysis.get('new_features', [])[:3]]
        features_str = ', '.join(features) if features else 'general'
        
        prompt = f"""Find resources for Rancher {version} focusing on: {features_str}

Return ONLY valid JSON:
{{
  "documentation": [
    {{"title": "Doc title", "url": "https://...", "description": "Brief"}}
  ],
  "kb_articles": [
    {{"title": "Article title", "url": "https://...", "summary": "Brief"}}
  ],
  "videos": [
    {{"title": "Video title", "url": "https://youtube.com/...", "channel": "Channel name"}}
  ]
}}

Include top 3 items per category. Valid JSON only."""
        
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=1500,
                    temperature=0.7,
                )
            )
            
            resources = self._parse_json_response(response.text)
            
            doc_count = len(resources.get('documentation', []))
            video_count = len(resources.get('videos', []))
            print(f"  ✓ Found {doc_count} docs, {video_count} videos")
            
            return resources
            
        except Exception as e:
            print(f"  ⚠️  Failed to fetch resources: {e}")
            return {
                "documentation": [],
                "kb_articles": [],
                "videos": []
            }
    
    async def compare_versions(self, version1: str, version2: str) -> Dict:
        """Compare two Rancher versions using Gemini"""
        
        print(f"🔄 Comparing {version1} vs {version2}...")
        
        # Get both releases from database
        release1 = await self.db.get_release(version1)
        release2 = await self.db.get_release(version2)
        
        if not release1 or not release2:
            missing = []
            if not release1:
                missing.append(version1)
            if not release2:
                missing.append(version2)
            return {
                "error": f"Version(s) not found: {', '.join(missing)}",
                "summary": "Cannot compare - versions not in database"
            }
        
        # Build comparison prompt
        analysis1 = release1.get('analysis', {})
        analysis2 = release2.get('analysis', {})
        
        prompt = f"""Compare Rancher {version1} vs {version2}.

VERSION {version1}:
Summary: {analysis1.get('summary', 'N/A')[:200]}
Features: {len(analysis1.get('new_features', []))}
Severity: {analysis1.get('severity', 'unknown')}

VERSION {version2}:
Summary: {analysis2.get('summary', 'N/A')[:200]}
Features: {len(analysis2.get('new_features', []))}
Severity: {analysis2.get('severity', 'unknown')}

Return ONLY valid JSON:
{{
  "summary": "Brief comparison overview (2-3 sentences)",
  "major_changes": ["Change 1", "Change 2", "Change 3"],
  "upgrade_complexity": "easy|moderate|complex",
  "recommended_path": "Direct upgrade or step-by-step",
  "migration_time": "Estimated time",
  "breaking_changes_count": 0,
  "risk_level": "low|medium|high"
}}"""
        
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=1000,
                    temperature=0.7,
                )
            )
            
            comparison = self._parse_json_response(response.text)
            print(f"✓ Comparison complete")
            
            return comparison
            
        except Exception as e:
            print(f"❌ Comparison failed: {e}")
            return {
                "error": str(e),
                "summary": "Failed to generate comparison"
            }
    
    def _create_error_response(self, version: str, error: str) -> Dict:
        """Create error response structure"""
        return {
            "version": version,
            "error": error,
            "summary": "Analysis failed due to error",
            "severity": "unknown",
            "release_type": "unknown",
            "new_features": [],
            "bug_fixes": [],
            "breaking_changes": [],
            "security_updates": [],
            "recommended_actions": ["Check logs for error details", "Review release manually"],
            "upgrade_notes": {
                "prerequisites": [],
                "known_issues": [],
                "estimated_downtime": "Unknown"
            },
            "resources": {
                "documentation": [],
                "kb_articles": [],
                "videos": []
            }
        }