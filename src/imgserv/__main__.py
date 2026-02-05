"""
CLI entry point for the Photo Frame Server.

Usage:
    python -m imgserv /path/to/images [--port 8000] [--interval 5]
"""

import argparse
import os
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
    python -m imgserv ./photos --city "New York" --weather-api-key YOUR_API_KEY
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
    
    parser.add_argument(
        '--weather-api-key',
        help='OpenWeather API key (or set OPENWEATHER_API_KEY env var)'
    )
    
    parser.add_argument(
        '--city',
        help='City name for weather display (e.g., "London" or "New York,US")'
    )
    
    parser.add_argument(
        '--sleep-start',
        default='23:00',
        help='Sleep mode start time in HH:MM format (default: 23:00)'
    )
    
    parser.add_argument(
        '--sleep-end',
        default='06:00',
        help='Sleep mode end time in HH:MM format (default: 06:00)'
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
    
    # Get weather API key (CLI arg takes precedence over env var)
    weather_api_key = args.weather_api_key or os.environ.get('OPENWEATHER_API_KEY')
    
    # Validate sleep time format
    import re
    time_pattern = re.compile(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
    if not time_pattern.match(args.sleep_start):
        print("Error: --sleep-start must be in HH:MM format (e.g., 23:00)")
        sys.exit(1)
    if not time_pattern.match(args.sleep_end):
        print("Error: --sleep-end must be in HH:MM format (e.g., 06:00)")
        sys.exit(1)
    
    # Run the server
    sys.exit(run_server(args.image_dir, args.port, args.interval, weather_api_key, args.city,
                        args.sleep_start, args.sleep_end))


if __name__ == '__main__':
    main()
