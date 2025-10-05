import easyocr
import re
from datetime import datetime, timedelta
import ssl
import cv2
import numpy as np
ssl._create_default_https_context = ssl._create_unverified_context

def detect_colored_blocks(image_path, debug=False):
    """Detect individual colored schedule blocks by unique colors"""
    img = cv2.imread(image_path)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Define color ranges for different class colors
    # Lower saturation threshold (30 instead of 50) to catch lighter/pastel colors
    color_ranges = [
        # Teal/Cyan (COMP)
        {'name': 'teal', 'lower': np.array([80, 30, 50]), 'upper': np.array([100, 255, 255])},
        # Blue
        {'name': 'blue', 'lower': np.array([100, 30, 50]), 'upper': np.array([130, 255, 255])},
        # Green
        {'name': 'green', 'lower': np.array([40, 30, 50]), 'upper': np.array([80, 255, 255])},
        # Yellow/Orange (MATH/ENTR)
        {'name': 'yellow', 'lower': np.array([20, 30, 50]), 'upper': np.array([40, 255, 255])},
        # Red/Pink
        {'name': 'red', 'lower': np.array([0, 30, 50]), 'upper': np.array([20, 255, 255])},
        # Purple
        {'name': 'purple', 'lower': np.array([130, 30, 50]), 'upper': np.array([160, 255, 255])},
    ]

    all_contours = []

    # Detect blocks for each color separately
    for color_range in color_ranges:
        mask = cv2.inRange(hsv, color_range['lower'], color_range['upper'])

        # Very light erosion to clean up edges without removing small blocks
        kernel = np.ones((2, 2), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=1)

        # Find contours for this color
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        all_contours.extend(contours)

    # Draw all contours on debug image
    if debug:
        debug_img = img.copy()
        all_blocks = []
        filtered_blocks = []

        for contour in all_contours:
            x, y, w, h = cv2.boundingRect(contour)
            all_blocks.append((x, y, w, h))

            # Draw all contours in red
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(debug_img, f'{w}x{h}', (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

            # Check if it passes filter
            if 150 < w < 300 and 80 < h < 350:
                filtered_blocks.append((x, y, w, h))
                # Draw filtered blocks in green
                cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 255, 0), 3)

        cv2.imwrite('debug_blocks.png', debug_img)

    blocks = []
    for contour in all_contours:
        x, y, w, h = cv2.boundingRect(contour)

        # If block is too wide (spans multiple columns), split it
        if w > 400 and 80 < h < 350:
            # This is likely multiple blocks merged horizontally
            # Split into ~210px wide segments
            num_blocks = round(w / 210)
            block_width = w // num_blocks

            for i in range(num_blocks):
                split_x = x + i * block_width
                # Keep full height for now - will be trimmed later if needed
                blocks.append({
                    'x1': split_x,
                    'y1': y,
                    'x2': split_x + block_width,
                    'y2': y + h,
                    'center_x': split_x + block_width // 2,
                    'center_y': y + h // 2,
                    'was_split': True  # Mark as horizontally split
                })
        # Normal sized block
        elif 150 < w < 300 and 80 < h < 350:
            blocks.append({
                'x1': x,
                'y1': y,
                'x2': x + w,
                'y2': y + h,
                'center_x': x + w // 2,
                'center_y': y + h // 2
            })

    return blocks

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
        # Match patterns like "9am", "9 am", "12pm", "12 pm", "11:30am", "11:30 am"
        time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)'
        match = re.search(time_pattern, text, re.IGNORECASE)
        if match:
            hour_str = match.group(1)
            minutes_str = match.group(2) if match.group(2) else "00"
            # Skip if this looks like it might be malformed (e.g., "1 0" interpreted as "1")
            if hour_str in ['0']:
                continue
            hour = int(hour_str)
            if hour > 12:  # Invalid hour for 12-hour format
                continue
            period = match.group(3).upper()
            time_str = f"{hour}:{minutes_str} {period}"
            # Only keep the first occurrence of each time (avoid duplicates)
            if time_str not in time_rows:
                time_rows[time_str] = center_y

    # Sort by position
    day_columns = dict(sorted(day_columns.items(), key=lambda x: x[1]))
    time_rows = dict(sorted(time_rows.items(), key=lambda x: x[1]))

    # Fill in missing hourly time markers by interpolation
    time_rows = fill_missing_hours(time_rows)

    return {'days': day_columns, 'times': time_rows}

