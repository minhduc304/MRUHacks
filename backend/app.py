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

# Import authentication utilities
try:
    # When running with gunicorn from project root
    from backend.auth import hash_password, verify_password, create_access_token, token_required, optional_token
except ImportError:
    # When running directly with python backend/app.py
    from auth import hash_password, verify_password, create_access_token, token_required, optional_token

app = Flask(__name__)
CORS(app)  # Allow frontend to call this API

# Initialize Supabase client
# Get credentials from environment variables
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().replace('\n', '').replace('\r', '').replace(' ', '')
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip().replace('\n', '').replace('\r', '').replace(' ', '')

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Supabase credentials not found in environment variables")
    print("   Set SUPABASE_URL and SUPABASE_KEY to enable database")
    supabase: Client = None
else:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"Supabase client created!")

        # Test connection
        test_result = supabase.table('groups').select('id').limit(1).execute()
        print(f"Connection test passed!")
    except Exception as e:
        print(f"Supabase connection error: {e}")
        supabase: Client = None


@app.route('/')
def home():
    """API home page"""
    return jsonify({
        "message": "Schedule Free Time Finder API",
        "endpoints": [
            "POST /api/auth/register - Register new user",
            "POST /api/auth/login - Login user",
            "GET /api/auth/me - Get current user (protected)",
            "POST /api/groups - Create group",
            "POST /api/groups/<code>/upload - Upload schedule",
            "GET /api/groups/<code>/free-times - Get free times"
        ]
    })

# AUTHENTICATION ENDPOINTS
@app.route('/api/auth/register', methods=['POST'])
def register():
    """
    Register a new user
    """
    if not supabase:
        return jsonify({"error": "Database not available"}), 503

    data = request.json

    # Validate required fields
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # Check if user already exists
    existing_user = supabase.table('users').select('*').eq('email', email).execute()
    if len(existing_user.data) > 0:
        return jsonify({"error": "User with this email already exists"}), 409

    # Hash password
    password_hash = hash_password(password)

    # Insert user into database
    try:
        result = supabase.table('users').insert({
            "email": email,
            "password_hash": password_hash,
            "full_name": full_name
        }).execute()

        user = result.data[0]

        # Create JWT token
        token = create_access_token({
            "user_id": user['id'],
            "email": user['email']
        })

        print(f"User registered: {email}")

        return jsonify({
            "message": "User registered successfully",
            "user": {
                "id": user['id'],
                "email": user['email'],
                "full_name": user['full_name']
            },
            "token": token
        }), 201

    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({"error": "Failed to register user"}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """
    Login user and return JWT token
    """
    if not supabase:
        return jsonify({"error": "Database not available"}), 503

    data = request.json

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    # Get user from database
    try:
        result = supabase.table('users').select('*').eq('email', email).execute()

        if len(result.data) == 0:
            return jsonify({"error": "Invalid email or password"}), 401

        user = result.data[0]

        # Verify password
        if not verify_password(password, user['password_hash']):
            return jsonify({"error": "Invalid email or password"}), 401

        # Create JWT token
        token = create_access_token({
            "user_id": user['id'],
            "email": user['email']
        })

        print(f"User logged in: {email}")

        return jsonify({
            "message": "Login successful",
            "user": {
                "id": user['id'],
                "email": user['email'],
                "full_name": user['full_name']
            },
            "token": token
        }), 200

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"error": "Login failed"}), 500


@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    """
    Get current authenticated user's information

    Requires: Authorization header with Bearer token
    """
    if not supabase:
        return jsonify({"error": "Database not available"}), 503

    try:
        # Fetch full user data from database
        result = supabase.table('users').select('id, email, full_name, created_at').eq('id', current_user['user_id']).execute()

        if len(result.data) == 0:
            return jsonify({"error": "User not found"}), 404

        user = result.data[0]

        return jsonify({"user": user}), 200

    except Exception as e:
        print(f"Get user error: {e}")
        return jsonify({"error": "Failed to fetch user"}), 500


@app.route('/api/groups', methods=['POST'])
@optional_token
def create_group(current_user):
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

    # Prepare group data
    group_data = {
        "name": group_name,
        "invite_code": invite_code
    }

    # If user is authenticated, associate group with user
    if current_user:
        group_data["created_by"] = current_user['user_id']

    # Insert into Supabase
    result = supabase.table('groups').insert(group_data).execute()

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
    for i, schedule in enumerate(schedules_result.data):
        gaps = find_gaps_for_schedule(schedule["classes"], min_gap_minutes=30)
        # Count total gaps across all days
        total_gaps = sum(len(day_gaps) for day_gaps in gaps.values()) if isinstance(gaps, dict) else len(gaps)
        print(f"Person {i+1} ({schedule.get('user_name', 'Unknown')}): {total_gaps} gaps found")
        all_gaps.append(gaps)

    # Find common free times
    common_gaps = find_common_free_times(all_gaps, min_gap_minutes=30)

    print(f"Calculated free times for group {invite_code} with {len(schedules_result.data)} people")
    print(f"Common free times found: {len(common_gaps)}")
    print(f"Common gaps: {common_gaps}")

    # Transform format: {"Mon": [...], "Tue": [...]} -> [{"day": "Monday", ...}, ...]
    day_name_map = {
        "Mon": "Monday",
        "Tue": "Tuesday",
        "Wed": "Wednesday",
        "Thu": "Thursday",
        "Fri": "Friday",
        "Sat": "Saturday",
        "Sun": "Sunday"
    }

    formatted_gaps = []
    for short_day, time_slots in common_gaps.items():
        full_day = day_name_map.get(short_day, short_day)
        for slot in time_slots:
            formatted_gaps.append({
                "day": full_day,
                "start_time": slot["start"],
                "end_time": slot["end"],
                "duration_minutes": slot["duration_minutes"]
            })

    return jsonify({
        "group_name": group["name"],
        "num_people": len(schedules_result.data),
        "common_free_times": formatted_gaps
    })


if __name__ == '__main__':
    print("\nStarting Schedule Free Time Finder API...")
    print("Running at: http://localhost:5001")
    print("\nTest using:")
    print("  1. Create group: curl -X POST http://localhost:5001/api/groups -H 'Content-Type: application/json' -d '{\"name\":\"My Group\"}'")
    print("  2. Upload schedule: curl -X POST http://localhost:5001/api/groups/group1/upload -F 'file=@schedules/schedule1.png' -F 'user_name=John'")
    print("  3. Get free times: curl http://localhost:5001/api/groups/group1/free-times\n")

    app.run(debug=True, port=5001, host='0.0.0.0')