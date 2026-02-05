#!/usr/bin/env python3
"""
Entry point script for PyInstaller executable.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from imgserv.__main__ import main

if __name__ == '__main__':
    main()
