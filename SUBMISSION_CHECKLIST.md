# OILTRACE AI — Submission Checklist

Submit the complete project folder, including:

- `README.md`
- `ARCHITECTURE.md`
- `DEMO_SCRIPT.md`
- `backend/`
  - `main.py`
  - `models/`
  - `routes/`
  - `services/`
  - `data/`
  - `scripts/`
  - `requirements.txt`
- `frontend/`
  - `package.json`
  - `vite.config.ts`
  - `tsconfig.json`
  - `index.html`
  - `src/`
  - `public/demo-data/`
  - `public/demo-images/`

Do **not** submit `frontend/node_modules/` or Python virtual environments.

No credentials/API keys are required.

Before submission, run:
1. `cd backend && python3 -m pip install -r requirements.txt`
2. `uvicorn main:app --reload --port 8000`
3. `cd frontend && npm install && npm run dev`
4. Open the Vite URL and click **START INVESTIGATION**.
