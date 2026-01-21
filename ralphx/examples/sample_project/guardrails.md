# Excuse Generator - Project Guardrails

## Content Guidelines

- Keep all excuses **PG-rated** and workplace-appropriate
- No offensive, discriminatory, or harmful content
- Excuses should be clearly fictional/humorous - avoid anything that could be used maliciously
- No references to violence, illegal activities, or sensitive topics

## Technical Guidelines

### Frontend

- Use **vanilla JavaScript only** - no React, Vue, or other frameworks
- No npm dependencies for the frontend
- Keep JavaScript in a single `app.js` file
- Use modern ES6+ syntax (const/let, arrow functions, template literals)
- CSS should be custom - no Tailwind, Bootstrap, or CSS frameworks

### Backend

- Use **FastAPI** for the Python backend
- SQLite for database - no PostgreSQL, MySQL, or other databases
- Keep dependencies minimal - only what's in requirements.txt
- Use Pydantic models for request/response validation

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to all public functions
- Keep functions small and focused (< 30 lines ideally)

### Database

- All data stored in SQLite at `data/excuses.db`
- Use parameterized queries to prevent SQL injection
- Include proper indexes for frequently queried columns

### Performance

- Page load should be instant (< 1 second)
- No unnecessary API calls
- Cache static assets appropriately

### Accessibility

- Use semantic HTML elements
- Include ARIA labels where needed
- Ensure color contrast meets WCAG AA standards
- All interactive elements must be keyboard accessible

### Mobile Support

- Mobile-first responsive design
- Touch targets at least 44x44 pixels
- No horizontal scrolling on mobile devices