def fill_missing_hours(time_rows):
    """Fill in missing hourly time markers based on detected ones"""
    if len(time_rows) < 2:
        return time_rows

    sorted_times = sorted(time_rows.items(), key=lambda x: x[1])

    # Calculate average pixels per hour using the shared function
    avg_pixels_per_hour = calculate_pixels_per_hour(sorted_times)

    if avg_pixels_per_hour == 0:
        return time_rows

    # Fill in missing hours between consecutive time markers
    filled_times = dict(time_rows)

    for i in range(len(sorted_times) - 1):
        time1_str, y1 = sorted_times[i]
        time2_str, y2 = sorted_times[i + 1]

        dt1 = datetime.strptime(time1_str, "%I:%M %p")
        dt2 = datetime.strptime(time2_str, "%I:%M %p")

        hour_diff = (dt2 - dt1).total_seconds() / 3600

        # If gap is more than 1 hour, fill in the missing hours
        if hour_diff > 1.5:
            current_time = dt1
            current_y = y1

            for _ in range(int(hour_diff)):
                current_time += timedelta(hours=1)
                current_y += avg_pixels_per_hour

                if current_time < dt2:
                    time_str = current_time.strftime('%I:%M %p')
                    if time_str not in filled_times:
                        filled_times[time_str] = current_y

    return dict(sorted(filled_times.items(), key=lambda x: x[1]))

