# Ops runbook — email notifications (task @mentions)

How to stand up **real email delivery** for the platform. Today the only outbound email is a **task
@mention ping**, but everything below (durable outbox + Celery worker + transport config) is generic and
serves any future notification.

Two independent things have to be true for a colleague to actually receive mail:

1. **Delivery infrastructure is running** — an SMTP transport is configured and the Celery worker + beat are
   up (§2, §3). Without this, mentions still work in-app (the mentions bell); the email just stays queued.
2. **Deliverability is set up** — your sending domain has SPF / DKIM / DMARC so mailbox providers accept the
   mail instead of junking it (§4). This is DNS + your email provider, not code.

---

## 1. How it works (the moving parts)

- A comment with an `@mention` writes a row to **`email_outbox`** (status `pending`) in the *same DB
  transaction* as the mention — so it's never lost and never sent for a rolled-back comment.
- **Dispatch by transport** (`services/notifications/mailer.py :: dispatch`):
  - `console` / `off` → delivered **inline** (dev/demo). No worker needed.
  - `smtp` → handed to the **Celery worker**; the request never waits on SMTP.
- The worker delivers via two paths:
  - **on-demand**: the API enqueues an `emails.drain_outbox` task right after a mention (best-effort, from a
    daemon thread — a down broker never blocks the request).
  - **beat sweep**: `emails.drain_outbox` also runs **every 120 s** as the durable guarantee / retry.
- `deliver()` claims rows `FOR UPDATE SKIP LOCKED`, so the two paths never double-send.

Delivery is idempotent-ish per row: a row moves `pending → sent`; a transient failure becomes `failed` and is
retried on the next sweep.

---

## 2. Configuration (environment / secret manager)

Set these in `.env` (gitignored) or your secret manager — **never commit SMTP credentials**. Fields map 1:1
to `core/config.py`.

```bash
# Turn on real delivery
EMAIL_TRANSPORT=smtp                 # ""=auto (smtp if SMTP_HOST set, else off) | smtp | console | off
EMAIL_FROM="Tellumen <notifications@mail.yourdomain.com>"
APP_BASE_URL=https://app.yourdomain.com   # builds the deep-link back to the task in the email

# SMTP relay (values from your email provider)
SMTP_HOST=smtp.youresp.com
SMTP_PORT=587                        # 587 = STARTTLS (recommended)
SMTP_USER=<provider-username-or-apikey>
SMTP_PASSWORD=<from-secret-manager>
SMTP_STARTTLS=true

# Broker for the Celery worker (already used by the platform's other jobs)
REDIS_URL=redis://localhost:6379/0
```

Notes:
- Use a **subdomain** for `EMAIL_FROM` (e.g. `mail.yourdomain.com` or `notifications.yourdomain.com`). It
  isolates sending reputation from your corporate mail and simplifies DKIM/SPF.
- `EMAIL_TRANSPORT=console` is the safe non-prod setting — it renders + logs the email and marks the outbox
  row `sent` without sending anything externally.

---

## 3. Run the worker + beat

Real SMTP delivery requires **Redis up** and **both** a Celery worker and the beat scheduler, run as separate
processes from the API (they already exist for the platform's hazard/feed jobs — this just adds the email
task to them).

```bash
# 0) Redis must be reachable at REDIS_URL
redis-cli ping           # -> PONG

# 1) worker (executes emails.drain_outbox + the existing hazard/feed tasks)
celery -A services.tasks.celery_app worker --loglevel=info

# 2) beat (periodic scheduler: drains the outbox every 120s, refreshes feeds hourly)
celery -A services.tasks.celery_app beat --loglevel=info
```

### systemd (production)

```ini
# /etc/systemd/system/tellumen-worker.service
[Unit]
Description=Tellumen Celery worker
After=network.target redis.service
[Service]
User=tellumen
WorkingDirectory=/opt/tellumen
EnvironmentFile=/opt/tellumen/.env
ExecStart=/opt/tellumen/.venv/bin/celery -A services.tasks.celery_app worker --loglevel=info
Restart=always
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/tellumen-beat.service
[Unit]
Description=Tellumen Celery beat
After=network.target redis.service
[Service]
User=tellumen
WorkingDirectory=/opt/tellumen
EnvironmentFile=/opt/tellumen/.env
ExecStart=/opt/tellumen/.venv/bin/celery -A services.tasks.celery_app beat --loglevel=info
Restart=always
[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now tellumen-worker tellumen-beat
```

