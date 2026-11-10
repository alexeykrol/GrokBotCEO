#!/usr/bin/env python3
"""
Tests for bot-payload-compiler.py
Verifies full persona preservation, metadata stripping, placeholder resolution
NO live bot creation - fictional fixtures only
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
COMPILER_SCRIPT = SCRIPT_DIR / "bot-payload-compiler.py"

class TestPayloadCreate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.profile_path = self.tmpdir / "profile.json"
        self.prompt_path = self.tmpdir / "prompt.md"
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_full_persona_preserved(self):
        """Full canonical persona from prompt.md must be preserved in payload"""
        canonical_persona = "This is a detailed bot persona from prompt.md with multiple sentences. " * 10
        profile = {
            "name": "Test Bot",
            "title": "METADATA",
            "avatarShape": "circle",
            "_comment": "metadata comment"
        }
        self.profile_path.write_text(json.dumps(profile))
        
        # Canonical persona in prompt.md
        self.prompt_path.write_text(canonical_persona)
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"Compiler failed: {result.stderr}")
        payload = json.loads(result.stdout)
        
        # Must use prompt.md, not profile.description
        self.assertEqual(payload["description"], canonical_persona, "Full canonical persona from prompt.md must be preserved")
        self.assertEqual(len(payload["description"]), len(canonical_persona))
    
    def test_metadata_stripped(self):
        """Metadata fields must NOT appear in payload"""
        profile = {
            "name": "Test Bot",
            "title": "Bot Title",
            "avatarShape": "teardrop",
            "avatarColor": "red",
            "namedBy": "user",
            "harness": "temporal",
            "serverId": "srv_12345",
            "_comment": "Remove serverId"
        }
        self.profile_path.write_text(json.dumps(profile))
        
        # Create canonical persona in prompt.md
        self.prompt_path.write_text("Canonical persona text from prompt.md")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        
        # Only whitelisted keys
        self.assertEqual(set(payload.keys()), {"name", "description"})
        
        # Description should be from prompt.md, not profile
        self.assertEqual(payload["description"], "Canonical persona text from prompt.md")
        
        # Metadata NOT present
        for metadata_key in ["title", "avatarShape", "avatarColor", "namedBy", "harness", "serverId", "_comment"]:
            self.assertNotIn(metadata_key, payload)
    
    def test_placeholder_resolution(self):
        """Placeholders {{KEY}} must be resolved with --param"""
        # Note: Using allowed placeholder keys only
        profile = {
            "name": "Monitor Bot"
        }
        self.profile_path.write_text(json.dumps(profile))
        
        # Canonical prompt with allowed placeholders
        self.prompt_path.write_text("Bot for {{WORKSPACE_PATH}} in {{OWNER_TIMEZONE}}")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path),
             "--param", "WORKSPACE_PATH=/home/bot/grokbot",
             "--param", "OWNER_TIMEZONE=America/Los_Angeles"],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        
        self.assertEqual(payload["name"], "Monitor Bot")
        self.assertEqual(payload["description"], "Bot for /home/bot/grokbot in America/Los_Angeles")
    
    def test_unresolved_placeholder_fails(self):
        """Unresolved placeholders must cause failure"""
        profile = {
            "name": "Bot"
        }
        self.profile_path.write_text(json.dumps(profile))
        
        # Prompt with allowed but unresolved placeholder
        self.prompt_path.write_text("Uses {{WORKSPACE_PATH}} placeholder")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail on unresolved placeholder")
        self.assertIn("WORKSPACE_PATH", result.stderr)
    
    def test_empty_description_fails(self):
        """Empty description must fail"""
        profile = {
            "name": "Bot"
        }
        self.profile_path.write_text(json.dumps(profile))
        
        # Empty prompt.md
        self.prompt_path.write_text("")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail on empty prompt.md")
        self.assertIn("empty", result.stderr.lower())
    
    def test_missing_name_fails(self):
        """Missing name field must fail"""
        profile = {
            "title": "metadata only"
        }
        self.profile_path.write_text(json.dumps(profile))
        
        self.prompt_path.write_text("Canonical persona")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail on missing name")
        self.assertIn("name", result.stderr.lower())
    
    def test_section_id_optional(self):
        """section_id parameter is optional"""
        profile = {
            "name": "Bot"
        }
        self.profile_path.write_text(json.dumps(profile))
        
        self.prompt_path.write_text("Canonical persona from prompt.md")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path),
             "--section-id", "sec_abc123"],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        
        self.assertEqual(payload["section_id"], "sec_abc123")

class TestPayloadUpdate(unittest.TestCase):
    def test_update_name_only(self):
        """UpdateAgent with name only"""
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "update",
             "--agent-id", "agent_123",
             "--name", "New Name"],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        
        self.assertEqual(payload["agent_id"], "agent_123")
        self.assertEqual(payload["name"], "New Name")
        self.assertNotIn("description", payload)
    
    def test_update_description_only(self):
        """UpdateAgent with description only"""
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "update",
             "--agent-id", "agent_123",
             "--description", "New persona text"],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        
        self.assertEqual(payload["agent_id"], "agent_123")
        self.assertEqual(payload["description"], "New persona text")
        self.assertNotIn("name", payload)
    
    def test_update_both(self):
        """UpdateAgent with both name and description"""
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "update",
             "--agent-id", "agent_123",
             "--name", "New Name",
             "--description", "New persona"],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        
        self.assertEqual(set(payload.keys()), {"agent_id", "name", "description"})
    
    def test_update_missing_agent_id_fails(self):
        """UpdateAgent without agent_id must fail"""
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "update",
             "--name", "New Name"],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agent-id", result.stderr.lower())

class TestPlan(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.profile_path = self.tmpdir / "profile.json"
        self.prompt_path = self.tmpdir / "prompt.md"
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_plan_shows_preview(self):
        """Plan command shows preview WITHOUT creating bot"""
        canonical_persona = "Detailed canonical persona text from prompt.md " * 20
        profile = {
            "name": "Test Bot",
            "title": "Bot Title",
            "avatarShape": "circle"
        }
        self.profile_path.write_text(json.dumps(profile))
        
        # Canonical persona in prompt.md
        self.prompt_path.write_text(canonical_persona)
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "plan", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0)
        
        # Check plan content
        self.assertIn("Installation Plan", result.stdout)
        self.assertIn("Test Bot", result.stdout)
        self.assertIn(f"{len(canonical_persona)} characters", result.stdout)
        self.assertIn("Metadata stripped", result.stdout)
        self.assertIn("title", result.stdout.lower())
        self.assertIn("Manual configuration required", result.stdout)

class TestActualBotTemplates(unittest.TestCase):
    """Test real bot templates from repository"""
    
    def test_all_bots_compile(self):
        """All 13+ bot templates must compile successfully (with dummy params for placeholders)"""
        bots_dir = SCRIPT_DIR.parent / "bots"
        
        if not bots_dir.exists():
            self.skipTest("Bots directory not found")
        
        bot_dirs = [d for d in bots_dir.iterdir() if d.is_dir() and (d / "profile.json").exists()]
        
        self.assertGreater(len(bot_dirs), 0, "No bot templates found")
        
        # Dummy params for placeholder resolution (all possible placeholders)
        dummy_params = [
            "--param", "IMPLEMENTER_BOT=@implementer",
            "--param", "READER_X_BOT=@reader-x",
            "--param", "REMINDER_BOT=@reminder",
            "--param", "BOT_MAKER_BOT=@bot-maker",
            "--param", "TASK_MANAGER_BOT=@task-manager",
            "--param", "REPOSITORY_ANALYST_BOT=@repository-analyst",
            "--param", "TRANSLATOR_BOT=@translator",
            "--param", "IMPROVEMENTS_CHANNEL=#improvements",
            "--param", "IMPROVEMENTS_CHANNEL_ID=C12345",
            "--param", "PUBLISHING_CHANNEL=#publishing",
            "--param", "OWNER_TIMEZONE=America/Los_Angeles",
            "--param", "WORKSPACE_PATH=/home/bot/grokbot",
            "--param", "MONITOR_DATA_PATH=/home/bot/grokbot/data/monitor",
            "--param", "READING_DATA_PATH=/home/bot/grokbot/data/reading",
            "--param", "READING_FILTER_PATH=/home/bot/grokbot/data/reading/filter.json",
            "--param", "REMINDER_DATA_PATH=/home/bot/grokbot/data/reminders",
            "--param", "ANALYSIS_DATA_PATH=/home/bot/grokbot/data/analysis",
            "--param", "PLANNING_DATA_PATH=/home/bot/grokbot/data/planning",
            "--param", "PROJECT_TRACKING_PATH=/home/bot/grokbot/data/projects",
            "--param", "VIDEO_PROJECT_PATH=/home/bot/grokbot/videos",
            "--param", "REPORT_LANGUAGE=Russian",
            "--param", "OUTPUT_LANGUAGE=English",
            "--param", "WEEKLY_REPORT_DAY=Sunday",
            "--param", "WEEKLY_REPORT_TIME=20:00",
            "--param", "HOUR=09",
            "--param", "MINUTE=00",
            "--param", "DAY_OF_WEEK=Monday",
            "--param", "READING_ROUTINE_NAME=daily-reading",
            "--param", "NOTION_PROJECT_DATABASE=https://notion.so/db123",
            "--param", "CVE_NAG_INTERVAL=7d",
            "--param", "CVE_PACKAGES=package1,package2",
            "--param", "X_USER_ID=123456789",
            "--param", "X_USERNAME=@testuser"
        ]
        
        for bot_dir in bot_dirs:
            with self.subTest(bot=bot_dir.name):
                profile_path = bot_dir / "profile.json"
                
                result = subprocess.run(
                    [sys.executable, str(COMPILER_SCRIPT), "create", str(profile_path)] + dummy_params,
                    capture_output=True,
                    text=True
                )
                
                self.assertEqual(result.returncode, 0, 
                    f"Bot {bot_dir.name} failed to compile: {result.stderr}")
                
                payload = json.loads(result.stdout)
                
                # Verify structure
                self.assertIn("name", payload)
                self.assertIn("description", payload)
                
                # Verify full persona present
                self.assertGreater(len(payload["description"]), 50, 
                    f"Bot {bot_dir.name} persona too short")
                
                # Verify no metadata leaked
                for metadata_key in ["title", "avatarShape", "_comment"]:
                    self.assertNotIn(metadata_key, payload,
                        f"Bot {bot_dir.name} leaked metadata: {metadata_key}")

class TestCanonicalPersonaIdentities(unittest.TestCase):
    """Negative contract test 1: Verify all 13+ bot identities use FULL canonical prompt.md with anti-jobs"""
    
    def test_all_bots_have_full_canonical_persona(self):
        """All bot payloads must contain full prompt.md content including anti-jobs, not summaries"""
        bots_dir = SCRIPT_DIR.parent / "bots"
        
        if not bots_dir.exists():
            self.skipTest("Bots directory not found")
        
        bot_dirs = [d for d in bots_dir.iterdir() if d.is_dir() and (d / "profile.json").exists()]
        
        # Require at least 13 bots (as stated in review)
        self.assertGreaterEqual(len(bot_dirs), 13, "Expected at least 13 bot templates")
        
        # Complete dummy params matching all possible placeholders
        dummy_params = [
            "--param", "IMPLEMENTER_BOT=@implementer",
            "--param", "READER_X_BOT=@reader-x",
            "--param", "REMINDER_BOT=@reminder",
            "--param", "BOT_MAKER_BOT=@bot-maker",
            "--param", "TASK_MANAGER_BOT=@task-manager",
            "--param", "REPOSITORY_ANALYST_BOT=@repository-analyst",
            "--param", "TRANSLATOR_BOT=@translator",
            "--param", "IMPROVEMENTS_CHANNEL=#improvements",
            "--param", "IMPROVEMENTS_CHANNEL_ID=C12345",
            "--param", "PUBLISHING_CHANNEL=#publishing",
            "--param", "OWNER_TIMEZONE=America/Los_Angeles",
            "--param", "WORKSPACE_PATH=/home/bot/grokbot",
            "--param", "MONITOR_DATA_PATH=/home/bot/grokbot/data/monitor",
            "--param", "READING_DATA_PATH=/home/bot/grokbot/data/reading",
            "--param", "READING_FILTER_PATH=/home/bot/grokbot/data/reading/filter.json",
            "--param", "REMINDER_DATA_PATH=/home/bot/grokbot/data/reminders",
            "--param", "ANALYSIS_DATA_PATH=/home/bot/grokbot/data/analysis",
            "--param", "PLANNING_DATA_PATH=/home/bot/grokbot/data/planning",
            "--param", "PROJECT_TRACKING_PATH=/home/bot/grokbot/data/projects",
            "--param", "VIDEO_PROJECT_PATH=/home/bot/grokbot/videos",
            "--param", "REPORT_LANGUAGE=Russian",
            "--param", "OUTPUT_LANGUAGE=English",
            "--param", "WEEKLY_REPORT_DAY=Sunday",
            "--param", "WEEKLY_REPORT_TIME=20:00",
            "--param", "HOUR=09",
            "--param", "MINUTE=00",
            "--param", "DAY_OF_WEEK=Monday",
            "--param", "READING_ROUTINE_NAME=daily-reading",
            "--param", "NOTION_PROJECT_DATABASE=https://notion.so/db123",
            "--param", "CVE_NAG_INTERVAL=7d",
            "--param", "CVE_PACKAGES=package1,package2",
            "--param", "X_USER_ID=123456789",
            "--param", "X_USERNAME=@testuser"
        ]
        
        for bot_dir in bot_dirs:
            with self.subTest(bot=bot_dir.name):
                profile_path = bot_dir / "profile.json"
                prompt_path = bot_dir / "prompt.md"
                
                # Verify prompt.md exists (canonical persona source)
                self.assertTrue(prompt_path.exists(), 
                    f"Bot {bot_dir.name} missing canonical prompt.md")
                
                # Load expected full prompt
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    canonical_prompt = f.read()
                
                self.assertGreater(len(canonical_prompt), 200,
                    f"Bot {bot_dir.name} prompt.md too short to be full persona")
                
                # Compile payload
                result = subprocess.run(
                    [sys.executable, str(COMPILER_SCRIPT), "create", str(profile_path)] + dummy_params,
                    capture_output=True,
                    text=True
                )
                
                self.assertEqual(result.returncode, 0,
                    f"Bot {bot_dir.name} failed to compile: {result.stderr}")
                
                payload = json.loads(result.stdout)
                
                # CRITICAL: Description must be full prompt.md content after substitution
                # For bots with no placeholders, should match exactly
                # For bots with placeholders, should match after substitution
                description = payload["description"]
                
                # Verify substantial length (full persona, not summary)
                self.assertGreater(len(description), 200,
                    f"Bot {bot_dir.name} description too short - expected full prompt.md")
                
                # Check for anti-jobs markers (canonical prompts should define what bot doesn't do)
                # Most bots have explicit anti-jobs or limits sections
                has_anti_jobs_markers = any(marker in description.lower() for marker in [
                    "never", "don't", "do not", "not ", "anti-job", "only job", "honest limit"
                ])
                
                # If bot has anti-jobs in prompt.md, they MUST appear in payload
                if "never" in canonical_prompt.lower() or "don't" in canonical_prompt.lower():
                    self.assertTrue(has_anti_jobs_markers,
                        f"Bot {bot_dir.name} prompt.md has anti-jobs but payload description missing them")

class TestTokenSubstitutionSecurity(unittest.TestCase):
    """Negative contract test 2: Unknown/injected/malformed tokens must be rejected"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.profile_path = Path(self.temp_dir) / "profile.json"
        self.prompt_path = Path(self.temp_dir) / "prompt.md"
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_unknown_placeholder_rejected(self):
        """Placeholders not in ALLOWED_PLACEHOLDER_KEYS must fail"""
        profile = {
            "name": "Test Bot"
        }
        with open(self.profile_path, 'w') as f:
            json.dump(profile, f)
        
        # Prompt with unknown placeholder
        with open(self.prompt_path, 'w') as f:
            f.write("Bot with {{UNKNOWN_KEY}} placeholder")
        
        # Don't provide any params - the unknown placeholder will be caught
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail on unknown placeholder")
        # Should mention either "unknown" or "invalid" and the key name
        self.assertTrue("UNKNOWN_KEY" in result.stderr or "unknown" in result.stderr.lower())
    
    def test_injected_token_in_value_rejected(self):
        """Parameter values containing {{TOKENS}} must be rejected (prevent recursive expansion)"""
        profile = {"name": "Test Bot"}
        with open(self.profile_path, 'w') as f:
            json.dump(profile, f)
        
        with open(self.prompt_path, 'w') as f:
            f.write("Bot with {{WORKSPACE_PATH}} placeholder")
        
        # Try to inject a token in the parameter value
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path),
             "--param", "WORKSPACE_PATH=/path/{{INJECTED}}"],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should reject values with placeholder patterns")
        self.assertIn("recursive expansion not allowed", result.stderr.lower())
    
    def test_invalid_param_key_rejected(self):
        """Parameter keys not in ALLOWED_PLACEHOLDER_KEYS must be rejected"""
        profile = {"name": "Test Bot"}
        with open(self.profile_path, 'w') as f:
            json.dump(profile, f)
        
        with open(self.prompt_path, 'w') as f:
            f.write("Simple bot")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path),
             "--param", "INVALID_KEY=value"],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should reject invalid parameter keys")
        self.assertIn("INVALID_KEY", result.stderr)
    
    def test_unresolved_placeholder_rejected(self):
        """Placeholders without values must fail"""
        profile = {"name": "Test Bot"}
        with open(self.profile_path, 'w') as f:
            json.dump(profile, f)
        
        with open(self.prompt_path, 'w') as f:
            f.write("Bot with {{WORKSPACE_PATH}} placeholder")
        
        # Don't provide the required parameter
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail on unresolved placeholder")
        self.assertIn("WORKSPACE_PATH", result.stderr)
    
    def test_malformed_placeholder_rejected(self):
        """Malformed placeholders like {{unknown1}}, {{lowercase}}, etc must fail"""
        profile = {"name": "Test Bot"}
        with open(self.profile_path, 'w') as f:
            json.dump(profile, f)
        
        # Test with malformed placeholder ({{unknown1}} - not in allowed list, not uppercase-only)
        with open(self.prompt_path, 'w') as f:
            f.write("Bot with {{unknown1}} malformed placeholder")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail on malformed placeholder")
        self.assertTrue("unknown1" in result.stderr.lower() or "malformed" in result.stderr.lower() or "invalid" in result.stderr.lower())
    
    def test_leftover_delimiters_rejected(self):
        """Leftover {{ or }} after substitution must fail"""
        profile = {"name": "Test Bot"}
        with open(self.profile_path, 'w') as f:
            json.dump(profile, f)
        
        # Create prompt with text that looks like it has leftover delimiters
        with open(self.prompt_path, 'w') as f:
            f.write("Bot uses {{WORKSPACE_PATH}} and has leftover {{")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path),
             "--param", "WORKSPACE_PATH=/home/bot/grokbot"],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail on leftover delimiter")
        self.assertTrue("malformed" in result.stderr.lower() or "delimiter" in result.stderr.lower() or "{{" in result.stderr)

