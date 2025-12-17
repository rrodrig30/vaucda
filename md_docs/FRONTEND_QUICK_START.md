# VAUCDA Frontend - Quick Start Guide

## Prerequisites

- Node.js 18+ installed
- npm or yarn package manager
- Backend API running on http://localhost:8000

## Quick Start (5 Minutes)

### 1. Navigate to Frontend Directory
```bash
cd /home/gulab/PythonProjects/VAUCDA/frontend
```

### 2. Install Dependencies
```bash
npm install
```

This will install all required packages (~2-3 minutes):
- React 18.2
- TypeScript 5.3
- Vite 5.0
- Tailwind CSS 3.4
- Redux Toolkit 2.0
- React Router 6.21
- Axios, Socket.io-client, and more

### 3. Create Environment File
```bash
cp .env.example .env
```

The `.env` file should contain:
```
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_ENABLE_DEVTOOLS=true
```

### 4. Start Development Server
```bash
npm run dev
```

The application will start at **http://localhost:3000**

### 5. Login

Navigate to http://localhost:3000/login

**Default Credentials** (if backend has test user):
- Username: `admin`
- Password: `admin`

Or use credentials configured in your backend.

## What You'll See

### Login Page
- Branded VA logo
- Username/password form
- Error handling
- Responsive design

### Dashboard (After Login)
- Welcome message with username
- Quick action cards:
  - Generate Note
  - Calculators
  - Knowledge Base
- Recent notes section (if any exist)
- Theme toggle (light/dark)
- User menu with logout

### Navigation
- **Dashboard** - Overview and quick actions
- **Note Generation** - Clinical note generator (placeholder)
- **Calculators** - Calculator library (placeholder)
- **Knowledge Base** - RAG search (placeholder)
- **Settings** - User preferences (placeholder)

## Available Features

### ✅ Fully Functional
- User authentication (login/logout)
- JWT token management
- Protected routes
- Dark mode toggle
- Responsive layout
- Dashboard with quick actions
- Recent notes display (if backend provides)
- Theme persistence
- User profile display

### ⚠️ Placeholder (To Be Expanded)
- Note generation page
- Calculator library
- Knowledge Base search
- Settings page

## Development Commands

### Start Dev Server
```bash
npm run dev
```
Hot reload enabled. Changes appear instantly.

### Type Check
```bash
npm run type-check
```
Verify TypeScript types without building.

### Lint Code
```bash
npm run lint
```
Check for code quality issues.

### Build for Production
```bash
npm run build
```
Creates optimized production bundle in `dist/`.

### Preview Production Build
```bash
npm run preview
```
Preview the production build locally.

## Project Structure Overview

```
frontend/
├── src/
│   ├── api/              # API client (ALL backend endpoints)
│   ├── components/       # React components
│   │   ├── common/       # Reusable UI (Button, Input, Card, etc.)
│   │   └── layout/       # Header, Sidebar, Layout
│   ├── pages/            # Route pages
│   ├── store/            # Redux state management
│   ├── hooks/            # Custom React hooks
│   ├── types/            # TypeScript types
│   ├── utils/            # Utilities
│   ├── styles/           # Global CSS
│   ├── App.tsx           # Root component
│   └── main.tsx          # Entry point
├── public/               # Static assets
└── [config files]        # TypeScript, Vite, Tailwind configs
```

## API Integration

All API calls are pre-configured and type-safe:

```typescript
import { notesApi } from '@/api'

// Generate a note
const result = await notesApi.generateNote({
  clinical_input: 'Patient data...',
  note_type: 'clinic_note',
  llm_config: {
    provider: 'ollama',
    model: 'llama3.1:8b',
  },
})
```

Available APIs:
- `authApi` - Login, logout, user profile
- `notesApi` - Generate, fetch, recent notes
- `calculatorsApi` - List, execute calculators
- `templatesApi` - Template management
- `settingsApi` - User settings
- `llmApi` - LLM provider management
- `ragApi` - Knowledge base search
- `healthApi` - System health checks

## State Management

Redux Toolkit is configured with slices for:
- **auth** - User authentication
- **note** - Note generation
- **calculator** - Calculator execution
- **settings** - User preferences
- **ui** - Theme, sidebar, modals, toasts

Usage:
```typescript
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { login } from '@/store/slices/authSlice'

const { user, isAuthenticated } = useAppSelector((state) => state.auth)
```

## Theming

### Toggle Theme
Click the sun/moon icon in the header.

### Theme Persistence
Theme choice is saved to localStorage and persists across sessions.

### Dark Mode Classes
Tailwind's dark mode is class-based. All components support dark mode.

## Troubleshooting

### Port Already in Use
If port 3000 is busy, Vite will suggest an alternative port.

### Cannot Connect to Backend
1. Verify backend is running: `curl http://localhost:8000/api/v1/health`
2. Check `.env` file has correct `VITE_API_BASE_URL`
3. Ensure no CORS issues (backend should allow localhost:3000)

### Module Not Found Errors
```bash
rm -rf node_modules package-lock.json
npm install
```

### TypeScript Errors
```bash
npm run type-check
```
Fix reported type errors.

### Build Fails
1. Check Node.js version: `node --version` (must be 18+)
2. Clear cache: `rm -rf node_modules/.vite`
3. Reinstall dependencies

## Next Development Steps

To complete the application, implement these pages (in order):

1. **Note Generation Page** (~8-12 hours)
   - Clinical input textarea
   - Template selector
   - LLM configuration
   - WebSocket streaming
   - Calculator panel
   - RAG search panel

2. **Calculator Library** (~6-10 hours)
   - Calculator grid by category
   - Calculator modal
   - Dynamic forms
   - Result display

3. **Knowledge Base** (~4-6 hours)
   - Search interface
   - Results display
   - Document preview

4. **Settings** (~4-6 hours)
   - Profile settings
   - LLM preferences
   - Template management

## Testing

Test users can be created in the backend. Ensure you have at least one user account to log in.

### Test Login Flow
1. Navigate to http://localhost:3000/login
2. Enter credentials
3. Should redirect to dashboard on success
4. Should show error message on failure

### Test Protected Routes
1. Try accessing http://localhost:3000/ without logging in
2. Should redirect to /login
3. After login, should access protected pages

### Test Theme Toggle
1. Click moon icon in header
2. Should switch to dark mode
3. Refresh page - dark mode should persist
4. Click sun icon to return to light mode

### Test Logout
1. Click logout icon in header
2. Should return to login page
3. Should clear authentication
4. Cannot access protected routes

## Production Deployment

When ready for production:

1. **Build**:
   ```bash
   npm run build
   ```

2. **Test Build**:
   ```bash
   npm run preview
   ```

3. **Deploy**:
   Copy `dist/` directory to web server

4. **Configure**:
   - Update `.env` with production API URL
   - Ensure backend CORS allows production domain
   - Configure HTTPS

## Support

- **Documentation**: See `/frontend/README.md` for detailed information
- **Implementation Status**: See `/FRONTEND_IMPLEMENTATION_SUMMARY.md`
- **API Spec**: See `/API_SPECIFICATION.md`
- **Architecture**: See `/ARCHITECTURE.md`

## Summary

You now have:
- ✅ Fully configured React + TypeScript + Vite application
- ✅ Complete API integration layer
- ✅ Redux state management
- ✅ Authentication flow
- ✅ Responsive layout with dark mode
- ✅ Dashboard with quick actions
- ✅ Reusable component library

The foundation is complete. Build out the remaining pages to achieve 100% functionality!
