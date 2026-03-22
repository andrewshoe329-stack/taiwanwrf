"""Pytest configuration — add project root to sys.path."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