Run **exactly one** beat instance (multiple beats = duplicate schedules). Workers can scale horizontally.

---

## 4. Deliverability — DNS records

Set these on your **sending (sub)domain**. Exact values come from your ESP's dashboard — the ones below are
the shapes, with placeholders marked `<…>`. Publish at the DNS host for `yourdomain.com`.

Assume sending subdomain = `mail.yourdomain.com`.

**SPF** — authorises your ESP to send for the subdomain. One TXT record on `mail.yourdomain.com`:

```
mail.yourdomain.com.   TXT   "v=spf1 include:<esp-spf-include> -all"
# e.g. include:sendgrid.net   |  include:amazonses.com  |  include:_spf.google.com
```

**DKIM** — cryptographically signs the mail. Your ESP gives you the selector + key; publish exactly what they
provide (often 1–3 CNAMEs, or a TXT):

```
<selector>._domainkey.mail.yourdomain.com.   CNAME   <esp-provided-target>
# (SES/SendGrid typically hand you a set of CNAMEs to paste verbatim)
```

**DMARC** — tells mailbox providers what to do with mail that fails SPF/DKIM, and where to send reports. One
TXT on `_dmarc.mail.yourdomain.com`. Start at `p=none` (monitor), then tighten to `quarantine`/`reject` once
reports look clean:

```
_dmarc.mail.yourdomain.com.   TXT   "v=DMARC1; p=none; rua=mailto:dmarc-reports@yourdomain.com; fo=1"
```

**Return-Path / custom MAIL FROM** (recommended) — some ESPs have you add a CNAME/MX so the bounce domain
aligns with your domain (improves DMARC alignment). Follow the ESP's "domain authentication" wizard; it lists
every record and verifies them for you.

Checklist:
- [ ] Sending subdomain chosen (`mail.yourdomain.com`), `EMAIL_FROM` uses it.
- [ ] ESP "domain authentication" completed → SPF + DKIM records published and **verified green** in the ESP.
- [ ] DMARC record published (`p=none` first).
- [ ] Send a test to a Gmail + an Outlook address; confirm it lands in inbox and the headers show
      `dkim=pass` and `spf=pass`.

---

## 5. Verify end-to-end

1. **Config loaded** — the API/worker process has `EMAIL_TRANSPORT=smtp` and `SMTP_*` set.
2. **Trigger** — @mention a colleague in a task comment (or in-app: Tasks → open a task → comment `@Name`).
3. **Queued** — a row appears in the outbox:
   ```sql
   SELECT to_email, status, transport, attempts, last_error, created_at
   FROM email_outbox WHERE kind = 'task_mention' ORDER BY created_at DESC LIMIT 5;
   ```
   Expect `status='sent'`, `transport='smtp'` within ~a few seconds (on-demand) or ≤120 s (beat).
4. **Stuck?** — `status='pending'` means no drain ran → check the **worker + beat are up** and Redis is
   reachable. `status='failed'` → read `last_error` (auth, TLS, or relay rejection); it will retry on the
   next sweep once fixed.

---

## 6. Failure modes & behaviour

| Situation | What happens | Fix |
|---|---|---|
| Redis down | Enqueue fails fast (swallowed); rows stay `pending` | Bring Redis up; beat drains the backlog |
| Worker/beat not running | Rows stay `pending`; in-app mentions still work | Start worker + beat (§3) |
| SMTP auth/relay error | Row → `failed` with `last_error`; retried each sweep | Fix creds/relay; auto-recovers |
| `EMAIL_TRANSPORT=off` | Row → `skipped` (intent recorded, nothing sent) | Set `smtp` (or `console` for dev) |
| API restart mid-send | At-least-once: unfinished rows re-drained by beat | none — by design |

---

## 7. Scale / hardening (later, not required day one)

- Move `EMAIL_FROM` sending to a dedicated ESP subuser with its own API key + reputation.
- Add a `dead-letter` threshold: after N failed attempts, alert an operator rather than retry forever
  (today the sweep retries indefinitely — fine at low volume).
- Per-recipient rate limiting / digest batching if mention volume grows (avoid emailing on every comment in a
  busy thread).
- Add an unsubscribe / notification-preferences surface before enabling any non-mention email.