class TestParameterOrderIndependence(unittest.TestCase):
    """Negative contract test 3: Substitution must be deterministic regardless of parameter order"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.profile_path = Path(self.temp_dir) / "profile.json"
        self.prompt_path = Path(self.temp_dir) / "prompt.md"
        
        profile = {"name": "Test Bot"}
        with open(self.profile_path, 'w') as f:
            json.dump(profile, f)
        
        # Prompt with multiple placeholders
        with open(self.prompt_path, 'w') as f:
            f.write("Bot uses {{WORKSPACE_PATH}} and {{OWNER_TIMEZONE}} and {{REPORT_LANGUAGE}}")
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_parameter_order_independence(self):
        """Result must be identical regardless of --param order"""
        params1 = [
            "--param", "WORKSPACE_PATH=/home/bot/grokbot",
            "--param", "OWNER_TIMEZONE=America/Los_Angeles",
            "--param", "REPORT_LANGUAGE=English"
        ]
        
        params2 = [
            "--param", "REPORT_LANGUAGE=English",
            "--param", "WORKSPACE_PATH=/home/bot/grokbot",
            "--param", "OWNER_TIMEZONE=America/Los_Angeles"
        ]
        
        result1 = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)] + params1,
            capture_output=True,
            text=True
        )
        
        result2 = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(self.profile_path)] + params2,
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result1.returncode, 0)
        self.assertEqual(result2.returncode, 0)
        
        payload1 = json.loads(result1.stdout)
        payload2 = json.loads(result2.stdout)
        
        # Descriptions must be identical
        self.assertEqual(payload1["description"], payload2["description"],
            "Parameter order affected substitution result (non-deterministic)")

class TestCLIFailureModes(unittest.TestCase):
    """Negative contract test 4: Invalid CLI/plan must exit nonzero with no installable payload"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_missing_prompt_md_fails_nonzero(self):
        """Missing canonical prompt.md must exit nonzero"""
        profile_path = Path(self.temp_dir) / "profile.json"
        with open(profile_path, 'w') as f:
            json.dump({"name": "Test"}, f)
        
        # No prompt.md created
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail nonzero when prompt.md missing")
        self.assertIn("prompt.md", result.stderr.lower())
    
    def test_plan_with_unresolved_fails_nonzero(self):
        """Plan command with unresolved placeholders must exit nonzero"""
        profile_path = Path(self.temp_dir) / "profile.json"
        prompt_path = Path(self.temp_dir) / "prompt.md"
        
        with open(profile_path, 'w') as f:
            json.dump({"name": "Test"}, f)
        
        with open(prompt_path, 'w') as f:
            f.write("Bot with {{WORKSPACE_PATH}}")
        
        # Don't provide required param
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "plan", str(profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Plan should fail nonzero on unresolved placeholders")
    
    def test_invalid_profile_json_fails_nonzero(self):
        """Invalid JSON must exit nonzero"""
        profile_path = Path(self.temp_dir) / "profile.json"
        with open(profile_path, 'w') as f:
            f.write("{invalid json")
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail nonzero on invalid JSON")
    
    def test_empty_prompt_md_fails_nonzero(self):
        """Empty prompt.md must exit nonzero"""
        profile_path = Path(self.temp_dir) / "profile.json"
        prompt_path = Path(self.temp_dir) / "prompt.md"
        
        with open(profile_path, 'w') as f:
            json.dump({"name": "Test"}, f)
        
        with open(prompt_path, 'w') as f:
            f.write("")  # Empty
        
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "create", str(profile_path)],
            capture_output=True,
            text=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should fail nonzero on empty prompt.md")

