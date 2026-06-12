-- Run this in your Supabase project: SQL Editor → New Query → Paste → Run

-- 1. Tasks table
create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default '00000000-0000-0000-0000-000000000001',
  title text not null,
  description text,
  status text not null check (status in ('To Do', 'In Progress', 'Done', 'Blocked')),
  priority text not null check (priority in ('Low', 'Medium', 'High', 'Urgent')),
  tags text[] default '{}',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 2. AI action audit log table
create table if not exists ai_action_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  user_prompt text not null,
  raw_llm_output jsonb,
  validation_attempts jsonb,
  final_status text not null check (final_status in (
    'success', 'self_corrected', 'failed', 'rejected_unauthorized'
  )),
  executed_action jsonb,
  provider text,
  created_at timestamptz default now()
);

-- 3. Insert some seed tasks so the demo isn't empty
insert into tasks (user_id, title, status, priority) values
  ('00000000-0000-0000-0000-000000000001', 'Build portfolio project README',   'In Progress', 'High'),
  ('00000000-0000-0000-0000-000000000001', 'Deploy to Hugging Face Spaces',     'To Do',       'High'),
  ('00000000-0000-0000-0000-000000000001', 'Write adversarial eval set',        'To Do',       'Medium'),
  ('00000000-0000-0000-0000-000000000001', 'Run multi-model benchmark',         'To Do',       'Medium'),
  ('00000000-0000-0000-0000-000000000001', 'Record demo GIF for README',        'To Do',       'Low'),
  ('00000000-0000-0000-0000-000000000001', 'Write SECURITY.md threat model',    'Done',        'High'),
  ('00000000-0000-0000-0000-000000000001', 'Set up Supabase schema',            'Done',        'Urgent');
