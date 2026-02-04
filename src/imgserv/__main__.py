"""
CLI entry point for the Photo Frame Server.

Usage:
    python -m imgserv /path/to/images [--port 8000] [--interval 5]
"""

import argparse
import sys
from .server import run_server


def main():
    """Parse command line arguments and start the server."""
    parser = argparse.ArgumentParser(
        description='Photo Frame Server - Serve images as a slideshow',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    python -m imgserv ./photos
    python -m imgserv /path/to/images --port 8080
    python -m imgserv ./images --interval 10
    python -m imgserv ./pictures --port 3000 --interval 3
        '''
    )
    
    parser.add_argument(
        'image_dir',
        help='Path to directory containing images'
    )
    
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8000,
        help='Server port (default: 8000)'
    )
    
    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=5,
        help='Seconds between images (default: 5)'
    )
    
    args = parser.parse_args()
    
    # Validate interval
    if args.interval < 1:
        print("Error: Interval must be at least 1 second")
        sys.exit(1)
    
    # Validate port
    if args.port < 1 or args.port > 65535:
        print("Error: Port must be between 1 and 65535")
        sys.exit(1)
    
    # Run the server
    sys.exit(run_server(args.image_dir, args.port, args.interval))


if __name__ == '__main__':
    main()
