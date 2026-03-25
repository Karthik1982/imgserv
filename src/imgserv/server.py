"""
Photo Frame Web Server

A simple HTTP server that serves images from a directory as an auto-advancing slideshow.
"""

import os
import json
import mimetypes
import time
import ssl
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote, quote
try:
    from urllib.request import urlopen, Request
    from urllib.error import URLError
except ImportError:
    from urllib2 import urlopen, URLError, Request

# Optional CA bundle fallback for macOS/python.org installs
try:
    import certifi
except ImportError:
    certifi = None

# Try to import Pillow for EXIF reading
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# Supported image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

# Weather cache (to avoid excessive API calls)
weather_cache = {
    'data': None,
    'timestamp': 0
}
WEATHER_CACHE_DURATION = 600  # 10 minutes in seconds
weather_last_error = None

# Metadata cache (to avoid re-reading EXIF for same image)
metadata_cache = {}


def safe_urlopen(url, timeout, headers=None):
    """Open URLs with default TLS verification and certifi fallback."""
    request_obj = Request(url, headers=headers or {}) if headers else url
    try:
        return urlopen(request_obj, timeout=timeout)
    except Exception as e:
        # If certificate validation fails and certifi exists, retry with its CA bundle.
        if certifi and "CERTIFICATE_VERIFY_FAILED" in str(e):
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            try:
                return urlopen(request_obj, timeout=timeout, context=ssl_context)
            except TypeError:
                # Python 2 urllib2 doesn't support SSL context argument.
                pass
        raise


def convert_gps_to_decimal(gps_coords, gps_ref):
    """Convert GPS coordinates from EXIF format to decimal degrees."""
    try:
        degrees = float(gps_coords[0])
        minutes = float(gps_coords[1])
        seconds = float(gps_coords[2])
        
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        
        if gps_ref in ['S', 'W']:
            decimal = -decimal
        
        return decimal
    except (TypeError, IndexError, ValueError):
        return None


def reverse_geocode(lat, lon):
    """Reverse geocode coordinates to location name using OpenStreetMap Nominatim."""
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=jsonv2&lat={lat}&lon={lon}&zoom=10&addressdetails=1"
        )
        headers = {
            "User-Agent": "imgserv/0.1 (+https://localhost)",
            "Accept-Language": "en"
        }
        response = safe_urlopen(url, timeout=5, headers=headers)
        data = json.loads(response.read().decode('utf-8'))
        
        address = data.get('address', {})
        
        # Build location string from address components
        city = address.get('city') or address.get('town') or address.get('village') or address.get('hamlet')
        state = address.get('state')
        country = address.get('country')
        
        parts = []
        if city:
            parts.append(city)
        if state:
            parts.append(state)
        if not parts and country:
            parts.append(country)
        
        return ', '.join(parts) if parts else None
    except Exception:
        # If reverse geocoding fails, return coordinates
        return f"{lat:.4f}, {lon:.4f}"


