# PHASE 2: Real-Time Alerting & Impact Assessment
## Complete Implementation Plan

**Duration:** Weeks 2-6  
**Status:** 🚀 STARTING NOW  
**Goal:** Banks know about regulatory changes within 24 hours

---

## WHAT PHASE 2 DELIVERS

### User Experience (Bank Compliance Officer)

**Monday 9 AM:**
```
📧 Email Alert arrives:
─────────────────────────────────────
Subject: ⚠️ New Regulatory Requirement: EU Taxonomy v2.1

Basel Bank (your org),

EU Taxonomy was updated on 2026-06-26 (effective Dec 31, 2026).

YOUR IMPACT:
├─ 47 of your 500 assets reclassified
├─ 2 tables need schema updates
├─ 40 estimated dev hours
├─ 6 months to implementation deadline
└─ Priority: HIGH (€2.3B portfolio at risk)

ACTION REQUIRED: Review impact in dashboard
👉 https://platform.com/changes/tax-v21

Questions? Your account manager: Sarah@climate-platform.com
─────────────────────────────────────
```

**Monday 10 AM (same user logs into dashboard):**
```
🎯 Dashboard shows:
├─ New Alert: EU Taxonomy v2.1 (6 months to deadline)
├─ Impact Summary:
│  ├─ Affected Assets: 47 (flood-risk real estate)
│  ├─ System Changes: bank_assets, taxonomy_assessment, regulatory_filings
│  ├─ Dev Effort: 40 hours (2 engineers, 5 days)
│  └─ Financial Impact: €2.3B portfolio reclassified
├─ Next Steps: Click to create JIRA ticket
└─ Peer Status: 3 similar banks already implementing
```

---

## COMPONENTS TO BUILD

### 1. SCHEDULER (Daily Monitoring Loop)
**File:** `services/scheduling/regulatory_scheduler.py`

Runs daily at 02:00 UTC:
```python
1. FOR EACH registered customer:
   2. FOR EACH regulatory framework (TCFD, Taxonomy, SEC, Basel, EBA, FCA):
      3. Call CRCS detection
      4. IF changes detected:
         5. Analyze impact (our Phase 1 analyzer)
         6. Queue notification
         7. Create dashboard alert
         8. Optionally create JIRA ticket
```

### 2. NOTIFICATION SERVICE (Email + In-App)
**File:** `services/notifications/notification_service.py`

Sends alerts via:
- Email (primary)
- Dashboard banner (in-app)
- Slack/Teams integration (optional)

Template:
```
Subject: ⚠️ [Framework]: New requirement detected
Body:
- What changed
- Your impact (specific to your assets)
- Timeline (regulatory deadline - 7 days + implementation time)
- Effort estimate (dev hours)
- Action link (dashboard)
```

### 3. COMPETITIVE BENCHMARKING
**File:** `services/intelligence/benchmarking.py`

Answers: "What are peer banks doing?"

Data:
- Framework versions adopted by competitors
- Implementation timelines (rough estimate)
- Compliance status (leading vs. lagging)

### 4. TASK AUTOMATION (JIRA/Linear)
**File:** `services/integrations/task_automation.py`

When bank clicks "Create task":
```
JIRA Ticket created:
├─ Title: "Implement EU Taxonomy v2.1"
├─ Description: (auto-filled from impact analysis)
├─ Effort: 40 hours
├─ Deadline: Dec 31, 2026
├─ Tags: taxonomy, compliance, high-priority
└─ Assigned to: Engineering team lead
```

### 5. DASHBOARD UPDATES (Real-Time)
**File:** `api/routes/alerts_dashboard.py`

New endpoints:
```
GET  /dashboard/alerts               → List all active alerts
GET  /dashboard/alerts/{alert_id}    → Detail view
GET  /dashboard/peer-status          → What are competitors doing?
POST /dashboard/alerts/{id}/create-task → Create JIRA ticket
```

---

## DETAILED BUILD PLAN

### Week 2: Scheduler + Notification Foundation

