from find_times import detect_colored_blocks, extract_text, identify_grid_structure, extract_classes
from datetime import datetime
import glob
import pickle
import os

def parse_time(time_str):
    """Convert time string like '10:00 AM' to datetime object"""
    return datetime.strptime(time_str, "%I:%M %p")

def time_to_minutes(time_str):
    """Convert time string to minutes since midnight"""
    dt = parse_time(time_str)
    return dt.hour * 60 + dt.minute

def minutes_to_time(minutes):
    """Convert minutes since midnight to time string"""
    hours = minutes // 60
    mins = minutes % 60
    period = "AM" if hours < 12 else "PM"
    if hours == 0:
        hours = 12
    elif hours > 12:
        hours -= 12
    return f"{hours:02d}:{mins:02d} {period}"

def find_gaps_for_schedule(classes, min_gap_minutes=30):
    """Find free time gaps in a single schedule"""
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    gaps_by_day = {}

    for day in days:
        # Get all classes for this day
        day_classes = [c for c in classes if c['day'] == day]

        if not day_classes:
            # No classes this day - entire day is free (8 AM to 8 PM)
            gaps_by_day[day] = [{'start': '08:00 AM', 'end': '08:00 PM', 'duration_minutes': 720}]
            continue

        # Sort by start time
        day_classes.sort(key=lambda x: time_to_minutes(x['start_time']))

        gaps = []

        # Check gap from 8 AM to first class
        first_class_start = time_to_minutes(day_classes[0]['start_time'])
        morning_gap = first_class_start - time_to_minutes('08:00 AM')
        if morning_gap >= min_gap_minutes:
            gaps.append({
                'start': '08:00 AM',
                'end': day_classes[0]['start_time'],
                'duration_minutes': morning_gap
            })

        # Check gaps between classes
        for i in range(len(day_classes) - 1):
            current_end = time_to_minutes(day_classes[i]['end_time'])
            next_start = time_to_minutes(day_classes[i + 1]['start_time'])
            gap_duration = next_start - current_end

            if gap_duration >= min_gap_minutes:
                gaps.append({
                    'start': day_classes[i]['end_time'],
                    'end': day_classes[i + 1]['start_time'],
                    'duration_minutes': gap_duration
                })

        # Check gap from last class to 8 PM
        last_class_end = time_to_minutes(day_classes[-1]['end_time'])
        evening_gap = time_to_minutes('08:00 PM') - last_class_end
        if evening_gap >= min_gap_minutes:
            gaps.append({
                'start': day_classes[-1]['end_time'],
                'end': '08:00 PM',
                'duration_minutes': evening_gap
            })

        gaps_by_day[day] = gaps

    return gaps_by_day

def find_common_free_times(schedules_gaps, min_gap_minutes=30):
    """Find time slots that are free across ALL schedules"""
    if not schedules_gaps:
        return {}

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    common_gaps = {}

    for day in days:
        # Get all gap lists for this day across all schedules
        day_gaps_all_schedules = []
        for schedule_gaps in schedules_gaps:
            day_gaps_all_schedules.append(schedule_gaps.get(day, []))

        # Find intersection of all gaps for this day
        if not day_gaps_all_schedules:
            common_gaps[day] = []
            continue

        # Start with first schedule's gaps
        common_day_gaps = day_gaps_all_schedules[0][:]

        # Intersect with each subsequent schedule
        for other_gaps in day_gaps_all_schedules[1:]:
            new_common = []

            for gap1 in common_day_gaps:
                for gap2 in other_gaps:
                    # Find overlap between gap1 and gap2
                    start1 = time_to_minutes(gap1['start'])
                    end1 = time_to_minutes(gap1['end'])
                    start2 = time_to_minutes(gap2['start'])
                    end2 = time_to_minutes(gap2['end'])

                    # Calculate intersection
                    overlap_start = max(start1, start2)
                    overlap_end = min(end1, end2)
                    overlap_duration = overlap_end - overlap_start

                    if overlap_duration >= min_gap_minutes:
                        new_common.append({
                            'start': minutes_to_time(overlap_start),
                            'end': minutes_to_time(overlap_end),
                            'duration_minutes': overlap_duration
                        })

            common_day_gaps = new_common

        common_gaps[day] = common_day_gaps

    return common_gaps

def get_cached_classes(schedule_path, use_cache=True):
    """Get classes from cache or extract from image"""
    cache_path = schedule_path.replace('.png', '_cache.pkl')

    # Check if cache exists and is newer than the image
    if use_cache and os.path.exists(cache_path):
        image_mtime = os.path.getmtime(schedule_path)
        cache_mtime = os.path.getmtime(cache_path)

        if cache_mtime > image_mtime:
            with open(cache_path, 'rb') as f:
                # cache file saved after a file is loaded
                return pickle.load(f)

    # Extract classes (slow - uses OCR)
    colored_blocks = detect_colored_blocks(schedule_path, debug=False)
    text_regions = extract_text(schedule_path)
    grid = identify_grid_structure(text_regions)
    classes = extract_classes(text_regions, grid, colored_blocks)

    # Cache the results
    if use_cache:
        with open(cache_path, 'wb') as f:
            # uses eixsting cache file to improve proessing speed
            pickle.dump(classes, f)

    return classes

def process_schedules(schedule_paths, min_gap_minutes=30, use_cache=True):
    """Process multiple schedules and find common free times"""
    all_schedules_data = []
    all_gaps = []

    print(f"Processing {len(schedule_paths)} schedules...\n")

    for i, schedule_path in enumerate(schedule_paths, 1):
        print(f"[{i}/{len(schedule_paths)}] Processing {schedule_path}...", end='')

        # Get classes (cached if available)
        classes = get_cached_classes(schedule_path, use_cache)
        print(f" Found {len(classes)} classes")

        # Find gaps in this schedule
        gaps = find_gaps_for_schedule(classes, min_gap_minutes)
        all_gaps.append(gaps)
        all_schedules_data.append({
            'path': schedule_path,
            'classes': classes,
            'gaps': gaps
        })

    # Find common free times
    common_gaps = find_common_free_times(all_gaps, min_gap_minutes)

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    total_common_gaps = 0

    for day in days:
        day_gaps = common_gaps.get(day, [])
        if day_gaps:
            print(f"{day}:")
            for gap in day_gaps:
                hours = gap['duration_minutes'] // 60
                mins = gap['duration_minutes'] % 60
                duration_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                print(f"  {gap['start']:>10} - {gap['end']:<10}  ({duration_str})")
                total_common_gaps += 1
            print()

    if total_common_gaps == 0:
        print("No common free time slots found across all schedules.")
    else:
        print(f"\nTotal common free slots: {total_common_gaps}")

    return all_schedules_data, common_gaps

if __name__ == "__main__":
    # Find all schedules
    schedule_paths = sorted(glob.glob("schedules/*.png"))

    if not schedule_paths:
        print("No schedules found in schedules/ directory")
    else:
        # use_cache=True by default - caches OCR results for fast subsequent runs
        schedules_data, common_gaps = process_schedules(schedule_paths, min_gap_minutes=30, use_cache=True)