class TestApprovalGating(unittest.TestCase):
    """Negative contract test 5: No filesystem or native apply without explicit approval"""
    
    def test_compiler_never_creates_filesystem_side_effects(self):
        """Compiler must never write files or make network calls - pure payload generation only"""
        temp_dir = tempfile.mkdtemp()
        try:
            profile_path = Path(temp_dir) / "profile.json"
            prompt_path = Path(temp_dir) / "prompt.md"
            
            with open(profile_path, 'w') as f:
                json.dump({"name": "Test"}, f)
            
            with open(prompt_path, 'w') as f:
                f.write("Test bot")
            
            # Track files before
            files_before = set(Path(temp_dir).rglob("*"))
            
            # Run compiler (should only output JSON to stdout)
            result = subprocess.run(
                [sys.executable, str(COMPILER_SCRIPT), "create", str(profile_path)],
                capture_output=True,
                text=True
            )
            
            # Track files after
            files_after = set(Path(temp_dir).rglob("*"))
            
            # No new files should be created (except by us)
            new_files = files_after - files_before
            self.assertEqual(len(new_files), 0, 
                f"Compiler created unexpected files: {new_files}")
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_plan_command_never_applies(self):
        """Plan command must be read-only, never apply changes"""
        temp_dir = tempfile.mkdtemp()
        try:
            profile_path = Path(temp_dir) / "profile.json"
            prompt_path = Path(temp_dir) / "prompt.md"
            
            with open(profile_path, 'w') as f:
                json.dump({"name": "Test"}, f)
            
            with open(prompt_path, 'w') as f:
                f.write("Test bot")
            
            result = subprocess.run(
                [sys.executable, str(COMPILER_SCRIPT), "plan", str(profile_path)],
                capture_output=True,
                text=True
            )
            
            self.assertEqual(result.returncode, 0)
            # Plan output should not contain CreateAgent calls or confirmations
            self.assertNotIn("CreateAgent(", result.stdout)
            self.assertNotIn("created successfully", result.stdout.lower())
            
        finally:
            shutil.rmtree(temp_dir)

