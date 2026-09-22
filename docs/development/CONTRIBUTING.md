# Contributing

## Branch/PR Workflow

This project uses a simple branch workflow:

1. Create a feature branch from `main`
2. Make changes and commit
3. Push and create a PR
4. CI must pass (backend tests, frontend tests, typecheck, build, compose validation, container build)
5. Merge after review

## Testing Before PR

Run the full test suite before submitting a PR:

```bash
# Backend
cd backend && python -m pytest -q

# Frontend
cd frontend && npx vitest run && npm run typecheck && npm run build
```

All tests must pass. The CI workflow runs on every push and PR.

## Documentation Expectations

- Update documentation when adding/changing features
- Keep architecture.md current with implementation changes
- Add milestone records under `docs/milestones/` for significant features
- Preserve historical evidence under `docs/audits/`

## Commit Conventions

The repository uses conventional commit messages:

- `feat:` — new features
- `fix:` — bug fixes
- `docs:` — documentation changes
- `refactor:` — code refactoring
- `test:` — test additions/changes
- `chore:` — maintenance tasks

Examples from the repository:

```
feat: establish M16-C release machinery
fix(ci): invoke backend pytest through python module
fix(tests): make filesystem tests platform portable
```

## Code Style

- **Backend:** Python 3.14, FastAPI, Pydantic models, pytest
- **Frontend:** TypeScript, React, Vite, TailwindCSS, Vitest
- Follow existing patterns in the codebase
- No comments unless the logic is genuinely complex
- Configuration centralized in `backend/app/core/config.py`

## Security

- Never commit secrets, API keys, or credentials
- `.env` is gitignored — use `.env.example` as a template
- Docker socket access is a privileged trust boundary — document any changes
- All user-provided code runs in Docker sandbox — never on the host

## Milestone Documentation

When completing a milestone:

1. Update `docs/architecture/architecture.md` with new capabilities
2. Create a milestone record under `docs/milestones/`
3. Update `README.md` with current status
4. Update `docs/release/CHANGELOG.md` if releasing
