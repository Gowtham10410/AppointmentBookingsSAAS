# Smart Appointment Scheduler

A conflict-free appointment booking system for a single service business, built from a Django + MySQL backend and a Next.js + React frontend.

## Project summary
This project follows the master build prompt for a smart appointment scheduler that handles:
- staff and service management
- working-hour configuration
- availability generation and booking rules
- concurrency-safe slot booking
- confirmation and cancellation flows
- admin and staff dashboard workflows

## Stack
- Backend: Python 3.12+, Django, DRF, MySQL 8.x, pytest
- Frontend: Next.js App Router, React, TypeScript, Tailwind CSS, shadcn/ui
- QA: Playwright, Vitest, axe-core, Lighthouse
- Tooling: Docker Compose, GitHub Actions, Ruff, mypy

## Quick start
Placeholder instructions for Phase 8 and beyond.

### Docker
```bash
cp .env.example .env
make db-up
```

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py runserver
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Demo credentials
Demo credentials are intentionally labelled as demo and will be seeded in later phases through the `seed_demo` management command.

## Project structure
```text
.
├── .github/
├── backend/
├── docs/
├── frontend/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .editorconfig
├── Makefile
├── README.md
└── ...
```

## Notes
- The repository is in the bootstrap state and will be expanded across the planned implementation phases.
- Full runtime, deployment and verification instructions will be completed in later phases.
