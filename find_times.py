import cv2
import numpy as np
import easyocr
import re
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

def extract_text(image_path):
    reader = easyocr.Reader(['en'])

    # Read text from image 
    results = reader.readtext(image_path)

    text_regions = []
    for (bbox, text, confidence) in results:
        # bbox contains corner points
        x1 = min(point[0] for point in bbox)
        y1 = min(point[1] for point in bbox)
        x2 = max(point[0] for point in bbox)
        y2 = max(point[1] for point in bbox)

        text_regions.append({
            'text': text,
            'bbox': (x1, y1, x2, y2),
            'confidence': confidence
        })

    return text_regions

def identify_grid_structure(text_regions):
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    day_columns = {}
    time_rows = {}

    for region in text_regions:
        text = region['text']
        x1, y1, x2, y2 = region['bbox']
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2

        # Check for day headers
        for day in days:
            if day.lower() in text.lower():
                day_columns[day] = center_x

        # Check for time indicators
        # Match patterns like "9am", "9 am", "12pm", "12 pm"
        time_pattern = r'(\d{1,2})\s*(am|pm)'
        match = re.search(time_pattern, text, re.IGNORECASE)
        if match:
            hour_str = match.group(1)
            # Skip if this looks like it might be malformed (e.g., "1 0" interpreted as "1")
            if hour_str in ['0']:
                continue
            hour = int(hour_str)
            if hour > 12:  # Invalid hour for 12-hour format
                continue
            period = match.group(2).upper()
            time_str = f"{hour}:00 {period}"
            # Only keep the first occurrence of each time (avoid duplicates)
            if time_str not in time_rows:
                time_rows[time_str] = center_y

    # Sort by position
    day_columns = dict(sorted(day_columns.items(), key=lambda x: x[1]))
    time_rows = dict(sorted(time_rows.items(), key=lambda x: x[1]))

    return {'days': day_columns, 'times': time_rows}

def extract_classes(text_regions, grid):
    classes = []

    #[Any A-Z character] 4 times; [space] one or more; [1-9 character] 4 times
    course_pattern = re.compile(r'[A-Z]{4}\s*\d{4}')

    for region in text_regions:
        text = region['text']
        x1, y1, x2, y2 = region['bbox']
        confidence = region.get('confidence', 1.0)

        # Check if this is a course code (with lower confidence threshold to catch all courses)
        if course_pattern.search(text) and confidence > 0.4:
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2

            # Find which day column this belongs to
            day = find_closest_day(center_x, grid['days'])

            # Determine class type by looking for nearby text
            class_type = find_class_type(center_x, center_y, text_regions)

            # Find time range based on vertical position and class type
            start_time, end_time = find_time_range(y1, y2, grid['times'], class_type)

            if day and start_time:
                classes.append({
                    'course': text.strip(),
                    'day': day,
                    'start_time': start_time,
                    'end_time': end_time,
                    'type': class_type
                })

    return classes

def find_class_type(course_x, course_y, text_regions, threshold=100):
    """
    Find the class type (Lecture, Lab, Tutorial) by looking for nearby text
    """
    for region in text_regions:
        text = region['text'].lower()
        x1, y1, x2, y2 = region['bbox']
        region_x = (x1 + x2) // 2
        region_y = (y1 + y2) // 2

        # Check if this text is close to the course code
        if abs(region_x - course_x) < threshold and abs(region_y - course_y) < threshold:
            if 'lecture' in text:
                return 'Lecture'
            elif 'lab' in text or 'laboratory' in text:
                return 'Laboratory'
            elif 'tutorial' in text:
                return 'Tutorial'

    return 'Lecture'  # Default to Lecture if not specified

def find_closest_day(center_x, day_columns, threshold=150):
    """
    Find which day column a class belongs to

    If distance between center of x coordinate of bounding box is less than 150 pixels from the x position of the day column,
    then it is assigned that day. 
    """
    for day, col_x in day_columns.items():
        if abs(center_x - col_x) < threshold:
            return day
        
    return None

def add_minutes_to_time(time_str, minutes):
    """Add minutes to a time string like '9:00 AM'"""
    import re
    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str)
    if not match:
        return time_str

    hour = int(match.group(1))
    minute = int(match.group(2))
    period = match.group(3)

    # Convert to 24-hour format
    if period == 'PM' and hour != 12:
        hour += 12
    elif period == 'AM' and hour == 12:
        hour = 0

    # Add minutes
    total_minutes = hour * 60 + minute + minutes
    new_hour = (total_minutes // 60) % 24
    new_minute = total_minutes % 60

    # Convert back to 12-hour format
    if new_hour == 0:
        display_hour = 12
        new_period = 'AM'
    elif new_hour < 12:
        display_hour = new_hour
        new_period = 'AM'
    elif new_hour == 12:
        display_hour = 12
        new_period = 'PM'
    else:
        display_hour = new_hour - 12
        new_period = 'PM'

    return f"{display_hour}:{new_minute:02d} {new_period}"

def find_time_range(y_start, y_end, time_rows, class_type='Lecture'):
    """Determine start and end based on vertical position and class type"""
    if not time_rows:
        return None, None

    sorted_times = sorted(time_rows.items(), key=lambda x: x[1])

    # Find the closest time to the top of the bounding box (start time)
    start_time = None
    start_idx = 0
    min_dist = float('inf')
    for idx, (time, y_pos) in enumerate(sorted_times):
        dist = abs(y_pos - y_start)
        if dist < min_dist:
            min_dist = dist
            start_time = time
            start_idx = idx

    # Find the closest time to the bottom of the bounding box (end time)
    end_time = None
    min_dist = float('inf')
    for time, y_pos in sorted_times:
        dist = abs(y_pos - y_end)
        if dist < min_dist:
            min_dist = dist
            end_time = time

    # Calculate proper end time based on class type
    if class_type == 'Lecture':
        # Lecture is 1.5 hours (90 minutes)
        calculated_end = add_minutes_to_time(start_time, 90)
    else:  # Laboratory or Tutorial
        # Lab/Tutorial is 1 hour (60 minutes)
        calculated_end = add_minutes_to_time(start_time, 60)

    # Use calculated end time (unless we detected a significantly different end time from bounding box)
    # Ensures consistency, lectures are always 1.5h, labs/tutorials are always 1h
    return start_time, calculated_end

if __name__ == "__main__":
    schedule = "schedules/schedule1.png"
    text_regions = extract_text(schedule)
    grid = identify_grid_structure(text_regions)
    classes = extract_classes(text_regions, grid)
    print(f"Found {len(classes)} classes:\n")
    for cls in classes:
        print(f"  {cls['course']:15} {cls['type']:12} {cls['day']:5} {cls['start_time']:10} - {cls['end_time']}")