#### Task 2.1: Build Scheduler
```python
# services/scheduling/regulatory_scheduler.py

class RegulatoryScheduler:
    """
    Daily monitoring job - runs 02:00 UTC
    For each bank, check all 6 frameworks for changes
    """
    
    def run_daily_scan(self):
        """Main scheduler entry point"""
        # 1. Get all customers
        # 2. For each customer's frameworks:
        #    - Run CRCS detection (Phase 1)
        #    - Detect changes
        #    - Calculate impact
        #    - Queue notifications
        # 3. Log results
    
    def detect_and_analyze(self, org_id, framework_id):
        """Detect changes + analyze impact for one org"""
        # 1. Call RegulatoryChangeDetector
        # 2. If changes:
        #    - Call ImpactAnalyzer
        #    - Calculate effort hours
        #    - Determine deadline
        #    - Get peer benchmarks
        # 3. Return: AlertData
    
    def queue_notification(self, org_id, alert_data):
        """Add to notification queue"""
        # 1. Create notification record in DB
        # 2. Queue for email sending
        # 3. Add dashboard alert
```

#### Task 2.2: Build Notification Service
```python
# services/notifications/notification_service.py

class NotificationService:
    """
    Sends alerts via email + dashboard
    """
    
    def send_email_alert(self, org_id, alert_data):
        """Send email to compliance team"""
        # 1. Render email template
        # 2. Personalize with org data
        # 3. Send via SendGrid/AWS SES
        # 4. Log delivery
    
    def create_dashboard_alert(self, org_id, alert_data):
        """Create in-app notification"""
        # 1. Store alert in database
        # 2. Mark as "unread"
        # 3. Broadcast to connected dashboards
    
    def email_template(self, alert_data):
        """HTML email template"""
        # Header: What changed
        # Your Impact: Specific to this org
        # Timeline: Deadline
        # Action: Link to dashboard
```

#### Task 2.3: Add Alert Database Table
```sql
CREATE TABLE regulatory_alerts (
    alert_id UUID PRIMARY KEY,
    org_id UUID REFERENCES organizations,
    change_id UUID REFERENCES regulatory_changes,
    framework_id UUID REFERENCES regulatory_frameworks,
    
    -- Impact data (personalized to org)
    affected_asset_count INT,
    portfolio_value_affected_eur DECIMAL,
    affected_tables JSONB,
    estimated_dev_hours INT,
    
    -- Timeline
    regulatory_deadline DATE,
    org_implementation_deadline DATE,
    urgency_level VARCHAR(20),  -- 'low', 'medium', 'high', 'critical'
    
    -- Status
    alert_status VARCHAR(50),  -- 'new', 'viewed', 'acknowledged', 'in_progress'
    email_sent_at TIMESTAMP,
    dashboard_viewed_at TIMESTAMP,
    
    -- Benchmarking
    peer_count_affected INT,
    peer_response_avg_weeks DECIMAL,
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

---

### Week 3: Competitive Benchmarking + Task Automation

#### Task 3.1: Build Benchmarking Engine
```python
# services/intelligence/benchmarking.py

class CompetitiveBenchmarking:
    """
    Analyze what peer banks are doing
    """
    
    def get_peer_status(self, org_id, framework_id):
        """
        Returns: How are competitors responding?
        """
        # 1. Find peer banks (same sector, similar size)
        # 2. For this framework:
        #    - Get their current version
        #    - Get their update status
        #    - Estimate their timeline
        # 3. Return comparison
    
    def estimate_peer_timeline(self, framework, peer_implementations):
        """
        Based on similar changes in history,
        estimate how long peers will take
        """
        # 1. Look at historical implementations
        # 2. Calculate average implementation time
        # 3. Return distribution
```

#### Task 3.2: Build Task Automation
```python
# services/integrations/task_automation.py

class TaskAutomation:
    """
    Create tickets in bank's project management system
    """
    
    def create_jira_ticket(self, org_id, alert_data, jira_config):
        """
        Create JIRA ticket for engineering team
        """
        # 1. Get org's JIRA credentials
        # 2. Create ticket:
        #    - Title: "Implement [Framework] [version]"
        #    - Description: Impact analysis
        #    - Effort: estimated_dev_hours
        #    - Deadline: org_implementation_deadline
        #    - Labels: framework, compliance
        # 3. Return ticket URL
    
    def create_linear_ticket(self, org_id, alert_data, linear_config):
        """Create Linear ticket (alternative to JIRA)"""
        # Similar to JIRA
    
    def create_slack_message(self, org_id, alert_data, slack_config):
        """Post alert to Slack #compliance channel"""
        # 1. Get org's Slack webhook
        # 2. Post formatted message
        # 3. Add action buttons (view dashboard, create task)
