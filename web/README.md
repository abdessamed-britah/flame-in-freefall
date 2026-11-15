# Flame in Freefall: static front end

A Next.js (App Router, TypeScript, Tailwind, Recharts) static site with the same five pages as the
Streamlit app. It has no server and runs no model: every number comes from the JSON files in
`public/data/`, written once by the team's Python code.

```
python ../src/export_web.py      # from the repository root's conda env: writes public/data/
python -m pytest ../tests/test_export_web.py
npm install
npm run build                    # static export to out/
```

Deployed on Vercel with Root Directory `web`. "Ask a new question" opens the Streamlit app,
<https://flame-in-freefall-1.streamlit.app/> (override with `NEXT_PUBLIC_STREAMLIT_URL`).
