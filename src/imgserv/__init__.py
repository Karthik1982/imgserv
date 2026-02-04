"""
imgserv - Photo Frame Web Server

A simple Python web server that serves images from a directory as an auto-advancing slideshow.
"""

from .server import run_server, get_image_files

__version__ = '0.1.0'
__all__ = ['run_server', 'get_image_files']
