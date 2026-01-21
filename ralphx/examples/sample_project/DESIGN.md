# Excuse Generator - Design Document

## Overview

The Excuse Generator is a fun, lightweight web application that helps users generate creative excuses for various life situations. Whether you're late to a meeting, forgot a birthday, or missed a deadline, this app provides entertaining (and sometimes surprisingly convincing) excuses at the click of a button.

## Goals

1. **Entertainment First** - The app should be fun to use and generate amusing content
2. **Simple & Fast** - No account required, instant results, mobile-friendly
3. **Customizable Output** - Users can tune excuses by category and tone
4. **Memorable** - Save favorites and track history for repeat use

## Features

### Core Features

#### 1. Excuse Generation
- Select a **category** for the situation:
  - Late to work/meeting
  - Missed deadline
  - Forgot birthday/anniversary
  - Didn't reply to message
  - Skipped event/party
  - Generic/Other
- Select a **tone** for the excuse:
  - Professional (workplace appropriate, formal)
  - Casual (friendly, conversational)
  - Dramatic (over-the-top, theatrical)
  - Absurd (ridiculous, comedy-focused)
- Click "Generate" to get a random excuse matching the criteria
- Each excuse is built from templates with variable substitution for variety

#### 2. Favorites System
- Click a heart icon to save an excuse to favorites
- View all saved favorites in a dedicated tab
- Remove excuses from favorites
- Favorites persist in the database

#### 3. Believability Rating
- After generating an excuse, rate it 1-5 stars for "believability"
- Ratings are stored and can be viewed in history
- Optional: Show average rating for excuse templates

#### 4. History View
- Browse all previously generated excuses
- Search by keyword
- Filter by category, tone, or date range
- See when each excuse was generated
- View ratings given

#### 5. Excuse of the Day
- Homepage displays a featured "Excuse of the Day"
- Rotates daily (seeded by date for consistency)
- Pulls from curated high-quality excuse templates

#### 6. Copy to Clipboard
- One-click button to copy excuse text
- Visual feedback (checkmark animation) on successful copy
- Works on mobile and desktop

## Technical Architecture

### Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.10+) |
| Database | SQLite |
| Frontend | Vanilla HTML/CSS/JS |
| Styling | Custom CSS (no framework) |

### Project Structure

```
excuse-generator/
├── main.py              # FastAPI application
├── database.py          # SQLite database operations
├── models.py            # Pydantic models
├── templates.py         # Excuse template data
├── requirements.txt     # Python dependencies
├── data/
│   └── excuses.db       # SQLite database file
└── static/
    ├── index.html       # Main SPA page
    ├── styles.css       # Application styles
    └── app.js           # Frontend JavaScript
```

### Database Schema

```sql
-- Excuse templates (seed data)
CREATE TABLE excuse_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    tone TEXT NOT NULL,
    template TEXT NOT NULL,
    variables TEXT,  -- JSON array of variable names
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Generated excuses (history)
CREATE TABLE generated_excuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER REFERENCES excuse_templates(id),
    excuse_text TEXT NOT NULL,
    category TEXT NOT NULL,
    tone TEXT NOT NULL,
    rating INTEGER,  -- 1-5 stars, NULL if not rated
    is_favorite BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily excuse selection
CREATE TABLE daily_excuse (
    date TEXT PRIMARY KEY,  -- YYYY-MM-DD format
    template_id INTEGER REFERENCES excuse_templates(id),
    excuse_text TEXT NOT NULL
);
```

### API Endpoints

#### GET /api/health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

#### GET /api/generate
Generate a random excuse.

**Query Parameters:**
- `category` (string, optional): Filter by category
- `tone` (string, optional): Filter by tone

**Response:**
```json
{
  "id": 42,
  "excuse": "My cat accidentally unplugged my alarm clock while chasing a ghost.",
  "category": "late",
  "tone": "absurd",
  "template_id": 15
}
```

#### POST /api/excuses/{id}/favorite
Toggle favorite status for an excuse.

**Response:**
```json
{
  "id": 42,
  "is_favorite": true
}
```

#### POST /api/excuses/{id}/rate
Rate an excuse.

**Request Body:**
```json
{
  "rating": 4
}
```

**Response:**
```json
{
  "id": 42,
  "rating": 4
}
```

#### GET /api/favorites
Get all favorited excuses.

**Response:**
```json
{
  "favorites": [
    {
      "id": 42,
      "excuse": "...",
      "category": "late",
      "tone": "absurd",
      "rating": 4,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### GET /api/history
Get excuse generation history.

**Query Parameters:**
- `category` (string, optional): Filter by category
- `tone` (string, optional): Filter by tone
- `search` (string, optional): Search in excuse text
- `limit` (int, default 50): Max results
- `offset` (int, default 0): Pagination offset

**Response:**
```json
{
  "excuses": [...],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

#### GET /api/excuse-of-the-day
Get today's featured excuse.

**Response:**
```json
{
  "excuse": "The traffic was terrible because a family of ducks decided to cross the highway.",
  "category": "late",
  "tone": "casual",
  "date": "2024-01-15"
}
```

#### GET /api/categories
Get list of available categories.

**Response:**
```json
{
  "categories": ["late", "deadline", "birthday", "message", "event", "other"]
}
```

#### GET /api/tones
Get list of available tones.

**Response:**
```json
{
  "tones": ["professional", "casual", "dramatic", "absurd"]
}
```

## User Interface

### Layout

The app uses a single-page layout with tabs:

```
+------------------------------------------+
|  EXCUSE GENERATOR           [History] [*] |
+------------------------------------------+
|                                          |
|  Category: [Late ▼]    Tone: [Casual ▼]  |
|                                          |
|  +------------------------------------+  |
|  |                                    |  |
|  |  "Sorry I'm late, my neighbor's   |  |
|  |   parrot learned to mimic my      |  |
|  |   alarm and kept hitting snooze." |  |
|  |                                    |  |
|  |  [Copy]  [♡]  Rating: ★★★★☆      |  |
|  +------------------------------------+  |
|                                          |
|        [ Generate New Excuse ]           |
|                                          |
+------------------------------------------+
|  Excuse of the Day:                      |
|  "My GPS took me through a time warp..." |
+------------------------------------------+
```

### Responsive Design

- Mobile-first approach
- Single column on phones (<768px)
- Centered card layout on tablets/desktop
- Touch-friendly buttons (44px minimum)

### Color Scheme

- Primary: #6366F1 (Indigo)
- Background: #F8FAFC (Light gray)
- Card: #FFFFFF
- Text: #1E293B (Slate)
- Accent: #F59E0B (Amber for favorites)

## Excuse Template System

Excuses are generated from templates with variable placeholders:

```python
templates = [
    {
        "category": "late",
        "tone": "absurd",
        "template": "My {pet} accidentally {action} my {item}.",
        "variables": {
            "pet": ["cat", "dog", "hamster", "goldfish"],
            "action": ["ate", "hid", "unplugged", "sat on"],
            "item": ["car keys", "alarm clock", "shoes", "phone"]
        }
    }
]
```

The generator:
1. Filters templates by category and tone
2. Picks a random template
3. Substitutes variables with random choices
4. Returns the complete excuse

## Error Handling

- All API errors return consistent JSON format:
  ```json
  {
    "error": {
      "code": "not_found",
      "message": "Excuse not found"
    }
  }
  ```
- Frontend shows user-friendly error toasts
- Database errors are logged server-side

## Future Enhancements (Out of Scope)

- User accounts and cloud sync
- Sharing excuses on social media
- Community-submitted templates
- AI-generated excuses
- Multi-language support
