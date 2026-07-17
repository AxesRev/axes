"""Aegra API - Self-hosted Agent Protocol server."""

import asyncio
import sys
from importlib.metadata import version

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

__version__ = version("aegra-api")