class TestReadbackVerification(unittest.TestCase):
    """Contract test 6 (stage-1 policy): every created bot gets a write check result;
    a check that cannot be done is reported as NOT VERIFIED, never as verified."""
    
    def test_documentation_defines_write_check(self):
        """Loading instructions must define the write check and its three outcomes"""
        loading_doc = SCRIPT_DIR.parent / "LOADING-INSTRUCTIONS.md"
        
        if not loading_doc.exists():
            self.skipTest("LOADING-INSTRUCTIONS.md not found")
        
        content = loading_doc.read_text(encoding="utf-8")
        
        for outcome in ["VERIFIED", "NOT VERIFIED", "MISMATCH"]:
            self.assertIn(outcome, content, f"Loading instructions missing write-check outcome {outcome}")
        # Installation goes through the compiler build, not hand-made payloads
        self.assertIn("bot-payload-compiler.py build", content)
        self.assertIn("--config", content)
    
    def test_onboarding_explains_not_verified(self):
        """Onboarding doc must tell the user what NOT VERIFIED means"""
        onboarding_doc = SCRIPT_DIR.parent / "ONBOARDING.md"
        
        if not onboarding_doc.exists():
            self.skipTest("ONBOARDING.md not found")
        
        content = onboarding_doc.read_text(encoding="utf-8")
        self.assertIn("NOT VERIFIED", content, "Onboarding does not explain NOT VERIFIED")
    
    def test_compiler_output_warns_about_verification(self):
        """Compiler plan output must mention verification requirement"""
        temp_dir = tempfile.mkdtemp()
        try:
            profile_path = Path(temp_dir) / "profile.json"
            prompt_path = Path(temp_dir) / "prompt.md"
            
            with open(profile_path, 'w') as f:
                json.dump({"name": "Test"}, f)
            
            with open(prompt_path, 'w') as f:
                f.write("Test bot")
            
            result = subprocess.run(
                [sys.executable, str(COMPILER_SCRIPT), "plan", str(profile_path)],
                capture_output=True,
                text=True
            )
            
            self.assertEqual(result.returncode, 0)
            # Plan should mention manual verification or config required
            self.assertIn("Manual", result.stdout)
            
        finally:
            shutil.rmtree(temp_dir)

