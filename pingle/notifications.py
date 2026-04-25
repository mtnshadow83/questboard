"""
questboard notifications — Windows toast popups for /pings board activity.

Watches the Questboard activity_log for new events on the /pings project
and displays Windows native toast notifications via PowerShell.

Usage:
    python notifications.py
"""

import sqlite3
import os
import sys
import subprocess
import time
import textwrap

DB_PATH = os.path.join(
    os.path.expanduser("~"),
    "library", "0-system", "claude", "toolsets", "questboard", "db", "questboard.db",
)
QB_URL = "http://localhost:5151"
POLL_INTERVAL = 3  # seconds
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notifications.log")


def log(msg):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def get_pings_project_id(db):
    row = db.execute("SELECT id FROM projects WHERE name='pings'").fetchone()
    return row["id"] if row else None


def get_max_activity_id():
    try:
        db = get_db()
        row = db.execute("SELECT MAX(id) as m FROM activity_log").fetchone()
        db.close()
        return row["m"] or 0
    except Exception:
        return 0


def send_toast(ticket_id, title, action, detail):
    """Send a Windows native toast notification via PowerShell."""
    # Build action label
    if action == "created":
        action_text = "New ticket"
    elif detail and "->" in detail:
        new_status = detail.split("->")[-1].strip()
        action_text = f"Status: {new_status}"
    else:
        action_text = "Updated"

    heading = f"#{ticket_id} — {action_text}"
    # Escape XML special chars
    heading_safe = heading.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    title_safe = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    url = f"{QB_URL}/ticket/{ticket_id}"

    ps_script = textwrap.dedent(f"""\
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null

        $template = @"
        <toast duration="long" scenario="reminder">
            <visual>
                <binding template="ToastGeneric">
                    <text>{heading_safe}</text>
                    <text>{title_safe}</text>
                </binding>
            </visual>
            <actions>
                <action content="Open Ticket" activationType="protocol" arguments="{url}"/>
                <action content="Dismiss" activationType="system" arguments="dismiss"/>
            </actions>
        </toast>
"@

        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)

        $appId = 'Questboard.Notifications'
        $toast = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId)
        $toast.Show([Windows.UI.Notifications.ToastNotification]::new($xml))
    """)

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log(f"Toast error: {result.stderr.strip()}")
        else:
            log(f"Toast sent: #{ticket_id} {title}")
    except Exception as e:
        log(f"Toast exception: {e}")


def poll_loop():
    last_seen_id = get_max_activity_id()
    log(f"Watcher started. last_seen_id={last_seen_id}")
    print(f"Questboard notifications running. Watching /pings board... (last_seen_id={last_seen_id})")

    while True:
        try:
            db = get_db()
            pings_id = get_pings_project_id(db)
            if pings_id is not None:
                rows = db.execute("""
                    SELECT a.id, a.ticket_id, a.action, a.detail, a.created_at,
                           t.title
                    FROM activity_log a
                    JOIN tickets t ON t.id = a.ticket_id
                    WHERE a.id > ?
                      AND t.project_id = ?
                      AND a.action IN ('created', 'status')
                    ORDER BY a.id
                """, (last_seen_id, pings_id)).fetchall()

                for r in rows:
                    last_seen_id = r["id"]
                    log(f"Event: #{r['ticket_id']} {r['title']} [{r['action']}] {r['detail']}")
                    send_toast(r["ticket_id"], r["title"], r["action"], r["detail"])
            db.close()
        except Exception as e:
            log(f"Poll error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    poll_loop()
