# Sausage'd - Schedule Free Time Finder

A web application that helps groups find common free time by analyzing uploaded schedule screenshots using OCR and intelligent time-gap detection.

## Features

- 🔐 **User Authentication** - JWT-based login/signup system
- 📸 **Schedule Upload** - Drag-and-drop schedule image uploads
- 🤖 **OCR Processing** - Automatic schedule parsing from images
- 📅 **Free Time Detection** - Find common free times across multiple schedules
- 👥 **Group Management** - Create groups with shareable invite codes
- 📋 **Copy to Clipboard** - Easy sharing of common free times

## Tech Stack

- **Backend**: Flask, Python 3.12
- **Database**: Supabase (PostgreSQL)
- **Authentication**: JWT with bcrypt
- **OCR**: PyTorch, Pillow
- **Frontend**: JavaScript, HTML, CSS

## Prerequisites

- Python 3.12+
- Supabase account (free tier works)
- Git

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/MRUHacks.git
cd MRUHacks
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r backend/requirements.txt
```

### 4. Configure Environment Variables

Create `backend/.env` file:

```env
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
```

### 5. Set Up Database

Run this SQL in your Supabase SQL Editor:

```sql
-- Create users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create groups table
CREATE TABLE groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    invite_code TEXT UNIQUE NOT NULL,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create schedules table
CREATE TABLE schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    user_name TEXT NOT NULL,
    classes JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Disable Row Level Security (for development)
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE groups DISABLE ROW LEVEL SECURITY;
ALTER TABLE schedules DISABLE ROW LEVEL SECURITY;
```

## Running Locally

### Start Backend (Terminal 1)

```bash
# From project root
gunicorn backend.app:app --bind 0.0.0.0:5001
```

### Start Frontend (Terminal 2)

```bash
# From project root
cd frontend
python -m http.server 8080
```

### Access the App

Open your browser to: `http://localhost:8080/login/login.html`

## Usage

1. **Sign Up** - Create an account at `/signup/signup.html`
2. **Login** - Sign in at `/login/login.html`
3. **Create Group** - Create a new group and get an invite code
4. **Upload Schedules** - Drag-and-drop schedule screenshots
5. **View Free Times** - See common free times once 2+ people have uploaded

## Project Structure

```
MRUHacks/
├── backend/
│   ├── app.py              # Flask API endpoints
│   ├── auth.py             # JWT authentication utilities
│   ├── requirements.txt    # Python dependencies
│   └── .env               # Environment variables (not in git)
├── frontend/
│   ├── login/
│   │   └── login.html     # Login page
│   ├── signup/
│   │   └── signup.html    # Registration page
│   └── scheduleInsert/
│       └── upload.html    # Main app - upload & view free times
├── find_times.py          # OCR and schedule parsing
├── find_free_times.py     # Time gap detection algorithm
└── README.md
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `GET /api/auth/me` - Get current user (protected)

### Groups & Schedules
- `POST /api/groups` - Create new group
- `POST /api/groups/<code>/upload` - Upload schedule image
- `GET /api/groups/<code>/free-times` - Get common free times

## Deployment

### Deploy Backend to Render

1. Push code to GitHub
2. Create new Web Service on [Render](https://render.com)
3. Configure:
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `gunicorn backend.app:app --bind 0.0.0.0:$PORT`
4. Add environment variables (SUPABASE_URL, SUPABASE_KEY, JWT_SECRET_KEY)
5. Deploy

### Update Frontend

Change `API_BASE` in all HTML files from:
```javascript
const API_BASE = 'http://localhost:5001/api';
```

To:
```javascript
const API_BASE = 'https://your-app.onrender.com/api';
```

## Troubleshooting

**Backend won't start:**
- Check `.env` file exists and has correct Supabase credentials
- Ensure virtual environment is activated
- Verify all dependencies installed: `pip install -r backend/requirements.txt`

**Database errors:**
- Check Supabase credentials in `.env`
- Verify tables created in Supabase SQL Editor
- Ensure RLS is disabled (for development)

**Frontend can't connect:**
- Verify backend is running on port 5001
- Check CORS is enabled in Flask
- Ensure `API_BASE` URL is correct

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - feel free to use this project for learning and personal projects.

## Authors

My friends [Lorenzo](https://github.com/lorenzoaht) and [Elijah](https://github.com/SwingSett)

Built at MRU Hacks 2025