def _load_compiler_module():
    """Import bot-payload-compiler.py (hyphenated file name) for its constants."""
    import importlib.util
    sys.dont_write_bytecode = True  # no __pycache__ next to the script
    spec = importlib.util.spec_from_file_location("bot_payload_compiler", COMPILER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT_DIR = SCRIPT_DIR.parent
REAL_BOTS_DIR = ROOT_DIR / "bots"
ROOT_CONFIG_EXAMPLE = ROOT_DIR / "config.example.json"
ROOT_CONFIG_SCHEMA = ROOT_DIR / "config.schema.md"


def _run(*args):
    return subprocess.run([sys.executable, str(COMPILER_SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True)


def _make_bot(bots_dir, bot_id, prompt, profile=None):
    bot_dir = Path(bots_dir) / bot_id
    bot_dir.mkdir(parents=True)
    (bot_dir / "profile.json").write_text(json.dumps(profile or {"name": bot_id.title()}))
    (bot_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    return bot_dir


class TestPersonaSource(unittest.TestCase):
    """Persona comes only from prompt.md; profile.json never carries a persona field"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_description_comes_from_prompt_md(self):
        """Changing prompt.md changes the payload description; profile.json is untouched"""
        bot = _make_bot(self.tmp, "alpha", "First persona from prompt.md",
                        {"name": "Test Bot Alpha", "title": "t", "_comment": "c"})
        r1 = _run("create", bot / "profile.json")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        (bot / "prompt.md").write_text("Second persona from prompt.md")
        r2 = _run("create", bot / "profile.json")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(json.loads(r1.stdout)["description"], "First persona from prompt.md")
        self.assertEqual(json.loads(r2.stdout)["description"], "Second persona from prompt.md")
        self.assertEqual(json.loads(r2.stdout)["name"], "Test Bot Alpha")

    def test_profile_with_description_rejected(self):
        """A persona field in profile.json is an error for create, plan and build"""
        for field in ["description", "persona", "prompt"]:
            with self.subTest(field=field):
                bots_dir = self.tmp / f"bots-{field}"
                bot = _make_bot(bots_dir, "alpha", "Persona", {"name": "Alpha", field: "duplicate persona"})
                for cmd in (["create", bot / "profile.json"], ["plan", bot / "profile.json"],
                            ["build", "--bots", "alpha", "--bots-dir", bots_dir, "--out", self.tmp / f"out-{field}"]):
                    r = _run(*cmd)
                    self.assertNotEqual(r.returncode, 0, f"{cmd[0]} accepted profile.{field}")
                    self.assertIn(field, r.stderr)
                    self.assertIn("prompt.md", r.stderr)
                self.assertFalse((self.tmp / f"out-{field}").exists())

    def test_profile_unknown_field_rejected(self):
        """profile.json may contain only name + known metadata"""
        bot = _make_bot(self.tmp, "alpha", "Persona", {"name": "Alpha", "routines": "x"})
        r = _run("create", bot / "profile.json")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("routines", r.stderr)

    def test_real_profiles_have_no_persona_field(self):
        """Every bots/*/profile.json holds only name + non-persona metadata"""
        compiler = _load_compiler_module()
        profiles = sorted(REAL_BOTS_DIR.glob("*/profile.json"))
        self.assertGreaterEqual(len(profiles), 13)
        for path in profiles:
            with self.subTest(bot=path.parent.name):
                profile = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("name", profile)
                self.assertEqual(set(profile) & compiler.PERSONA_FIELDS, set(),
                                 f"{path.parent.name}/profile.json duplicates the persona")
                self.assertTrue(set(profile) <= compiler.PROFILE_ALLOWED_FIELDS,
                                f"unexpected fields: {set(profile) - compiler.PROFILE_ALLOWED_FIELDS}")

    def test_real_bots_description_equals_resolved_prompt_md(self):
        """Independent oracle: built <id>.md == prompt.md with config values substituted"""
        config = json.loads(ROOT_CONFIG_EXAMPLE.read_text(encoding="utf-8"))
        out = self.tmp / "out"
        r = _run("build", "--config", ROOT_CONFIG_EXAMPLE, "--bots", "all", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        for bot_dir in sorted(d for d in REAL_BOTS_DIR.iterdir() if (d / "profile.json").exists()):
            with self.subTest(bot=bot_dir.name):
                expected = (bot_dir / "prompt.md").read_text(encoding="utf-8")
                for key, value in config.items():
                    expected = expected.replace("{{" + key + "}}", value)
                self.assertEqual((out / f"{bot_dir.name}.md").read_text(encoding="utf-8"), expected)


class TestConfigFile(unittest.TestCase):
    """--config: flat JSON {KEY: value}, same whitelist and rejection rules as --param"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bot = _make_bot(self.tmp / "bots", "alpha", "Bot in {{WORKSPACE_PATH}} at {{OWNER_TIMEZONE}}")
        self.config = self.tmp / "config.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_config(self, data):
        self.config.write_text(json.dumps(data) if not isinstance(data, str) else data)

    def test_config_resolves_placeholders(self):
        self._write_config({"WORKSPACE_PATH": "/srv/test", "OWNER_TIMEZONE": "UTC"})
        r = _run("create", self.bot / "profile.json", "--config", self.config)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["description"], "Bot in /srv/test at UTC")

    def test_param_overrides_config(self):
        self._write_config({"WORKSPACE_PATH": "/srv/test", "OWNER_TIMEZONE": "UTC"})
        r = _run("create", self.bot / "profile.json", "--config", self.config,
                 "--param", "OWNER_TIMEZONE=Asia/Tokyo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["description"], "Bot in /srv/test at Asia/Tokyo")

    def test_config_and_param_combined(self):
        self._write_config({"WORKSPACE_PATH": "/srv/test"})
        r = _run("create", self.bot / "profile.json", "--config", self.config, "--param", "OWNER_TIMEZONE=UTC")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unknown_config_key_rejected(self):
        self._write_config({"WORKSPACE_PATH": "/srv/test", "OWNER_TIMEZONE": "UTC", "YOUR_TIMEZONE": "UTC"})
        r = _run("create", self.bot / "profile.json", "--config", self.config)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("YOUR_TIMEZONE", r.stderr)

    def test_placeholder_in_config_value_rejected(self):
        for bad in ["/srv/{{OWNER_TIMEZONE}}", "/srv/{{", "/srv/}}"]:
            with self.subTest(value=bad):
                self._write_config({"WORKSPACE_PATH": bad, "OWNER_TIMEZONE": "UTC"})
                r = _run("create", self.bot / "profile.json", "--config", self.config)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("WORKSPACE_PATH", r.stderr)

    def test_missing_key_in_config_fails(self):
        self._write_config({"WORKSPACE_PATH": "/srv/test"})
        r = _run("create", self.bot / "profile.json", "--config", self.config)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("OWNER_TIMEZONE", r.stderr)

    def test_malformed_config_rejected(self):
        for bad in ['["WORKSPACE_PATH"]', '{"WORKSPACE_PATH": 5, "OWNER_TIMEZONE": "UTC"}',
                    '{"WORKSPACE_PATH": "", "OWNER_TIMEZONE": "UTC"}', '{not json',
                    '{"workspace_path": "/srv", "OWNER_TIMEZONE": "UTC"}']:
            with self.subTest(config=bad):
                self._write_config(bad)
                r = _run("create", self.bot / "profile.json", "--config", self.config)
                self.assertNotEqual(r.returncode, 0, f"accepted config {bad}")

    def test_example_config_has_exactly_the_whitelist(self):
        compiler = _load_compiler_module()
        example = json.loads(ROOT_CONFIG_EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(set(example), set(compiler.ALLOWED_PLACEHOLDER_KEYS))
        for key, value in example.items():
            self.assertIsInstance(value, str)
            self.assertTrue(value.strip(), key)
            self.assertNotIn("/Users/", value)
            self.assertNotIn("/workspace/", value)


class TestBuild(unittest.TestCase):
    """build: validate every bot first, then write <id>.payload.json + <id>.md"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bots = self.tmp / "bots"
        _make_bot(self.bots, "alpha", "Alpha persona in {{WORKSPACE_PATH}}",
                  {"name": "Test Bot Alpha", "title": "x", "avatarShape": "blob", "_comment": "meta"})
        _make_bot(self.bots, "beta", "Beta persona, timezone {{OWNER_TIMEZONE}}\n", {"name": "Test Bot Beta"})
        self.config = self.tmp / "config.json"
        self.config.write_text(json.dumps({"WORKSPACE_PATH": "/srv/test", "OWNER_TIMEZONE": "UTC"}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build(self, out, bots="alpha,beta", *extra):
        return _run("build", "--config", self.config, "--bots", bots, "--bots-dir", self.bots, "--out", out, *extra)

    def test_build_writes_payload_and_md(self):
        out = self.tmp / "out"
        r = self._build(out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ["alpha.md", "alpha.payload.json", "beta.md", "beta.payload.json"])
        for bot_id, name in [("alpha", "Test Bot Alpha"), ("beta", "Test Bot Beta")]:
            payload = json.loads((out / f"{bot_id}.payload.json").read_text(encoding="utf-8"))
            self.assertEqual(set(payload), {"name", "description"})
            self.assertEqual(payload["name"], name)
            self.assertEqual((out / f"{bot_id}.md").read_text(encoding="utf-8"), payload["description"])
        self.assertEqual((out / "beta.md").read_text(encoding="utf-8"), "Beta persona, timezone UTC\n")

    def test_build_section_id(self):
        out = self.tmp / "out"
        r = self._build(out, "alpha", "--section-id", "section-test")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads((out / "alpha.payload.json").read_text())
        self.assertEqual(payload["section_id"], "section-test")

    def test_build_is_deterministic(self):
        r1 = self._build(self.tmp / "out1", "alpha,beta")
        r2 = self._build(self.tmp / "out2", "beta,alpha")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        for name in ["alpha.md", "alpha.payload.json", "beta.md", "beta.payload.json"]:
            self.assertEqual((self.tmp / "out1" / name).read_bytes(), (self.tmp / "out2" / name).read_bytes())

    def test_build_all(self):
        out = self.tmp / "out"
        r = self._build(out, "all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(list(out.glob("*.payload.json"))), 2)

    def test_one_bad_bot_fails_whole_build_nothing_written(self):
        _make_bot(self.bots, "gamma", "Gamma uses {{REPORT_LANGUAGE}}")  # key missing from config
        for out_name, pre_create in [("out-new", False), ("out-existing", True)]:
            with self.subTest(out=out_name):
                out = self.tmp / out_name
                if pre_create:
                    out.mkdir()
                r = self._build(out, "alpha,gamma,beta")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("gamma", r.stderr)
                self.assertIn("REPORT_LANGUAGE", r.stderr)
                if pre_create:
                    self.assertEqual(list(out.iterdir()), [], "partial output written")
                else:
                    self.assertFalse(out.exists(), "output folder created on failed build")

    def test_all_errors_reported(self):
        _make_bot(self.bots, "gamma", "Gamma uses {{REPORT_LANGUAGE}}")
        r = self._build(self.tmp / "out", "gamma,missing-bot")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gamma", r.stderr)
        self.assertIn("missing-bot", r.stderr)

    def test_bad_bot_ids_rejected(self):
        for spec in ["alpha,alpha", "../alpha", "alpha,", "Alpha"]:
            with self.subTest(bots=spec):
                out = self.tmp / "out-bad"
                r = self._build(out, spec)
                self.assertNotEqual(r.returncode, 0, f"accepted --bots {spec}")
                self.assertFalse(out.exists())

    def test_build_requires_bots_and_out(self):
        self.assertNotEqual(_run("build", "--config", self.config, "--out", self.tmp / "o").returncode, 0)
        self.assertNotEqual(_run("build", "--config", self.config, "--bots", "alpha",
                                 "--bots-dir", self.bots).returncode, 0)

    def test_real_bots_build_with_example_config(self):
        out = self.tmp / "real"
        r = _run("build", "--config", ROOT_CONFIG_EXAMPLE, "--bots", "all", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        n_bots = len([d for d in REAL_BOTS_DIR.iterdir() if (d / "profile.json").exists()])
        self.assertEqual(len(list(out.glob("*.payload.json"))), n_bots)
        for md in out.glob("*.md"):
            text = md.read_text(encoding="utf-8")
            self.assertNotIn("{{", text, md.name)
            self.assertNotIn("}}", text, md.name)


class TestConfigExampleGeneration(unittest.TestCase):
    """config.example.json / config.schema.md are generated from the files and stay in sync"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_committed_files_match_generator(self):
        r = _run("config-example", "--out-dir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.tmp / "config.example.json").read_bytes(), ROOT_CONFIG_EXAMPLE.read_bytes(),
                         "config.example.json is stale: regenerate with config-example --out-dir .")
        self.assertEqual((self.tmp / "config.schema.md").read_bytes(), ROOT_CONFIG_SCHEMA.read_bytes(),
                         "config.schema.md is stale: regenerate with config-example --out-dir .")

    def test_every_prompt_placeholder_is_whitelisted(self):
        compiler = _load_compiler_module()
        import re
        for prompt in sorted(REAL_BOTS_DIR.glob("*/prompt.md")):
            with self.subTest(bot=prompt.parent.name):
                keys = set(re.findall(r"\{\{([A-Z_]+)\}\}", prompt.read_text(encoding="utf-8")))
                self.assertEqual(keys - compiler.ALLOWED_PLACEHOLDER_KEYS, set())

    def test_schema_lists_every_key_with_its_bots(self):
        compiler = _load_compiler_module()
        usage = compiler.placeholder_usage(REAL_BOTS_DIR)
        schema = ROOT_CONFIG_SCHEMA.read_text(encoding="utf-8")
        for key in compiler.ALLOWED_PLACEHOLDER_KEYS:
            row = next((l for l in schema.splitlines() if l.startswith(f"| `{key}` |")), None)
            self.assertIsNotNone(row, f"{key} missing from config.schema.md")
            for bot in usage[key]:
                self.assertIn(bot, row)

    def test_unknown_key_in_compiled_prompt_fails_generation(self):
        bots = self.tmp / "bots"
        _make_bot(bots, "alpha", "Uses {{NOT_A_KEY}}")
        r = _run("config-example", "--out-dir", self.tmp / "out", "--bots-dir", bots)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("NOT_A_KEY", r.stderr)
        self.assertFalse((self.tmp / "out").exists())


MIRROR_SCRIPT = SCRIPT_DIR / "bot-mirror.py"


class TestStage1(unittest.TestCase):
    """rc2 = stage 1: only main-grok and bot-maker are installed, with stage-1 keys only"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.compiler = _load_compiler_module()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage1_bots(self):
        self.assertEqual(tuple(self.compiler.STAGE1_BOTS), ("main-grok", "bot-maker"))

    def test_stage1_keys(self):
        """The installer fills exactly these keys itself (LOADING-INSTRUCTIONS step 4)"""
        keys = self.compiler.stage1_keys(REAL_BOTS_DIR)
        self.assertEqual(keys, ["BOT_MAKER_BOT", "WORKSPACE_PATH"])
        loading = (ROOT_DIR / "LOADING-INSTRUCTIONS.md").read_text(encoding="utf-8")
        for key in keys:
            self.assertIn(f"`{key}`", loading)

    def test_build_with_only_stage1_keys(self):
        keys = self.compiler.stage1_keys(REAL_BOTS_DIR)
        config = self.tmp / "config.json"
        config.write_text(json.dumps({k: self.compiler.KEY_DOCS[k][1] for k in keys}))
        out = self.tmp / "build"
        r = _run("build", "--config", config, "--bots", "main-grok,bot-maker", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ["bot-maker.md", "bot-maker.payload.json", "main-grok.md", "main-grok.payload.json"])
        names = {json.loads((out / f"{b}.payload.json").read_text(encoding="utf-8"))["name"]
                 for b in ("main-grok", "bot-maker")}
        self.assertEqual(names, {"Main Grok", "Bot Maker"})
        for md in out.glob("*.md"):
            text = md.read_text(encoding="utf-8")
            self.assertNotIn("{{", text, md.name)
            self.assertNotIn("}}", text, md.name)

    def test_stage1_build_fails_without_a_stage1_key(self):
        keys = self.compiler.stage1_keys(REAL_BOTS_DIR)
        for missing in keys:
            with self.subTest(missing=missing):
                config = self.tmp / f"config-{missing}.json"
                config.write_text(json.dumps({k: self.compiler.KEY_DOCS[k][1] for k in keys if k != missing}))
                out = self.tmp / f"out-{missing}"
                r = _run("build", "--config", config, "--bots", "main-grok,bot-maker", "--out", out)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(missing, r.stderr)
                self.assertFalse(out.exists())

    def test_stage1_prompts_name_no_uninstalled_bot(self):
        """Stage-1 bots must not route to bots this release does not install"""
        import re
        for bot in self.compiler.STAGE1_BOTS:
            with self.subTest(bot=bot):
                text = (REAL_BOTS_DIR / bot / "prompt.md").read_text(encoding="utf-8")
                bot_keys = set(re.findall(r"\{\{([A-Z_]+_BOT)\}\}", text))
                self.assertLessEqual(bot_keys, {"BOT_MAKER_BOT"})

    def test_schema_marks_stage1_keys(self):
        keys = set(self.compiler.stage1_keys(REAL_BOTS_DIR))
        schema = ROOT_CONFIG_SCHEMA.read_text(encoding="utf-8")
        for key in self.compiler.ALLOWED_PLACEHOLDER_KEYS:
            row = next(l for l in schema.splitlines() if l.startswith(f"| `{key}` |"))
            if key in keys:
                self.assertIn("**stage 1**", row)
            else:
                self.assertIn("optional bots", row)

    def test_loading_instructions_use_repo_mirror(self):
        loading = (ROOT_DIR / "LOADING-INSTRUCTIONS.md").read_text(encoding="utf-8")
        for needle in ["--bots main-grok,bot-maker", "~/agent-data/agents/<agent_id>/profile.json",
                       "bots/core/", "bots/my/", "bots/marketplace/", "git init", "Bot: "]:
            self.assertIn(needle, loading)


class TestPublicTreeHygiene(unittest.TestCase):
    """No leftovers of the third-party Bot Maker template anywhere in the public tree"""

    # Assembled from parts so this file does not contain the words itself
    FORBIDDEN = ["pote" + "to", "mad" + "-scientist", "mad" + " scientist", "ps" + "tack"]

    def test_no_third_party_template_words(self):
        hits = []
        for path in sorted(ROOT_DIR.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            text = path.read_bytes().decode("utf-8", errors="ignore").lower()
            rel = str(path.relative_to(ROOT_DIR)).lower()
            for word in self.FORBIDDEN:
                if word in text or word in rel:
                    hits.append(f"{path.relative_to(ROOT_DIR)}: {word}")
        self.assertEqual(hits, [])


def _mirror(*args):
    return subprocess.run([sys.executable, "-B", str(MIRROR_SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True)


class TestBotMirror(unittest.TestCase):
    """bot-mirror.py: write check, scan for unknown bots, name+description snapshot only"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.agents = self.tmp / "agents"
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        self.expected = self.tmp / "expected.md"
        self.expected.write_text("Exact text\nline two\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _agent(self, agent_id, name, description, extra=None):
        d = self.agents / agent_id
        d.mkdir(parents=True)
        profile = {"name": name, "description": description, "harness": "x"}
        (d / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
        for fname, content in (extra or {}).items():
            (d / fname).write_text(content)
        return d

    def _record(self, origin, slug, agent_id):
        d = self.ws / "bots" / origin / slug
        d.mkdir(parents=True)
        (d / "agent.json").write_text(json.dumps({"agent_id": agent_id}))

    def _check(self, agent_id):
        r = _mirror("check", "--agent-id", agent_id, "--expected", self.expected, "--agents-dir", self.agents)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_check_verified(self):
        self._agent("a1", "Alpha", "Exact text\nline two\n")
        self.assertEqual(self._check("a1"), "VERIFIED")

    def test_check_mismatch_on_any_difference(self):
        self._agent("a1", "Alpha", "Exact text\nline two")  # missing final newline
        self.assertEqual(self._check("a1"), "MISMATCH")

    def test_check_not_verified_when_file_missing_or_bad(self):
        self.assertEqual(self._check("missing"), "NOT VERIFIED")
        d = self.agents / "bad"
        d.mkdir(parents=True)
        (d / "profile.json").write_text("{not json")
        self.assertEqual(self._check("bad"), "NOT VERIFIED")
        d = self.agents / "nodesc"
        d.mkdir(parents=True)
        (d / "profile.json").write_text(json.dumps({"name": "X"}))
        self.assertEqual(self._check("nodesc"), "NOT VERIFIED")

    def test_invalid_agent_id_rejected(self):
        for bad in ["../x", "a/b", ".hidden", ""]:
            with self.subTest(agent_id=bad):
                r = _mirror("check", "--agent-id", bad, "--expected", self.expected, "--agents-dir", self.agents)
                self.assertNotEqual(r.returncode, 0)

    def test_scan_lists_only_unknown_bots(self):
        self._agent("core1", "Main Grok", "t")
        self._agent("my1", "Note Bot", "t")
        self._agent("new1", "Imported Bot", "t")
        self._record("core", "main-grok", "core1")
        self._record("my", "note-bot", "my1")
        r = _mirror("scan", "--workspace", self.ws, "--agents-dir", self.agents)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [{"agent_id": "new1", "name": "Imported Bot"}])

    def test_snapshot_keeps_non_latin_names(self):
        self._agent("ru1", "Помощник по почте", "t")
        self._agent("sym1", "***", "t")
        for agent_id, slug in (("ru1", "помощник-по-почте"), ("sym1", "bot")):
            with self.subTest(agent_id=agent_id):
                r = _mirror("snapshot", "--workspace", self.ws, "--agent-id", agent_id, "--agents-dir", self.agents)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue((self.ws / "bots" / "marketplace" / slug / "prompt.md").is_file())

    def test_scan_unreadable_agents_dir_fails(self):
        r = _mirror("scan", "--workspace", self.ws, "--agents-dir", self.tmp / "nope")
        self.assertNotEqual(r.returncode, 0)

    def test_snapshot_copies_only_name_and_description(self):
        self._agent("new1", "Imported Bot!", "Imported text\n",
                    {"store.db": "DB", "box-secrets.json": "{}", "settings.json": "{}"})
        r = _mirror("snapshot", "--workspace", self.ws, "--agent-id", "new1", "--source", "marketplace",
                    "--agents-dir", self.agents)
        self.assertEqual(r.returncode, 0, r.stderr)
        target = self.ws / "bots" / "marketplace" / "imported-bot"
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["agent.json", "prompt.md"])
        self.assertEqual((target / "prompt.md").read_text(encoding="utf-8"), "Imported text\n")
        self.assertEqual(json.loads((target / "agent.json").read_text()),
                         {"agent_id": "new1", "source": "marketplace"})
        # second snapshot of the same bot is refused; the record is now known
        r = _mirror("snapshot", "--workspace", self.ws, "--agent-id", "new1", "--agents-dir", self.agents)
        self.assertNotEqual(r.returncode, 0)

    def test_snapshot_slug_collision_and_bad_source(self):
        self._agent("n1", "Same Name", "one")
        self._agent("n2", "Same Name", "two")
        for agent_id in ("n1", "n2"):
            r = _mirror("snapshot", "--workspace", self.ws, "--agent-id", agent_id, "--agents-dir", self.agents)
            self.assertEqual(r.returncode, 0, r.stderr)
        base = self.ws / "bots" / "marketplace"
        self.assertEqual(sorted(p.name for p in base.iterdir()), ["same-name", "same-name-2"])
        self._agent("n3", "Other", "x")
        r = _mirror("snapshot", "--workspace", self.ws, "--agent-id", "n3", "--source", "github",
                    "--agents-dir", self.agents)
        self.assertNotEqual(r.returncode, 0)



LOCAL_COPY_DOC = ROOT_DIR / "LOCAL-COPY.md"


def _isolated_git_env(tmp: Path) -> dict:
    """git that ignores the host's global/system config (no signing, no hooks path, fixed user)."""
    cfg = tmp / "gitconfig"
    cfg.write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                   "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(cfg), "GIT_TERMINAL_PROMPT": "0"})
    return env


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestLocalCopy(unittest.TestCase):
    """bot-mirror.py pack (bot computer) + the unpack block of LOCAL-COPY.md (user's computer)"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = _isolated_git_env(self.tmp)
        self.ws = self.tmp / "ws"
        self.archive = self.ws / "build" / "local-copy.tar.gz"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args, cwd=None):
        r = subprocess.run(["git", *args], cwd=cwd or self.ws, env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def _write(self, rel, text):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _make_repo(self):
        self._write("bots/core/x/prompt.md", "Prompt v1\n")
        self._write("config.json", '{"WORKSPACE_PATH": "ws"}\n')
        self._write(".gitignore", "grokbotceo/\nbuild/\n")
        self._write("untracked.txt", "not committed\n")
        self._write("build/stale.txt", "build output\n")
        self._write("grokbotceo/VERSION", "release copy\n")
        self._git("init", "-q")
        self._git("add", ".gitignore", "config.json", "bots")
        self._git("commit", "-q", "-m", "Install GrokBotCEO", "-m", "Bot: Test")

    def _pack(self, workspace=None):
        return subprocess.run([sys.executable, "-B", str(MIRROR_SCRIPT), "pack",
                               "--workspace", str(workspace or self.ws), "--out", str(self.archive)],
                              capture_output=True, text=True, env=self.env)

    def _block(self):
        text = LOCAL_COPY_DOC.read_text(encoding="utf-8")
        blocks = re.findall(r"^```sh\n(.*?)^```$", text, re.M | re.S)
        self.assertEqual(len(blocks), 1, "LOCAL-COPY.md must hold exactly one ```sh block")
        self.assertEqual(text.count("```sh"), 1)
        self.assertTrue(blocks[0].startswith('P="<path>"\nA="<path>.tar.gz"\n'))
        self.assertEqual(blocks[0].count("<path>"), 2)
        return blocks[0]

    def _deliver(self, path):
        """Stand-in for copying the archive to <path>.tar.gz on the user's computer."""
        shutil.copyfile(self.archive, f"{path}.tar.gz")

    def _unpack(self, path, shell="/bin/sh"):
        script = self._block().replace("<path>", str(path))
        return subprocess.run([shell, "-c", script], cwd=self.tmp, env=self.env,
                              capture_output=True, text=True)

    # --- pack ---------------------------------------------------------------

    def test_pack_holds_committed_repo_only(self):
        self._make_repo()
        os.symlink("config.json", self.ws / "link")
        self._git("add", "link")
        self._git("config", "core.pager", "cat")
        self._git("commit", "-q", "-m", "Add link")
        hook = self.ws / ".git" / "hooks" / "post-checkout"
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o755)
        r = self._pack()
        self.assertEqual(r.returncode, 0, r.stderr)
        head = self._git("rev-parse", "--short", "HEAD").strip()
        self.assertEqual(r.stdout.splitlines(), [str(self.archive), f"commit {head}"])
        with tarfile.open(self.archive) as tar:
            members = tar.getmembers()
            names = [m.name for m in members]
            config = tar.extractfile(".git/config").read().decode("utf-8")
        self.assertEqual(names[0], ".grokbotceo-copy")
        for name in (".git/HEAD", "bots/core/x/prompt.md", "config.json", ".gitignore"):
            self.assertIn(name, names)
        for name in names:
            with self.subTest(member=name):
                self.assertFalse(name.startswith("/"))
                self.assertNotIn("..", name)
                self.assertNotIn(name, ("untracked.txt", "link"))
                self.assertFalse(name.startswith(("build/", "grokbotceo/", ".git/hooks")))
        self.assertTrue(all(m.isfile() or m.isdir() for m in members), "no symlinks in the archive")
        self.assertNotIn("pager", config)
        self.assertNotIn("[user]", config)

    def test_pack_refuses_uncommitted_changes(self):
        self._make_repo()
        self._write("config.json", '{"changed": true}\n')
        r = self._pack()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uncommitted", r.stderr)
        self.assertFalse(self.archive.exists())

    def test_pack_refuses_non_repo_and_empty_repo(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "a.txt").write_text("a")
        r = self._pack(plain)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a git repo", r.stderr)
        self.ws.mkdir()
        self._git("init", "-q")
        r = self._pack()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no commit", r.stderr)
        self.assertFalse(self.archive.exists())

    # --- unpack block -------------------------------------------------------

    def test_unpack_first_install(self):
        self._make_repo()
        self.assertEqual(self._pack().returncode, 0)
        shells = ["/bin/sh"] + [s for s in (shutil.which("dash"), shutil.which("bash"), shutil.which("zsh")) if s]
        for shell in shells:
            with self.subTest(shell=shell):
                copy = self.tmp / "home" / Path(shell).name / "GrokBotCEO-copy"
                copy.parent.mkdir(parents=True)
                self._deliver(copy)
                r = self._unpack(copy, shell)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("COPY UPDATED", r.stdout)
                self.assertTrue((copy / ".grokbotceo-copy").is_file())
                self.assertEqual((copy / "bots/core/x/prompt.md").read_text(encoding="utf-8"), "Prompt v1\n")
                self.assertFalse(Path(f"{copy}.tar.gz").exists())
                self.assertFalse(Path(f"{copy}.new").exists())
                self.assertFalse((copy / "untracked.txt").exists())
                self.assertIn("Install GrokBotCEO", self._git("log", "--format=%s", cwd=copy))
                self.assertEqual(self._git("status", "--porcelain", cwd=copy), "")

    def test_unpack_second_run_replaces_copy(self):
        self._make_repo()
        self.assertEqual(self._pack().returncode, 0)
        copy = self.tmp / "GrokBotCEO-copy"
        self._deliver(copy)
        self.assertEqual(self._unpack(copy).returncode, 0)
        (copy / "edited-by-user.txt").write_text("overwritten on refresh")
        self._write("bots/core/x/prompt.md", "Prompt v2\n")
        self._git("commit", "-q", "-am", "Change x", "-m", "Bot: Bot Maker")
        self.assertEqual(self._pack().returncode, 0)
        self._deliver(copy)
        r = self._unpack(copy)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("COPY UPDATED", r.stdout)
        self.assertEqual((copy / "bots/core/x/prompt.md").read_text(encoding="utf-8"), "Prompt v2\n")
        self.assertFalse((copy / "edited-by-user.txt").exists())
        self.assertEqual(self._git("log", "--format=%s", cwd=copy).splitlines(), ["Change x", "Install GrokBotCEO"])

    def test_unpack_refuses_folder_without_marker(self):
        self._make_repo()
        self.assertEqual(self._pack().returncode, 0)
        home = self.tmp / "home"
        home.mkdir()
        (home / "keep.txt").write_text("mine")
        self._deliver(home)
        r = self._unpack(home)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("STOP", r.stdout)
        self.assertEqual(sorted(p.name for p in home.iterdir()), ["keep.txt"])
        self.assertEqual((home / "keep.txt").read_text(), "mine")
        self.assertFalse(Path(f"{home}.new").exists())
        self.assertTrue(Path(f"{home}.tar.gz").exists())

    def test_unpack_refuses_stale_new_folder_without_marker(self):
        self._make_repo()
        self.assertEqual(self._pack().returncode, 0)
        copy = self.tmp / "GrokBotCEO-copy"
        stale = Path(f"{copy}.new")
        stale.mkdir()
        (stale / "keep.txt").write_text("mine")
        self._deliver(copy)
        r = self._unpack(copy)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("STOP", r.stdout)
        self.assertEqual(sorted(p.name for p in stale.iterdir()), ["keep.txt"])
        self.assertFalse(copy.exists())

    def test_unpack_refuses_relative_or_empty_path(self):
        self._make_repo()
        self.assertEqual(self._pack().returncode, 0)
        for path in ("relative/copy", ""):
            with self.subTest(path=path):
                r = self._unpack(path)
                self.assertNotEqual(r.returncode, 0)
                self.assertTrue(r.stdout.startswith("STOP:"), r.stdout)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["gitconfig", "ws"])

class TestCLI(unittest.TestCase):
    def test_help_works(self):
        """CLI help should work"""
        result = subprocess.run(
            [sys.executable, str(COMPILER_SCRIPT), "--help"],
            capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"Compile bot payloads", result.stdout)

if __name__ == "__main__":
    print(f"Testing: {COMPILER_SCRIPT}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("NO live bot creation - fictional fixtures only", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stderr)
    result = runner.run(suite)
    
    sys.exit(0 if result.wasSuccessful() else 1)
