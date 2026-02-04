"""
Photo Frame Web Server

A simple HTTP server that serves images from a directory as an auto-advancing slideshow.
"""

import os
import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote

# Supported image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

# HTML template with placeholder for interval
HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Photo Frame</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #000;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            overflow: hidden;
        }}
        img {{
            max-width: 100%;
            max-height: 100vh;
            object-fit: contain;
        }}
        .loading {{
            color: #fff;
            font-family: sans-serif;
            font-size: 24px;
        }}
    </style>
</head>
<body>
    <div id="loading" class="loading">Loading images...</div>
    <img id="photo" src="" alt="Photo" style="display:none;">
    <script>
        var currentImage = '';
        var interval = {interval};
        
        function fetchAndShow() {{
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/images', true);
            xhr.onreadystatechange = function() {{
                if (xhr.readyState === 4 && xhr.status === 200) {{
                    var images = JSON.parse(xhr.responseText);
                    if (images.length > 0) {{
                        document.getElementById('loading').style.display = 'none';
                        document.getElementById('photo').style.display = 'block';
                        
                        var nextIndex = 0;
                        if (currentImage) {{
                            var idx = images.indexOf(currentImage);
                            if (idx >= 0) {{
                                nextIndex = (idx + 1) % images.length;
                            }}
                        }}
                        
                        currentImage = images[nextIndex];
                        document.getElementById('photo').src = '/image/' + encodeURIComponent(currentImage);
                    }} else {{
                        document.getElementById('loading').style.display = 'block';
                        document.getElementById('photo').style.display = 'none';
                        document.getElementById('loading').innerHTML = 'No images found';
                    }}
                    setTimeout(fetchAndShow, interval);
                }}
            }};
            xhr.send();
        }}
        
        fetchAndShow();
    </script>
</body>
</html>'''


def get_image_files(directory):
    """Get list of image files from the specified directory."""
    if not os.path.isdir(directory):
        return []
    
    files = []
    for filename in os.listdir(directory):
        ext = os.path.splitext(filename)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            files.append(filename)
    
    # Sort alphabetically for consistent ordering
    files.sort()
    return files


def create_handler(image_dir, interval_ms):
    """Create a request handler class with the specified configuration."""
    
    class PhotoFrameHandler(BaseHTTPRequestHandler):
        """HTTP request handler for the photo frame server."""
        
        def log_message(self, format, *args):
            """Override to provide cleaner logging."""
            print(f"[{self.address_string()}] {format % args}")
        
        def send_response_headers(self, status, content_type, content_length=None):
            """Send response with common headers."""
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            if content_length is not None:
                self.send_header('Content-Length', content_length)
            self.end_headers()
        
        def do_GET(self):
            """Handle GET requests."""
            path = unquote(self.path)
            
            if path == '/' or path == '/index.html':
                self.serve_index()
            elif path == '/api/images':
                self.serve_image_list()
            elif path.startswith('/image/'):
                filename = path[7:]  # Remove '/image/' prefix
                self.serve_image(filename)
            else:
                self.send_error(404, 'Not Found')
        
        def serve_index(self):
            """Serve the main HTML page."""
            html = HTML_TEMPLATE.format(interval=interval_ms)
            content = html.encode('utf-8')
            self.send_response_headers(200, 'text/html; charset=utf-8', len(content))
            self.wfile.write(content)
        
        def serve_image_list(self):
            """Serve the list of available images as JSON."""
            images = get_image_files(image_dir)
            content = json.dumps(images).encode('utf-8')
            self.send_response_headers(200, 'application/json', len(content))
            self.wfile.write(content)
        
        def serve_image(self, filename):
            """Serve an individual image file."""
            # Security: prevent directory traversal
            filename = os.path.basename(filename)
            filepath = os.path.join(image_dir, filename)
            
            if not os.path.isfile(filepath):
                self.send_error(404, 'Image not found')
                return
            
            # Check if it's a valid image extension
            ext = os.path.splitext(filename)[1].lower()
            if ext not in IMAGE_EXTENSIONS:
                self.send_error(403, 'Not an allowed image type')
                return
            
            # Get MIME type
            mime_type, _ = mimetypes.guess_type(filepath)
            if mime_type is None:
                mime_type = 'application/octet-stream'
            
            # Read and serve the file
            try:
                with open(filepath, 'rb') as f:
                    content = f.read()
                self.send_response_headers(200, mime_type, len(content))
                self.wfile.write(content)
            except IOError as e:
                self.send_error(500, f'Error reading file: {e}')
    
    return PhotoFrameHandler


def run_server(image_dir, port=8000, interval=5):
    """
    Start the photo frame server.
    
    Args:
        image_dir: Path to directory containing images
        port: Server port (default 8000)
        interval: Seconds between images (default 5)
    """
    # Convert interval to milliseconds for JavaScript
    interval_ms = interval * 1000
    
    # Validate image directory
    if not os.path.isdir(image_dir):
        print(f"Error: '{image_dir}' is not a valid directory")
        return 1
    
    # Get initial image count
    images = get_image_files(image_dir)
    print(f"Found {len(images)} image(s) in '{image_dir}'")
    
    if len(images) == 0:
        print("Warning: No images found. Add images to the directory.")
    
    # Create and start the server
    handler = create_handler(image_dir, interval_ms)
    server = HTTPServer(('', port), handler)
    
    print(f"Photo Frame Server running at http://localhost:{port}")
    print(f"Slideshow interval: {interval} seconds")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()
    
    return 0