def get_exif_data(filepath):
    """Extract date and GPS location from image EXIF metadata."""
    if not PILLOW_AVAILABLE:
        return {'date': None, 'location': None}
    
    # Check cache
    if filepath in metadata_cache:
        return metadata_cache[filepath]
    
    result = {'date': None, 'location': None}
    
    try:
        img = Image.open(filepath)
        exif_data = img._getexif()
        
        if exif_data:
            # Extract date taken (tag 36867 = DateTimeOriginal)
            date_taken = exif_data.get(36867)
            if date_taken:
                try:
                    # Parse EXIF date format "YYYY:MM:DD HH:MM:SS"
                    dt = datetime.strptime(date_taken, "%Y:%m:%d %H:%M:%S")
                    result['date'] = dt.strftime("%B %d, %Y")  # "January 15, 2024"
                except ValueError:
                    result['date'] = date_taken
            
            # Extract GPS info (tag 34853 = GPSInfo)
            gps_info = exif_data.get(34853)
            if gps_info:
                lat = None
                lon = None
                
                # GPS tags: 1=LatitudeRef, 2=Latitude, 3=LongitudeRef, 4=Longitude
                lat_ref = gps_info.get(1)
                lat_coords = gps_info.get(2)
                lon_ref = gps_info.get(3)
                lon_coords = gps_info.get(4)
                
                if lat_coords and lon_coords:
                    lat = convert_gps_to_decimal(lat_coords, lat_ref)
                    lon = convert_gps_to_decimal(lon_coords, lon_ref)
                
                if lat is not None and lon is not None:
                    result['location'] = reverse_geocode(lat, lon)
        
        img.close()
    except Exception as e:
        print(f"Error reading EXIF from {filepath}: {e}")
    
    # Cache the result
    metadata_cache[filepath] = result
    return result


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
        #photo-container {{
            position: relative;
            width: 100%;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
        }}
        img {{
            max-width: 100%;
            max-height: 100vh;
            object-fit: contain;
            position: relative;
            left: 0;
        }}
        .loading {{
            color: #fff;
            font-family: sans-serif;
            font-size: 24px;
        }}
        #clock {{
            position: fixed;
            bottom: 55px;
            left: 20px;
            color: #fff;
            font-family: 'Courier New', monospace;
            font-size: 32px;
            font-weight: bold;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
            z-index: 1000;
        }}
        #weather {{
            position: fixed;
            bottom: 20px;
            left: 20px;
            color: white;
            font-size: 20px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
            display: flex;
            align-items: center;
        }}
        #weather img {{
            width: 40px;
            height: 40px;
            vertical-align: middle;
            margin-right: 5px;
        }}
        #photo-metadata {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            color: #f8f8ff;
            text-shadow: 
                0 1px 0 rgba(255, 255, 255, 0.4),
                0 -1px 1px rgba(0, 0, 0, 0.3),
                2px 2px 4px rgba(0, 0, 0, 0.6);
            z-index: 1000;
            text-align: right;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-weight: 500;
            letter-spacing: 0.5px;
        }}
        #photo-metadata .meta-date {{
            font-size: 29px;
            margin-bottom: 5px;
        }}
        #photo-metadata .meta-location {{
            font-size: 24px;
            opacity: 0.95;
            color: #fff;
            font-family: sans-serif;
            font-size: 24px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
            z-index: 1000;
            display: flex;
            align-items: center;
        }}
        #weather img {{
            width: 40px;
            height: 40px;
            margin-right: 5px;
            filter: drop-shadow(2px 2px 2px rgba(0, 0, 0, 0.8));
        }}
        #sleep-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: #000;
            z-index: 998;
            display: none;
        }}
        .sleep-mode #clock {{
            position: fixed;
            top: 50%;
            left: 50%;
            bottom: auto;
            transform: translate(-50%, -50%);
            font-size: 144px;
            color: #9a9a9a;
            opacity: 1;
            z-index: 1001;
            text-align: center;
        }}
        .sleep-mode #weather {{
            position: fixed;
            top: calc(50% + 125px);
            left: 50%;
            bottom: auto;
            transform: translateX(-50%);
            display: flex;
            justify-content: center;
            font-size: 42px;
            color: #8f8f8f;
            z-index: 1001;
            text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.7);
        }}
        .sleep-mode #weather img {{
            width: 52px;
            height: 52px;
            margin-right: 8px;
            filter: grayscale(100%) brightness(0.65);
        }}
        .sleep-mode #photo-metadata {{
            display: none;
        }}
        .sleep-mode #photo-container {{
            display: none !important;
        }}
        .sleep-mode #loading {{
            display: none !important;
        }}
    </style>
