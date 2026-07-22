"""Loads .env into the process environment before any app.* module reads it."""
from dotenv import load_dotenv

load_dotenv()
