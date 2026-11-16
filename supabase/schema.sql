create extension if not exists pgcrypto;

create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.organization_members (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member' check (role in ('owner', 'admin', 'member')),
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

create table if not exists public.aws_connections (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  account_id text not null,
  role_arn text not null,
  region text not null default 'us-east-1',
  status text not null default 'connected'
    check (status in ('pending', 'connected', 'error', 'revoked')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, account_id)
);

create table if not exists public.recommendations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  aws_connection_id uuid references public.aws_connections(id) on delete cascade,
  resource_id text not null,
  recommendation_type text not null,
  message text not null,
  estimated_monthly_savings numeric(12, 2),
  status text not null default 'open'
    check (status in ('open', 'approved', 'rejected', 'snoozed')),
  created_at timestamptz not null default now()
);

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  action text not null,
  resource_id text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create or replace function public.is_org_member(target_org uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.organization_members
    where organization_id = target_org
      and user_id = auth.uid()
  );
$$;

alter table public.organizations enable row level security;
alter table public.organization_members enable row level security;
alter table public.aws_connections enable row level security;
alter table public.recommendations enable row level security;
alter table public.audit_logs enable row level security;

create policy "members can view organizations"
  on public.organizations for select
  using (public.is_org_member(id));

create policy "members can view membership"
  on public.organization_members for select
  using (public.is_org_member(organization_id));

create policy "members can view connections"
  on public.aws_connections for select
  using (public.is_org_member(organization_id));

create policy "members can view recommendations"
  on public.recommendations for select
  using (public.is_org_member(organization_id));

create policy "members can view audit logs"
  on public.audit_logs for select
  using (public.is_org_member(organization_id));

