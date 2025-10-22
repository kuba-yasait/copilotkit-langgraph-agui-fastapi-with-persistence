# Repository Agent Instructions
## Mandatory setup before running the app
- Always run `npm install` from the repository root before starting the frontend or backend services.
- After installing npm dependencies, change into the `agent/` directory and run `poetry install` to ensure the Python backend environment is prepared.
- Always run `npx playwright install` to be ready to execute e2e tests
These steps are required each time the environment is initialized to guarantee all dependencies are available.

## End-to-end test requirements
- End-to-end coverage lives under `tests/e2e` and is executed with `npm run test:e2e` (Playwright).
- The command above automatically starts the combined UI and agent stack via `npm run dev`; ensure any required environment variables (for example `OPENAI_API_KEY` in `agent/.env`) are configured so the agent can respond during the run.
- Before preparing or submitting a pull request, always run `npm run test:e2e` locally and confirm every test passes. Do not merge or open PRs when these checks are failing.
