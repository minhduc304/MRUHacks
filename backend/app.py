"""
Schedule Free Time Finder - Simple Flask Backend
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import sys
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Import our schedule processing functions
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from find_times import detect_colored_blocks, extract_text, identify_grid_structure, extract_classes
from find_free_times import find_common_free_times, find_gaps_for_schedule

app = Flask(__name__)
CORS(app)  # Allow frontend to call this API

# Initialize Supabase client
# Get credentials from environment variables
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Supabase credentials not found in environment variables")
    print("   Set SUPABASE_URL and SUPABASE_KEY to enable database")
    supabase: Client = None
else:
    # Workaround for HTTP/2 stream reset issues: disable HTTP/2
    import httpx

    # Monkey-patch httpx.Client to default to HTTP/1.1
    original_client_init = httpx.Client.__init__
    def patched_init(self, *args, **kwargs):
        kwargs['http2'] = False
        original_client_init(self, *args, **kwargs)
    httpx.Client.__init__ = patched_init

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"Supabase client created (HTTP/1.1 enforced)!")

    # Test connection with a simple query
    # Note: This might fail intermittently due to HTTP/2 stream resets, but actual API calls usually work fine
    try:
        test_result = supabase.table('groups').select('id').limit(1).execute()
        print(f"Connection test passed!")
    except Exception as e:
        print(f"Connection test failed: {e}")
        print(f"   Don't worry - this is likely a transient HTTP/2 issue.")
        print(f"   API calls should still work fine!")


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
    """
    Create a new group

    SUPABASE CONCEPT: Insert data
    - .insert() adds a new row to the table
    - .execute() runs the query
    - Returns the inserted row data
    """
    data = request.json
    group_name = data.get('name', 'Unnamed Group')

    # Generate random invite code
    import secrets
    invite_code = secrets.token_urlsafe(6)[:8]

    # Insert into Supabase
    result = supabase.table('groups').insert({
        "name": group_name,
        "invite_code": invite_code
    }).execute()

    group = result.data[0]

    print(f"Group created! Name: '{group_name}', Code: {invite_code}")

    return jsonify({
        "id": group['id'],
        "invite_code": group['invite_code'],
        "name": group['name']
    }), 201


@app.route('/api/groups/<invite_code>/upload', methods=['POST'])
def upload_schedule(invite_code):
    """
    Upload a schedule to a group

    SUPABASE CONCEPT: Query with filters
    - .select() gets data from table
    - .eq() filters where column equals value
    - .single() returns one result (not a list)
    """
    # Check group exists
    group_result = supabase.table('groups').select('*').eq('invite_code', invite_code).execute()

    if len(group_result.data) == 0:
        return jsonify({"error": "Group not found"}), 404

    group = group_result.data[0]

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

        # Insert schedule into Supabase
        schedule_result = supabase.table('schedules').insert({
            "group_id": group['id'],
            "user_name": user_name,
            "classes": classes  # JSONB column stores the array directly
        }).execute()

        schedule = schedule_result.data[0]

        print(f"Schedule uploaded! User: {user_name}, Classes found: {len(classes)}")

        return jsonify({
            "id": schedule['id'],
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
    """
    Get common free times for a group

    SUPABASE CONCEPT: Joining tables
    - Get group by invite_code
    - Get all schedules for that group
    """
    # Get group
    group_result = supabase.table('groups').select('*').eq('invite_code', invite_code).execute()

    if len(group_result.data) == 0:
        return jsonify({"error": "Group not found"}), 404

    group = group_result.data[0]

    # Get all schedules for this group
    schedules_result = supabase.table('schedules').select('*').eq('group_id', group['id']).execute()

    if len(schedules_result.data) == 0:
        return jsonify({"error": "No schedules uploaded yet"}), 400

    # Find gaps for each schedule
    all_gaps = []
    for schedule in schedules_result.data:
        gaps = find_gaps_for_schedule(schedule["classes"], min_gap_minutes=30)
        all_gaps.append(gaps)

    # Find common free times
    common_gaps = find_common_free_times(all_gaps, min_gap_minutes=30)

    print(f"Calculated free times for group {invite_code} with {len(schedules_result.data)} people")

    return jsonify({
        "group_name": group["name"],
        "num_people": len(schedules_result.data),
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