"""
Schedule Free Time Finder - Simple Flask Backend
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import sys
import os

# Import our schedule processing functions
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from find_times import detect_colored_blocks, extract_text, identify_grid_structure, extract_classes
from find_free_times import find_common_free_times, find_gaps_for_schedule

app = Flask(__name__)
CORS(app)  # Allow frontend to call this API

# In-memory storage (replace with Supabase later)
groups = {}  # {invite_code: {"name": "...", "schedules": [...]}}


@app.route('/')
def home():
    """API home page"""
    return jsonify({
        "message": "Schedule Free Time Finder API",
        "endpoints": [
            "POST /api/groups - Create group",
            "POST /api/groups/<code>/upload - Upload schedule",
            "GET /api/groups/<code>/free-times - Get free times"
        ]
    })


@app.route('/api/groups', methods=['POST'])
def create_group():
    """Create a new group"""
    data = request.json
    group_name = data.get('name', 'Unnamed Group')

    # Generate simple invite code
    invite_code = f"group{len(groups) + 1}"

    # Store in memory
    groups[invite_code] = {
        "name": group_name,
        "schedules": []
    }

    # This will show in the terminal!
    print(f"Group created successfully! Name: '{group_name}', Code: {invite_code}")

    return jsonify({
        "invite_code": invite_code,
        "name": group_name
    }), 201


@app.route('/api/groups/<invite_code>/upload', methods=['POST'])
def upload_schedule(invite_code):
    """Upload a schedule to a group"""
    # Check group exists
    if invite_code not in groups:
        return jsonify({"error": "Group not found"}), 404

    # Get uploaded file
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    user_name = request.form.get('user_name', 'Anonymous')

    # Save temporarily and process
    temp_path = f"/tmp/schedule_{invite_code}_{user_name}.png"
    file.save(temp_path)

    try:
        print(f"Processing schedule upload for {user_name} in group {invite_code}...")

        # Process the image
        colored_blocks = detect_colored_blocks(temp_path, debug=False)
        text_regions = extract_text(temp_path)
        grid = identify_grid_structure(text_regions)
        classes = extract_classes(text_regions, grid, colored_blocks)

        # Store in memory (just the class data, not the image!)
        groups[invite_code]["schedules"].append({
            "user_name": user_name,
            "classes": classes
        })

        print(f"Schedule uploaded! User: {user_name}, Classes found: {len(classes)}")

        return jsonify({
            "message": "Schedule uploaded",
            "user_name": user_name,
            "num_classes": len(classes)
        }), 201

    finally:
        # Delete temp file for privacy
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route('/api/groups/<invite_code>/free-times', methods=['GET'])
def get_free_times(invite_code):
    """Get common free times for a group"""
    # Check group exists
    if invite_code not in groups:
        return jsonify({"error": "Group not found"}), 404

    group = groups[invite_code]

    # Get all schedules
    all_schedules = group["schedules"]

    if len(all_schedules) == 0:
        return jsonify({"error": "No schedules uploaded yet"}), 400

    # Find gaps for each schedule
    all_gaps = []
    for schedule in all_schedules:
        gaps = find_gaps_for_schedule(schedule["classes"], min_gap_minutes=30)
        all_gaps.append(gaps)

    # Find common free times
    common_gaps = find_common_free_times(all_gaps, min_gap_minutes=30)

    return jsonify({
        "group_name": group["name"],
        "num_people": len(all_schedules),
        "common_free_times": common_gaps
    })


if __name__ == '__main__':
    print("\nStarting Schedule Free Time Finder API...")
    print("Running at: http://localhost:5001")
    print("\nTest using:")
    print("  1. Create group: curl -X POST http://localhost:5001/api/groups -H 'Content-Type: application/json' -d '{\"name\":\"My Group\"}'")
    print("  2. Upload schedule: curl -X POST http://localhost:5001/api/groups/group1/upload -F 'file=@schedules/schedule1.png' -F 'user_name=John'")
    print("  3. Get free times: curl http://localhost:5001/api/groups/group1/free-times\n")

    app.run(debug=True, port=5001)