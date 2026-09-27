"""
conftest.py — Makes pytest discover all project modules without install.
Adds the project root to sys.path so `import shared`, `import network_sim`, etc. work.
"""
import sys
from pathlib import Path

# Insert project root at position 0 so all top-level packages are importable
sys.path.insert(0, str(Path(__file__).parent.parent))
