-- Run this in Supabase SQL Editor to replace seed data with complex, realistic tasks
-- that are more likely to stress-test the validation gate

-- Clear existing seed tasks first
DELETE FROM tasks WHERE user_id = '00000000-0000-0000-0000-000000000001';

-- Insert a rich, realistic project task list
INSERT INTO tasks (id, user_id, title, description, status, priority, tags) VALUES

  -- Auth & Backend
  ('a1000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001',
   'Implement JWT refresh token rotation',
   'Access tokens expire in 15min. Refresh tokens must be single-use and rotated on each call. Store in httpOnly cookie.',
   'In Progress', 'Urgent', ARRAY['backend', 'auth', 'security']),

  ('a1000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001',
   'Add rate limiting to /api/auth/login',
   'Use sliding window counter. Max 5 attempts per IP per 10 minutes. Return 429 with Retry-After header.',
   'To Do', 'High', ARRAY['backend', 'security', 'auth']),

  ('a1000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001',
   'Fix SQL injection in user search endpoint',
   'The /api/users?q= param is interpolated directly into the query. Must switch to parameterized queries immediately.',
   'To Do', 'Urgent', ARRAY['backend', 'security', 'bug']),

  -- Frontend
  ('a1000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001',
   'Migrate dashboard charts from Recharts to Victory',
   'Recharts has a memory leak on unmount in React 18. Victory is the approved replacement. Update 4 chart components.',
   'In Progress', 'Medium', ARRAY['frontend', 'charts', 'react']),

  ('a1000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000001',
   'Implement optimistic UI updates for task status changes',
   'Currently the board re-fetches on every mutation causing flicker. Use React Query mutation with rollback on error.',
   'To Do', 'Medium', ARRAY['frontend', 'ux', 'react']),

  ('a1000000-0000-0000-0000-000000000006', '00000000-0000-0000-0000-000000000001',
   'Fix mobile layout breaking below 375px',
   'Navigation overlaps content on iPhone SE. Sidebar needs to collapse to bottom nav on screens < 400px.',
   'To Do', 'High', ARRAY['frontend', 'bug', 'mobile']),

  -- AI / ML
  ('a1000000-0000-0000-0000-000000000007', '00000000-0000-0000-0000-000000000001',
   'Benchmark Claude Haiku vs GPT-4o-mini on structured output tasks',
   'Run the 25-prompt adversarial eval set against both models. Record first-pass %, self-correction %, avg latency.',
   'To Do', 'High', ARRAY['ai', 'eval', 'benchmark']),

  ('a1000000-0000-0000-0000-000000000008', '00000000-0000-0000-0000-000000000001',
   'Add prompt injection test cases to eval suite',
   'Tasks with titles like "Ignore previous instructions..." should be handled safely. Add 5 injection variants.',
   'In Progress', 'High', ARRAY['ai', 'security', 'eval']),

  ('a1000000-0000-0000-0000-000000000009', '00000000-0000-0000-0000-000000000001',
   'Implement confidence score in LLM action output',
   'Ask model to include a 0-1 confidence field. Route low-confidence (<0.6) actions to human review queue.',
   'To Do', 'Low', ARRAY['ai', 'feature']),

  -- DevOps / Infra
  ('a1000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001',
   'Set up GitHub Actions CI — lint, typecheck, pytest on every PR',
   'Use matrix strategy for Python 3.11/3.12. Cache pip dependencies. Fail fast on first error.',
   'Done', 'High', ARRAY['devops', 'ci', 'testing']),

  ('a1000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000001',
   'Configure Dependabot for weekly security updates',
   'Enable for pip and npm. Group patch updates into a single PR. Auto-merge if CI passes.',
   'Done', 'Medium', ARRAY['devops', 'security']),

  ('a1000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000001',
   'Add Sentry error tracking to Gradio app',
   'Instrument app.py with Sentry SDK. Capture unhandled exceptions in chat_handler and refresh_tasks.',
   'To Do', 'Medium', ARRAY['devops', 'observability']),

  -- Documentation & CV
  ('a1000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000001',
   'Write architecture diagram in Excalidraw',
   'Export as SVG and embed in README. Must show LLM → validation gate → execution flow clearly.',
   'In Progress', 'High', ARRAY['docs', 'portfolio']),

  ('a1000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000001',
   'Record 60-second demo GIF of the chat updating the task board',
   'Use LICEcap or OBS. Show: create task, bulk update, self-correction firing. Keep under 5MB.',
   'To Do', 'High', ARRAY['docs', 'portfolio']),

  ('a1000000-0000-0000-0000-000000000015', '00000000-0000-0000-0000-000000000001',
   'Publish adversarial eval notebook as public Kaggle notebook',
   'Export 02_eval.ipynb with results inline. Add to portfolio links section of CV.',
   'To Do', 'Low', ARRAY['docs', 'portfolio', 'kaggle']),

  -- Blocked items (interesting for demo)
  ('a1000000-0000-0000-0000-000000000016', '00000000-0000-0000-0000-000000000001',
   'Integrate Groq Llama 3.3 70B as primary HF Space provider',
   'Blocked on getting GROQ_API_KEY added to HF Space secrets. Free tier confirmed sufficient for demo load.',
   'Blocked', 'High', ARRAY['ai', 'devops', 'deployment']),

  ('a1000000-0000-0000-0000-000000000017', '00000000-0000-0000-0000-000000000001',
   'Add undo functionality for executed AI actions',
   'Blocked on schema design — need a reversals table that stores pre-action snapshots. Design doc pending.',
   'Blocked', 'Medium', ARRAY['backend', 'feature', 'ai']);