```

---

### Week 4: Dashboard + Integrations

#### Task 4.1: Build Alert Dashboard Endpoints
```python
# api/routes/alerts_dashboard.py

@router.get("/dashboard/alerts")
async def list_alerts(org_id: str, status: str = None, db: Session = Depends(get_db)):
    """
    List all alerts for org
    Filters: new, viewed, acknowledged, in_progress
    """
    # 1. Get all regulatory_alerts for org_id
    # 2. Filter by status if provided
    # 3. Sort by urgency_level DESC, regulatory_deadline ASC
    # 4. Return with impact summary

@router.get("/dashboard/alerts/{alert_id}")
async def get_alert_detail(alert_id: str, db: Session = Depends(get_db)):
    """
    Get full alert details + recommended actions
    """
    # 1. Get alert record
    # 2. Get associated change details
    # 3. Get affected assets (for this org)
    # 4. Get peer benchmarks
    # 5. Return comprehensive view

@router.get("/dashboard/peer-status")
async def get_peer_status(org_id: str, framework_id: str, db: Session = Depends(get_db)):
    """
    What are peer banks doing with this framework?
    """
    # 1. Find peers (sector, size)
    # 2. Get their version adoption
    # 3. Get their timeline estimates
    # 4. Return benchmarking data

@router.post("/dashboard/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    """
    Bank acknowledges receipt of alert
    """
    # 1. Update alert status to "acknowledged"
    # 2. Log timestamp
    # 3. Notify account manager

@router.post("/dashboard/alerts/{alert_id}/create-task")
async def create_task_from_alert(alert_id: str, system: str, config: dict, db: Session = Depends(get_db)):
    """
    Create task in bank's JIRA/Linear
    system: "jira" or "linear"
    config: org's API credentials
    """
    # 1. Get alert details
    # 2. Call TaskAutomation.create_jira_ticket() or create_linear_ticket()
    # 3. Return ticket URL
```

#### Task 4.2: Update API to Include Alerts
```python
# Update /api/v1/info endpoint to show:
{
    "alerts": {
        "total_active": 5,
        "new_this_week": 2,
        "critical": 1,
        "next_deadline": "2026-08-31"
    },
    "recent_changes": [
        {
            "framework": "EU Taxonomy",
            "version": "v2.1",
            "detected_date": "2026-06-26",
            "your_deadline": "2026-12-31",
            "effort_hours": 40,
            "affected_assets": 47,
            "peer_count": 12,
            "status": "new"
        }
    ]
}
```

---

### Week 5: Email Templates + Integrations

#### Task 5.1: Email Templates
```python
# services/notifications/email_templates.py

ALERT_EMAIL_TEMPLATE = """
<h1>⚠️ Regulatory Change Detected</h1>

<h2>What Changed</h2>
<p>{{ framework.framework_name }} was updated on {{ change.detected_date }}</p>
<p>{{ change.new_version }} effective {{ change.effective_date }}</p>

<h2>Your Impact ({{ org.name }})</h2>
<table>
  <tr>
    <td>Affected Assets:</td>
    <td>{{ alert.affected_asset_count }} of {{ org.total_assets }}</td>
  </tr>
  <tr>
    <td>Portfolio Value At Risk:</td>
    <td>€{{ alert.portfolio_value_affected_eur }}</td>
  </tr>
  <tr>
    <td>Implementation Effort:</td>
    <td>{{ alert.estimated_dev_hours }} hours</td>
  </tr>
  <tr>
    <td>Your Deadline:</td>
    <td>{{ alert.org_implementation_deadline }}</td>
  </tr>
  <tr>
    <td>Urgency:</td>
    <td style="color: {{ urgency_color }}">{{ alert.urgency_level }}</td>
  </tr>
</table>

<h2>Competitive Context</h2>
<p>{{ alert.peer_count_affected }} similar banks affected</p>
<p>Average implementation time: {{ alert.peer_response_avg_weeks }} weeks</p>

<h2>Next Steps</h2>
<ol>
  <li>Review impact in your dashboard: [LINK]</li>
  <li>Discuss with engineering team</li>
  <li>Create task in JIRA/Linear [BUTTON]</li>
  <li>Track progress in dashboard</li>
</ol>

<footer>
Questions? Reply to this email or contact your account manager.
</footer>
"""
```

#### Task 5.2: Integration Setup
```python
# services/integrations/integration_config.py

class IntegrationConfig:
    """
    Configure email, Slack, JIRA, Linear for org
    """
    
    def setup_email(self, org_id, email_recipients):
        """Who gets alerted emails?"""
        # Store: compliance_email@bank.com, manager@bank.com
    
    def setup_jira(self, org_id, jira_url, api_token, project_key):
        """Connect to JIRA"""
        # Store encrypted credentials
    
    def setup_slack(self, org_id, webhook_url, channel):
        """Connect to Slack"""
        # Store webhook URL
    
    def setup_linear(self, org_id, api_key, team_id):
        """Connect to Linear"""
        # Store API key
```

---

### Week 6: Testing + Deployment

#### Task 6.1: End-to-End Testing
```
Test Scenario: EU Taxonomy v2.1 change detected

1. Scraper finds EU Taxonomy v2.1 (June 26)
2. Change detector identifies it as new
3. Analyst confirms it's real
4. For EACH bank:
   5. Impact analyzer runs:
      - Scans their assets
      - Counts affected (47 assets)
      - Calculates effort (40 hours)
      - Determines deadline (Dec 31)
      - Gets peer benchmarks (12 banks affected)
   6. Email alert queued
   7. Dashboard alert created
   8. Slack notification sent
   9. JIRA ticket creation offered
```

#### Task 6.2: Deployment
```
1. Deploy scheduler to background worker
2. Configure daily 02:00 UTC run
3. Setup email service (SendGrid/SES)
4. Configure Slack/JIRA integrations
5. Test with beta customer
6. Monitor first 7 days
```

---

## FILES TO CREATE

```
services/
├── scheduling/
│   ├── __init__.py
│   ├── regulatory_scheduler.py      (400 lines) ← Daily monitoring
│   └── scheduler_config.py           (100 lines) ← Cron configuration
│
├── notifications/
│   ├── __init__.py
│   ├── notification_service.py      (300 lines) ← Email + dashboard
│   ├── email_templates.py           (150 lines) ← HTML templates
│   └── email_config.py              (80 lines)  ← SendGrid setup
│
├── intelligence/
│   ├── __init__.py
│   └── benchmarking.py              (250 lines) ← Peer analysis
│
└── integrations/
    ├── __init__.py
    ├── task_automation.py           (300 lines) ← JIRA/Linear
    └── integration_config.py        (150 lines) ← Credentials

api/
└── routes/
    └── alerts_dashboard.py          (350 lines) ← Dashboard APIs

core/
└── db/
    └── models_alerts.py             (200 lines) ← Alert schema
```

---

## SUCCESS CRITERIA (Phase 2)

### Week 2-3
- [ ] Scheduler runs daily without errors
- [ ] CRCS integrates with scheduler
- [ ] Email alerts sent within 2 hours of detection

### Week 4-5
- [ ] Dashboard shows all alerts
- [ ] Peer benchmarking data displayed
- [ ] JIRA/Linear integration working

### Week 6
- [ ] End-to-end test: Change → Email → Dashboard → JIRA ✅
- [ ] Beta customer receives alerts before competitors
- [ ] 0 email delivery failures
- [ ] Dashboard responsive (< 200ms load)

---

## METRICS TO TRACK

**Real-time Performance:**
- Time from change detection to email sent (target: < 2 hours)
- Email delivery rate (target: > 99%)
- Dashboard alert visibility (target: 90% within 24 hours)

**Business Impact:**
- Customer urgency (are they acting on alerts?)
- Task creation rate (what % create JIRA ticket)
- Peer benchmarking engagement (are they viewing it?)

**Operational:**
- Scheduler uptime (target: 99.9%)
- False alert rate (target: < 5%)
- Customer satisfaction (target: NPS > 50)

---

## READY TO BUILD

**Status:** ✅ Architecture defined, files planned, tasks sequenced

**Start:** Immediately with Task 2.1 (Scheduler)

**Timeline:** 4-5 weeks to full Phase 2 deployment

**Next Action:** Build `services/scheduling/regulatory_scheduler.py`