def split_overlapping_blocks(text_regions, colored_blocks, course_pattern, sorted_times):
    """Split blocks that contain multiple vertically-stacked courses or trim horizontally-split blocks"""
    split_blocks = []

    for block in colored_blocks:
        # Find all course texts in this block
        courses_in_block = []
        for region in text_regions:
            if course_pattern.search(region['text']):
                x1, y1, x2, y2 = region['bbox']
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2

                if (block['x1'] <= center_x <= block['x2'] and
                    block['y1'] <= center_y <= block['y2']):
                    courses_in_block.append({
                        'text': region['text'],
                        'center_y': center_y,
                        'y1': y1,
                        'y2': y2,
                        'text_bbox': (x1, y1, x2, y2),
                        'center_x': center_x
                    })

        # If this block was horizontally split and contains only one course,
        # trim it vertically to fit just that course (with standard duration)
        if block.get('was_split') and len(courses_in_block) == 1:
            course = courses_in_block[0]

            # Find if there's a "Lecture" or "Tutorial" label near this course text
            class_type = find_class_type(
                (course['text_bbox'][0] + course['text_bbox'][2]) // 2,
                (course['text_bbox'][1] + course['text_bbox'][3]) // 2,
                text_regions
            ) if 'text_bbox' in course else 'Lecture'

            # Calculate expected block height based on standard class duration
            # Lectures are typically 1.5h (90min), tutorials/labs are 1h (60min)
            pixels_per_hour = calculate_pixels_per_hour(sorted_times) if sorted_times else 108
            is_lecture = class_type == 'Lecture'
            expected_duration_hours = 1.5 if is_lecture else 1.0
            expected_height = int(pixels_per_hour * expected_duration_hours)

            # Position block: text is typically in top 20% of block
            # So if text center is at y, block should start ~10% of block height above
            text_center_y = (course['y1'] + course['y2']) // 2
            trimmed_y1 = text_center_y - int(expected_height * 0.2)
            trimmed_y2 = trimmed_y1 + expected_height

            # Clamp to original block boundaries (don't extend beyond)
            trimmed_y1 = max(block['y1'], trimmed_y1)
            trimmed_y2 = min(block['y2'], trimmed_y2)

            split_blocks.append({
                'x1': block['x1'],
                'y1': trimmed_y1,
                'x2': block['x2'],
                'y2': trimmed_y2,
                'center_x': block['center_x'],
                'center_y': (trimmed_y1 + trimmed_y2) // 2
            })
            continue

        # If multiple courses of the SAME name in same block, split it
        if len(courses_in_block) > 1:
            # Check if they're the same course (e.g., "MATH 1505" lecture and tutorial)
            course_names = [c['text'] for c in courses_in_block]
            if len(set(course_names)) == 1:
                # Same course name - split block between them
                courses_in_block.sort(key=lambda x: x['center_y'])

                for i, course in enumerate(courses_in_block):
                    if i == 0:
                        # First course: from block top to midpoint with next
                        if i + 1 < len(courses_in_block):
                            split_y = (course['y2'] + courses_in_block[i+1]['y1']) // 2
                        else:
                            split_y = block['y2']

                        split_blocks.append({
                            'x1': block['x1'],
                            'y1': block['y1'],
                            'x2': block['x2'],
                            'y2': split_y,
                            'center_x': block['center_x'],
                            'center_y': (block['y1'] + split_y) // 2
                        })
                    elif i == len(courses_in_block) - 1:
                        # Last course: from previous split to block bottom
                        split_y = (courses_in_block[i-1]['y2'] + course['y1']) // 2

                        split_blocks.append({
                            'x1': block['x1'],
                            'y1': split_y,
                            'x2': block['x2'],
                            'y2': block['y2'],
                            'center_x': block['center_x'],
                            'center_y': (split_y + block['y2']) // 2
                        })
                    else:
                        # Middle courses: between adjacent courses
                        split_y_top = (courses_in_block[i-1]['y2'] + course['y1']) // 2
                        split_y_bottom = (course['y2'] + courses_in_block[i+1]['y1']) // 2

                        split_blocks.append({
                            'x1': block['x1'],
                            'y1': split_y_top,
                            'x2': block['x2'],
                            'y2': split_y_bottom,
                            'center_x': block['center_x'],
                            'center_y': (split_y_top + split_y_bottom) // 2
                        })
            else:
                # Different courses in same block - keep as is
                split_blocks.append(block)
        else:
            # Single course or no courses - keep as is
            split_blocks.append(block)

    return split_blocks

def extract_classes(text_regions, grid, colored_blocks):
    classes = []
    course_pattern = re.compile(r'(?!ORIE)[A-Z]{4}\s*\d{4}')
    sorted_times = sorted(grid['times'].items(), key=lambda x: x[1])

    # Split blocks that contain multiple vertically-stacked courses
    split_blocks = split_overlapping_blocks(text_regions, colored_blocks, course_pattern, sorted_times)

    # Process each course code found in text
    for region in text_regions:
        text = region['text']
        x1, y1, x2, y2 = region['bbox']
        confidence = region.get('confidence', 1.0)

        if course_pattern.search(text) and confidence > 0.4:
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2

            # Find which day column this belongs to
            day = find_closest_day(center_x, grid['days'])

            # Determine class type
            class_type = find_class_type(center_x, center_y, text_regions)

            # Find the colored block that contains this text
            containing_block = None
            for block in split_blocks:
                if (block['x1'] <= center_x <= block['x2'] and
                    block['y1'] <= center_y <= block['y2']):
                    containing_block = block
                    break

            if containing_block:
                # Detect block duration and round to standard time slots
                # Blocks show actual time minus 10min buffer, we display full slot
                block_height = containing_block['y2'] - containing_block['y1']
                pixels_per_hour = calculate_pixels_per_hour(sorted_times)

                if pixels_per_hour > 0:
                    actual_hours = block_height / pixels_per_hour

                    # Round to standard durations:
                    # Blocks show actual time minus 10min buffer
                    # ~1.2-1.3h (70-80min actual) -> 1.5h (90min)
                    # ~1.7-1.8h (100-110min actual) -> 2.0h (120min)
                    # ~2.7-2.8h (160-170min actual) -> 3.0h (180min)
                    if actual_hours < 1.0:
                        duration_minutes = 60
                    elif actual_hours < 1.6:
                        duration_minutes = 90
                    elif actual_hours < 2.5:
                        duration_minutes = 120
                    else:
                        duration_minutes = 180
                else:
                    duration_minutes = 90 if class_type == 'Lecture' else 60

                # Start time from block top
                start_time = interpolate_time(containing_block['y1'], sorted_times)
                end_time = add_minutes_to_time(start_time, duration_minutes)
            else:
                # Fallback: use default duration
                start_time = interpolate_time(y1, sorted_times)
                duration = 90 if class_type == 'Lecture' else 60
                end_time = add_minutes_to_time(start_time, duration)

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
    dt_object = datetime.strptime(time_str, "%I:%M %p")
    new_dt_object = dt_object + timedelta(minutes=minutes)
    return new_dt_object.strftime('%I:%M %p')

