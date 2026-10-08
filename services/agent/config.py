"""
Configuration module for the ML Restock Agent service.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Service ports and URLs
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8001")
MARKET_URL = os.getenv("MARKET_URL", "http://localhost:8002")
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8003")

# Auth tokens
AGENT_KEY = os.getenv("AGENT_KEY", "key_agent_restock")
OWNER_TOKEN = os.getenv("OWNER_TOKEN", "tok_owner_ada")

# LLM provider settings (Defaults to Groq free tier)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