</head>
<body>
    <div id="sleep-overlay"></div>
    <div id="loading" class="loading">Loading images...</div>
    <div id="photo-container" style="display:none;">
        <img id="photo" src="" alt="Photo">
    </div>
    <div id="clock"></div>
    <div id="weather"></div>
    <div id="photo-metadata"></div>
    <script>
        // Weather display
        function updateWeather() {{
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/weather', true);
            xhr.onreadystatechange = function() {{
                if (xhr.readyState === 4 && xhr.status === 200) {{
                    var data = JSON.parse(xhr.responseText);
                    if (data.temp !== undefined) {{
                        var html = '';
                        if (data.icon) {{
                            var iconUrl = 'https://openweathermap.org/img/wn/' + data.icon + '@2x.png';
                            html += '<img src="' + iconUrl + '" alt="weather" onerror="this.style.display=&quot;none&quot;">';
                        }}
                        html += data.temp + '°F ' + data.description;
                        document.getElementById('weather').innerHTML = html;
                    }}
                }}
            }};
            xhr.send();
        }}
        updateWeather();
        setInterval(updateWeather, 600000);  // Update every 10 minutes
        
        // Photo metadata display
        function updateMetadata(filename) {{
            var metadataDiv = document.getElementById('photo-metadata');
            if (!filename) {{
                metadataDiv.innerHTML = '';
                return;
            }}
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/metadata/' + encodeURIComponent(filename), true);
            xhr.onreadystatechange = function() {{
                if (xhr.readyState === 4 && xhr.status === 200) {{
                    var data = JSON.parse(xhr.responseText);
                    var html = '';
                    if (data.date) {{
                        html += '<div class="meta-date">' + data.date + '</div>';
                    }}
                    if (data.location) {{
                        html += '<div class="meta-location">' + data.location + '</div>';
                    }}
                    metadataDiv.innerHTML = html;
                }}
            }};
            xhr.send();
        }}
        
        // Digital clock (12-hour format)
        function updateClock() {{
            var now = new Date();
            var hours = now.getHours();
            var minutes = now.getMinutes();
            var ampm = hours >= 12 ? 'PM' : 'AM';
            
            // Convert to 12-hour format
            hours = hours % 12;
            if (hours === 0) hours = 12;
            
            // Pad with leading zeros
            if (hours < 10) hours = '0' + hours;
            if (minutes < 10) minutes = '0' + minutes;
            
            document.getElementById('clock').innerHTML = hours + ':' + minutes + ' ' + ampm;
        }}
        updateClock();
        setInterval(updateClock, 1000);
        
        // Sleep mode check
        var isSleeping = false;
        
        function timeToMinutes(timeStr) {{
            var parts = timeStr.split(':');
            return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
        }}
        
        function isInSleepWindow(currentTime, sleepStart, sleepEnd) {{
            var current = timeToMinutes(currentTime);
            var start = timeToMinutes(sleepStart);
            var end = timeToMinutes(sleepEnd);
            
            // If start equals end, sleep mode is disabled
            if (start === end) return false;
            
            // Handle overnight sleep (e.g., 23:00 to 06:00)
            if (start > end) {{
                return current >= start || current < end;
            }} else {{
                return current >= start && current < end;
            }}
        }}
        
        function checkSleepMode() {{
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/api/schedule', true);
            xhr.onreadystatechange = function() {{
                if (xhr.readyState === 4 && xhr.status === 200) {{
                    var data = JSON.parse(xhr.responseText);
                    var shouldSleep = isInSleepWindow(data.server_time, data.sleep_start, data.sleep_end);
                    
                    if (shouldSleep && !isSleeping) {{
                        // Enter sleep mode
                        isSleeping = true;
                        document.body.classList.add('sleep-mode');
                        document.getElementById('sleep-overlay').style.display = 'block';
                    }} else if (!shouldSleep && isSleeping) {{
                        // Exit sleep mode
                        isSleeping = false;
                        document.body.classList.remove('sleep-mode');
                        document.getElementById('sleep-overlay').style.display = 'none';
                    }}
                }}
            }};
            xhr.send();
        }}
        
        checkSleepMode();
        setInterval(checkSleepMode, 60000);  // Check every minute
    </script>
    <script>
        var interval = {interval};
        var isFirstImage = true;
        var shuffledImages = [];
        var shuffleIndex = 0;
        var lastServerImages = [];
        var isLegacyIE = !!(document.documentMode && document.documentMode < 9) ||
            /MSIE [1-8]\./.test(navigator.userAgent);
        var effects = ['fade', 'slideLeft', 'zoomIn', 'flip'];
        if (isLegacyIE) {{
            // IE8 is flaky with width/position-heavy transitions and cached image onload events.
            effects = ['fade'];
        }}
        
        // Helper: Set opacity (cross-browser)
        function setOpacity(element, value) {{
            element.style.opacity = value / 100;
            element.style.filter = 'alpha(opacity=' + value + ')';
        }}
        
        // Helper: Set scale using width percentage (cross-browser)
        function setScale(element, value, originalWidth) {{
            if (originalWidth) {{
                element.style.width = (originalWidth * value / 100) + 'px';
            }}
        }}
        
        // Fisher-Yates shuffle algorithm
        function shuffleArray(array) {{
            var arr = array.slice();
            for (var i = arr.length - 1; i > 0; i--) {{
                var j = Math.floor(Math.random() * (i + 1));
                var temp = arr[i];
                arr[i] = arr[j];
                arr[j] = temp;
            }}
            return arr;
        }}
        
        // Check if arrays are equal
        function arraysEqual(a, b) {{
            if (a.length !== b.length) return false;
            for (var i = 0; i < a.length; i++) {{
                if (a[i] !== b[i]) return false;
            }}
            return true;
        }}
        
        // Get random effect
        function getRandomEffect() {{
            return effects[Math.floor(Math.random() * effects.length)];
        }}

        function resetPhotoStyles(photo) {{
            photo.style.left = '0';
            photo.style.width = '';
            setOpacity(photo, 100);
        }}

        function loadImageRobust(photo, src, onReady) {{
            var finished = false;
            var timeoutMs = isLegacyIE ? 6000 : 4000;
            var timer = setTimeout(function() {{
                if (finished) return;
                finished = true;
                photo.onload = null;
                photo.onerror = null;
                photo.onreadystatechange = null;
                onReady(false);
            }}, timeoutMs);

            function done(success) {{
                if (finished) return;
                finished = true;
                clearTimeout(timer);
                photo.onload = null;
                photo.onerror = null;
                photo.onreadystatechange = null;
                onReady(success);
            }}

            photo.onload = function() {{
                done(true);
            }};
            photo.onerror = function() {{
                done(false);
            }};
            photo.onreadystatechange = function() {{
                if (photo.readyState === 'loaded' || photo.readyState === 'complete') {{
                    done(true);
                }}
            }};

            // Ensure event handlers are attached before src changes.
            photo.src = src;
        }}
        
        // Effect: Fade Out
        function fadeOut(element, callback) {{
            var opacity = 100;
            var timer = setInterval(function() {{
                opacity -= 5;
                if (opacity <= 0) {{
                    clearInterval(timer);
                    setOpacity(element, 0);
                    if (callback) callback();
                }} else {{
                    setOpacity(element, opacity);
                }}
            }}, 50);
        }}
        
        // Effect: Fade In
        function fadeIn(element, callback) {{
            var opacity = 0;
            var timer = setInterval(function() {{
                opacity += 5;
                if (opacity >= 100) {{
                    clearInterval(timer);
                    setOpacity(element, 100);
                    if (callback) callback();
                }} else {{
                    setOpacity(element, opacity);
                }}
            }}, 50);
        }}
        
        // Effect: Slide Left Out (slide to left)
        function slideLeftOut(element, callback) {{
            var pos = 0;
            var timer = setInterval(function() {{
                pos -= 5;
                if (pos <= -100) {{
                    clearInterval(timer);
                    element.style.left = '-100%';
                    setOpacity(element, 0);
                    if (callback) callback();
                }} else {{
                    element.style.left = pos + '%';
                }}
            }}, 25);
        }}
        
        // Effect: Slide Left In (slide from right)
        function slideLeftIn(element, callback) {{
            element.style.left = '100%';
            setOpacity(element, 100);
            var pos = 100;
            var timer = setInterval(function() {{
                pos -= 5;
                if (pos <= 0) {{
                    clearInterval(timer);
                    element.style.left = '0';
                    if (callback) callback();
                }} else {{
                    element.style.left = pos + '%';
                }}
            }}, 25);
        }}
        
        // Effect: Zoom Out (shrink)
        function zoomOut(element, callback) {{
            var scale = 100;
            var origWidth = element.offsetWidth;
            var timer = setInterval(function() {{
                scale -= 5;
                if (scale <= 0) {{
                    clearInterval(timer);
                    element.style.width = '';
                    setOpacity(element, 0);
                    if (callback) callback();
                }} else {{
                    setScale(element, scale, origWidth);
                    setOpacity(element, scale);
                }}
            }}, 40);
        }}
        
        // Effect: Zoom In (grow)
        function zoomIn(element, callback) {{
            setOpacity(element, 0);
            element.style.width = '0';
            var scale = 0;
            var targetWidth = null;
            var timer = setInterval(function() {{
                if (targetWidth === null) {{
                    element.style.width = '';
                    targetWidth = element.offsetWidth;
                    element.style.width = '0';
                }}
                scale += 5;
                if (scale >= 100) {{
                    clearInterval(timer);
                    element.style.width = '';
                    setOpacity(element, 100);
                    if (callback) callback();
                }} else {{
                    setScale(element, scale, targetWidth);
                    setOpacity(element, scale);
                }}
            }}, 40);
        }}
        
        // Effect: Flip Out (squeeze horizontally)
        function flipOut(element, callback) {{
            var scale = 100;
            var origWidth = element.offsetWidth;
            var timer = setInterval(function() {{
                scale -= 10;
                if (scale <= 0) {{
                    clearInterval(timer);
                    element.style.width = '0';
                    if (callback) callback();
                }} else {{
                    setScale(element, scale, origWidth);
                }}
            }}, 30);
        }}
        
        // Effect: Flip In (expand horizontally)
        function flipIn(element, callback) {{
            element.style.width = '0';
            setOpacity(element, 100);
            var scale = 0;
            var targetWidth = null;
            var timer = setInterval(function() {{
                if (targetWidth === null) {{
                    element.style.width = '';
                    targetWidth = element.offsetWidth;
                    element.style.width = '0';
                }}
                scale += 10;
                if (scale >= 100) {{
                    clearInterval(timer);
                    element.style.width = '';
                    if (callback) callback();
                }} else {{
                    setScale(element, scale, targetWidth);
                }}
            }}, 30);
        }}
        
        // Apply transition out based on effect type
        function transitionOut(element, effect, callback) {{
            if (effect === 'fade') {{
                fadeOut(element, callback);
            }} else if (effect === 'slideLeft') {{
                slideLeftOut(element, callback);
            }} else if (effect === 'zoomIn') {{
                zoomOut(element, callback);
            }} else if (effect === 'flip') {{
                flipOut(element, callback);
            }} else {{
                fadeOut(element, callback);
            }}
        }}
        
        // Apply transition in based on effect type
        function transitionIn(element, effect, callback) {{
            if (effect === 'fade') {{
                fadeIn(element, callback);
            }} else if (effect === 'slideLeft') {{
                slideLeftIn(element, callback);
            }} else if (effect === 'zoomIn') {{
                zoomIn(element, callback);
            }} else if (effect === 'flip') {{
                flipIn(element, callback);
            }} else {{
                fadeIn(element, callback);
            }}
        }}
        
        // Get next image from shuffled list
        function getNextImage(serverImages) {{
            // Check if server images changed
            if (!arraysEqual(serverImages, lastServerImages)) {{
                lastServerImages = serverImages.slice();
                shuffledImages = shuffleArray(serverImages);
                shuffleIndex = 0;
            }}
            
            // If we've shown all images, reshuffle
            if (shuffleIndex >= shuffledImages.length) {{
                shuffledImages = shuffleArray(serverImages);
                shuffleIndex = 0;
            }}
            
            var img = shuffledImages[shuffleIndex];
            shuffleIndex++;
            return img;
        }}
        
        function fetchAndShow() {{
            var xhr = new XMLHttpRequest();
            var nextScheduled = false;
            function scheduleNext(delay) {{
                if (nextScheduled) return;
                nextScheduled = true;
                setTimeout(fetchAndShow, delay || interval);
            }}

            xhr.open('GET', '/api/images', true);
            xhr.timeout = 10000;
            xhr.onreadystatechange = function() {{
                if (xhr.readyState !== 4) return;

                if (xhr.status === 200) {{
                    try {{
                        var images = JSON.parse(xhr.responseText);
                        if (images.length > 0) {{
                            document.getElementById('loading').style.display = 'none';
                            var container = document.getElementById('photo-container');
                            var photo = document.getElementById('photo');
                            container.style.display = 'flex';
                            
                            var nextImage = getNextImage(images);
                            var effect = getRandomEffect();
                            
                            if (isFirstImage) {{
                                setOpacity(photo, 0);
                                resetPhotoStyles(photo);
                                loadImageRobust(photo, '/image/' + encodeURIComponent(nextImage), function(success) {{
                                    if (success) {{
                                        transitionIn(photo, effect);
                                    }} else {{
                                        // Fall back to visible image state even if load signaling is flaky.
                                        setOpacity(photo, 100);
                                    }}
                                }});
                                updateMetadata(nextImage);
                                isFirstImage = false;
                                scheduleNext(interval);
                            }} else {{
                                transitionOut(photo, effect, function() {{
                                    resetPhotoStyles(photo);
                                    loadImageRobust(photo, '/image/' + encodeURIComponent(nextImage), function(success) {{
                                        if (success) {{
                                            transitionIn(photo, effect);
                                        }} else {{
                                            setOpacity(photo, 100);
                                        }}
                                    }});
                                    updateMetadata(nextImage);
                                    scheduleNext(interval);
                                }});
                            }}
                        }} else {{
                            document.getElementById('loading').style.display = 'block';
                            document.getElementById('photo-container').style.display = 'none';
                            document.getElementById('loading').innerHTML = 'No images found';
                            scheduleNext(interval);
                        }}
                    }} catch (e) {{
                        scheduleNext(3000);
                    }}
                }} else {{
                    scheduleNext(3000);
                }}
            }};
            xhr.onerror = function() {{
                scheduleNext(3000);
            }};
            xhr.ontimeout = function() {{
                scheduleNext(3000);
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


def fetch_weather(api_key, city):
    """Fetch weather data from OpenWeather API with caching."""
    global weather_cache, weather_last_error
    
    # Check cache
    current_time = time.time()
    if weather_cache['data'] and (current_time - weather_cache['timestamp']) < WEATHER_CACHE_DURATION:
        weather_last_error = None
        return weather_cache['data']
    
    # Fetch from API
    try:
        encoded_city = quote(city)
        url = f"https://api.openweathermap.org/data/2.5/weather?q={encoded_city}&appid={api_key}&units=imperial"
        response = safe_urlopen(url, timeout=10)
        data = json.loads(response.read().decode('utf-8'))
        
        # Extract relevant data
        weather_data = {
            'temp': round(data['main']['temp']),
            'description': data['weather'][0]['main'],
            'icon': data['weather'][0]['icon'],
            'city': data['name']
        }
        
        # Update cache
        weather_cache['data'] = weather_data
        weather_cache['timestamp'] = current_time
        weather_last_error = None
        
        return weather_data
    except Exception as e:
        error_message = str(e)
        weather_last_error = error_message
        print(f"Weather API error: {error_message}")
        # Return cached data if available, even if expired
        if weather_cache['data']:
            return weather_cache['data']
        return None


def create_handler(image_dir, interval_ms, weather_api_key=None, city=None, sleep_start='23:00', sleep_end='06:00'):
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
            elif path == '/api/weather':
                self.serve_weather()
            elif path == '/api/schedule':
                self.serve_schedule()
            elif path.startswith('/api/metadata/'):
                filename = path[14:]  # Remove '/api/metadata/' prefix
                self.serve_metadata(filename)
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
        
        def serve_weather(self):
            """Serve current weather data as JSON."""
            if not weather_api_key or not city:
                content = json.dumps({
                    'error': 'Weather not configured',
                    'code': 'weather_not_configured',
                    'message': 'Set OPENWEATHER_API_KEY and --city to enable weather.'
                }).encode('utf-8')
                self.send_response_headers(200, 'application/json', len(content))
                self.wfile.write(content)
                return
            
            weather_data = fetch_weather(weather_api_key, city)
            if weather_data:
                content = json.dumps(weather_data).encode('utf-8')
                self.send_response_headers(200, 'application/json', len(content))
                self.wfile.write(content)
            else:
                details = weather_last_error or 'Unknown upstream error'
                hint = None
                if 'CERTIFICATE_VERIFY_FAILED' in details:
                    hint = 'TLS certificate validation failed. Install system/ Python CA certificates or use certifi.'

                content = json.dumps({
                    'error': 'Failed to fetch weather',
                    'code': 'weather_fetch_failed',
                    'message': 'Could not retrieve weather from OpenWeather.',
                    'details': details,
                    'hint': hint
                }).encode('utf-8')
                self.send_response_headers(500, 'application/json', len(content))
                self.wfile.write(content)
        
        def serve_schedule(self):
            """Serve sleep schedule and current server time as JSON."""
            now = datetime.now()
            server_time = now.strftime('%H:%M')
            
            schedule_data = {
                'sleep_start': sleep_start,
                'sleep_end': sleep_end,
                'server_time': server_time
            }
            content = json.dumps(schedule_data).encode('utf-8')
            self.send_response_headers(200, 'application/json', len(content))
            self.wfile.write(content)
        
        def serve_metadata(self, filename):
            """Serve EXIF metadata for a specific image as JSON."""
            # Security: prevent directory traversal
            filename = os.path.basename(filename)
            filepath = os.path.join(image_dir, filename)
            
            if not os.path.exists(filepath):
                self.send_error(404, 'Image not found')
                return
            
            metadata = get_exif_data(filepath)
            content = json.dumps(metadata).encode('utf-8')
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


def run_server(image_dir, port=8000, interval=5, weather_api_key=None, city=None,
               sleep_start='23:00', sleep_end='06:00'):
    """
    Start the photo frame server.
    
    Args:
        image_dir: Path to directory containing images
        port: Server port (default 8000)
        interval: Seconds between images (default 5)
        weather_api_key: OpenWeather API key (optional)
        city: City name for weather display (optional)
        sleep_start: Sleep mode start time in HH:MM format (default 23:00)
        sleep_end: Sleep mode end time in HH:MM format (default 06:00)
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
    handler = create_handler(image_dir, interval_ms, weather_api_key, city, sleep_start, sleep_end)
    server = HTTPServer(('', port), handler)
    
    print(f"Photo Frame Server running at http://localhost:{port}")
    print(f"Slideshow interval: {interval} seconds")
    if weather_api_key and city:
        print(f"Weather enabled for: {city}")
    if sleep_start != sleep_end:
        print(f"Sleep mode: {sleep_start} to {sleep_end}")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()
    
    return 0