def calculate_pixels_per_hour(sorted_times):
    """Calculate average pixels per hour from time markers"""
    if len(sorted_times) < 2:
        return 0

    pixel_diffs = []
    for i in range(len(sorted_times) - 1):
        time1_str, y1 = sorted_times[i]
        time2_str, y2 = sorted_times[i + 1]

        dt1 = datetime.strptime(time1_str, "%I:%M %p")
        dt2 = datetime.strptime(time2_str, "%I:%M %p")

        hour_diff = (dt2 - dt1).total_seconds() / 3600
        if hour_diff > 0:
            pixels_per_hour = (y2 - y1) / hour_diff
            pixel_diffs.append(pixels_per_hour)

    return sum(pixel_diffs) / len(pixel_diffs) if pixel_diffs else 0

def interpolate_time(y_position, sorted_times):
    """Interpolate time based on vertical position between time markers"""
    # Find the two time markers that bracket this position
    for i in range(len(sorted_times) - 1):
        time1, y1 = sorted_times[i]
        time2, y2 = sorted_times[i + 1]

        if y1 <= y_position <= y2:
            # Calculate the fraction of distance between the two markers
            fraction = (y_position - y1) / (y2 - y1) if y2 != y1 else 0

            # Parse the times
            dt1 = datetime.strptime(time1, "%I:%M %p")
            dt2 = datetime.strptime(time2, "%I:%M %p")

            # Calculate the time difference in minutes
            time_diff = (dt2 - dt1).total_seconds() / 60

            # Interpolate the time
            minutes_to_add = fraction * time_diff
            interpolated_time = dt1 + timedelta(minutes=minutes_to_add)

            # Round to nearest standard start time (:00 or :30)
            # Classes typically start on the hour or half-hour
            minute = interpolated_time.minute
            if minute < 15:
                rounded_minute = 0
            elif minute < 45:
                rounded_minute = 30
            else:
                rounded_minute = 0
                interpolated_time += timedelta(hours=1)

            interpolated_time = interpolated_time.replace(minute=rounded_minute, second=0, microsecond=0)
            return interpolated_time.strftime('%I:%M %p')

    # If position is before first marker or after last marker, use closest
    if y_position < sorted_times[0][1]:
        return sorted_times[0][0]
    else:
        return sorted_times[-1][0]

if __name__ == "__main__":
    schedule = "schedules/schedule2.png"
    colored_blocks = detect_colored_blocks(schedule, debug=False)
    text_regions = extract_text(schedule)
    grid = identify_grid_structure(text_regions)
    classes = extract_classes(text_regions, grid, colored_blocks)
    for cls in classes:
        print(f"  {cls['course']:15} {cls['type']:12} {cls['day']:5} {cls['start_time']:10} - {cls['end_time']}")