"""
Email Template Rendering
HTML email templates for regulatory alerts
"""


def render_alert_email(data: dict) -> str:
    """
    Render regulatory alert email

    Args:
        data: {
            org_name, framework_name, change_date,
            affected_assets, total_assets, portfolio_value_affected,
            dev_hours, deadline, urgency, peer_count, peer_avg_weeks,
            dashboard_url
        }
    """

    urgency_color = {
        'critical': '#d32f2f',
        'high': '#f57c00',
        'medium': '#fbc02d',
        'low': '#388e3c'
    }.get(data.get('urgency', 'medium'), '#f57c00')

    affected_pct = 0
    if data.get('total_assets') and data.get('affected_assets'):
        affected_pct = int((data['affected_assets'] / data['total_assets']) * 100)

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
            color: white;
            padding: 30px 20px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .header p {{
            margin: 8px 0 0 0;
            font-size: 14px;
            opacity: 0.9;
        }}
        .alert-box {{
            background: #fff3e0;
            border-left: 4px solid {urgency_color};
            padding: 20px;
            margin: 20px;
        }}
        .alert-title {{
            font-size: 16px;
            font-weight: 600;
            color: #e65100;
            margin: 0 0 8px 0;
        }}
        .alert-message {{
            font-size: 14px;
            color: #666;
            margin: 0;
        }}
        .content {{
            padding: 20px;
        }}
        .section {{
            margin-bottom: 24px;
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            color: #1976d2;
            margin: 0 0 12px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid #e3f2fd;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 16px;
        }}
        .metric {{
            background: #f5f5f5;
            padding: 12px;
            border-radius: 4px;
        }}
        .metric-label {{
            font-size: 12px;
            color: #999;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 4px;
        }}
        .metric-value {{
            font-size: 20px;
            font-weight: 600;
            color: #1976d2;
        }}
        .metric-unit {{
            font-size: 12px;
            color: #999;
            font-weight: normal;
            margin-left: 4px;
        }}
        .urgency-badge {{
            display: inline-block;
            background: {urgency_color};
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .peer-context {{
            background: #e3f2fd;
            padding: 12px;
            border-radius: 4px;
            margin: 12px 0;
        }}
        .peer-context-title {{
            font-size: 13px;
            font-weight: 600;
            color: #1565c0;
            margin-bottom: 8px;
        }}
        .peer-context-text {{
            font-size: 13px;
            color: #0d47a1;
            margin: 0;
        }}
        .button {{
            display: inline-block;
            background: #1976d2;
            color: white;
            padding: 12px 24px;
            border-radius: 4px;
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
            margin-right: 12px;
            margin-bottom: 12px;
        }}
        .button:hover {{
            background: #1565c0;
        }}
        .button-secondary {{
            background: #fff;
            color: #1976d2;
            border: 2px solid #1976d2;
        }}
        .button-secondary:hover {{
            background: #f5f5f5;
        }}
        .footer {{
            background: #f5f5f5;
            padding: 20px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #999;
            text-align: center;
        }}
        .footer a {{
            color: #1976d2;
            text-decoration: none;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
        }}
        th {{
            background: #f5f5f5;
            padding: 8px;
            text-align: left;
            font-size: 12px;
            font-weight: 600;
            color: #666;
            border-bottom: 1px solid #ddd;
        }}
        td {{
            padding: 8px;
            border-bottom: 1px solid #eee;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>⚠️ Regulatory Change Detected</h1>
            <p>{data.get('org_name', 'Organization')} • {data.get('framework_name', 'Framework')}</p>
        </div>

        <!-- Alert Box -->
        <div class="alert-box">
            <div class="alert-title">What Changed</div>
            <div class="alert-message">
                {data.get('framework_name')} was updated on {data.get('change_date', 'N/A')}
            </div>
        </div>

        <!-- Content -->
        <div class="content">
            <!-- Your Impact Section -->
            <div class="section">
                <div class="section-title">Your Impact</div>

                <div style="margin-bottom: 12px;">
                    <span class="urgency-badge">{data.get('urgency', 'medium')}</span>
                </div>

                <div class="metric-grid">
                    <div class="metric">
                        <div class="metric-label">Affected Assets</div>
                        <div class="metric-value">
                            {data.get('affected_assets', 0)}
                            <span class="metric-unit">of {data.get('total_assets', 0)}</span>
                        </div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Portfolio at Risk</div>
                        <div class="metric-value">
                            €{data.get('portfolio_value_affected', 0):,.0f}
                        </div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Dev Effort</div>
                        <div class="metric-value">
                            {data.get('dev_hours', 0)}
                            <span class="metric-unit">hours</span>
                        </div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Deadline</div>
                        <div class="metric-value">
                            {data.get('deadline', 'N/A')[:10]}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Competitive Context -->
            <div class="section">
                <div class="section-title">Competitive Context</div>

                <div class="peer-context">
                    <div class="peer-context-title">Peer Banks Affected</div>
                    <div class="peer-context-text">
                        {data.get('peer_count', 0)} similar banks detected this change
                    </div>
                </div>

                <div class="peer-context">
                    <div class="peer-context-title">Average Implementation Time</div>
                    <div class="peer-context-text">
                        {data.get('peer_avg_weeks', 0)} weeks (based on similar frameworks)
                    </div>
                </div>
            </div>

            <!-- Details Table -->
            <div class="section">
                <div class="section-title">Summary</div>

                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                    </tr>
                    <tr>
                        <td>Framework</td>
                        <td>{data.get('framework_name', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td>Changed</td>
                        <td>{data.get('change_date', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td>Assets Affected</td>
                        <td>{data.get('affected_assets', 0)} / {data.get('total_assets', 0)} ({affected_pct}%)</td>
                    </tr>
                    <tr>
                        <td>Implementation Effort</td>
                        <td>{data.get('dev_hours', 0)} dev hours</td>
                    </tr>
                    <tr>
                        <td>Your Deadline</td>
                        <td><strong>{data.get('deadline', 'N/A')}</strong></td>
                    </tr>
                    <tr>
                        <td>Urgency Level</td>
                        <td><span class="urgency-badge">{data.get('urgency', 'medium')}</span></td>
                    </tr>
                </table>
            </div>

            <!-- Next Steps -->
            <div class="section">
                <div class="section-title">Next Steps</div>

                <p style="margin: 0 0 12px 0; font-size: 14px; color: #666;">
                    1. Review the impact in your dashboard
                </p>
                <p style="margin: 0 0 12px 0; font-size: 14px; color: #666;">
                    2. Discuss with your engineering team
                </p>
                <p style="margin: 0 0 12px 0; font-size: 14px; color: #666;">
                    3. Create a task in your project management system
                </p>
                <p style="margin: 0; font-size: 14px; color: #666;">
                    4. Track progress in your dashboard
                </p>

                <div style="margin-top: 20px;">
                    <a href="{data.get('dashboard_url', '#')}" class="button">
                        Review in Dashboard
                    </a>
                </div>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p style="margin: 0 0 8px 0;">
                Climate Intelligence Platform • Real-Time Regulatory Monitoring
            </p>
            <p style="margin: 0 0 8px 0;">
                <a href="https://climate-platform.com/docs">Documentation</a> •
                <a href="https://climate-platform.com/settings">Notification Settings</a> •
                <a href="https://climate-platform.com/support">Support</a>
            </p>
            <p style="margin: 0; font-size: 11px;">
                This is an automated alert from your regulatory monitoring system.
                <br>
                You received this because you're on the compliance team at {data.get('org_name', 'your organization')}.
            </p>
        </div>
    </div>
</body>
</html>
"""


def render_summary_email(data: dict) -> str:
    """Render weekly summary email"""
    # TODO: Implement weekly summary template
    pass


def render_digest_email(data: dict) -> str:
    """Render daily/weekly digest email"""
    # TODO: Implement digest template
    pass
