"""
RAAH Project Configuration Bridge
=================================

Bridges historical path imports to the centralized api.settings.Settings layer.
Preserves full backwards compatibility for all modules importing from api.config.
"""

from api.settings import settings

# Backwards-compatible path constants
ROOT = settings.root_dir
DISPATCH_DIR = settings.dispatch_dir
DATASET_DIR = settings.dataset_dir
DATA_DIR = settings.data_dir
FRONTEND_DIR = settings.frontend_dir

# Export the settings instance
__all__ = ["ROOT", "DISPATCH_DIR", "DATASET_DIR", "DATA_DIR", "FRONTEND_DIR", "settings"]
