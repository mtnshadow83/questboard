"""
questboard — Agent-native project management tool.

CLI for agents (context-cheap), web UI for humans (kanban on localhost).
SQLite-backed, single-file, same ecosystem as Abadar and Desna.

Usage:
    python questboard.py <command> [args]
    python questboard.py serve [--port 5151]
"""

import sqlite3
import os
import sys
import argparse
import datetime
import json
import textwrap

# Fix Windows console encoding for Unicode content
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_DIR = os.path.join(os.path.expanduser("~"), "library", "0-system", "claude", "toolsets", "questboard", "db")
DB_DEFAULT = "questboard.db"
DB_PATH = os.path.join(DB_DIR, DB_DEFAULT)
MESSAGEBOARD_DIR = os.path.expanduser("~/library/0-system/claude/messageboard")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def list_dbs():
    """Return list of .db filenames available in DB_DIR."""
    if not os.path.isdir(DB_DIR):
        return []
    return sorted(f for f in os.listdir(DB_DIR) if f.endswith(".db"))


def get_db(db_path=None):
    path = db_path or DB_PATH
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL DEFAULT 'agent' CHECK(role IN ('human', 'agent')),
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS statuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            is_closed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id),
            status_id INTEGER NOT NULL REFERENCES statuses(id),
            assigned_to INTEGER REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS ticket_labels (
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            label_id INTEGER NOT NULL REFERENCES labels(id),
            PRIMARY KEY (ticket_id, label_id)
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            user_id INTEGER REFERENCES users(id),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            user_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
    """)

    # Seed default statuses if empty
    existing = db.execute("SELECT COUNT(*) FROM statuses").fetchone()[0]
    if existing == 0:
        seed = [
            ("queued", 0, 0),
            ("in-progress", 1, 0),
            ("blocked", 2, 0),
            ("review", 3, 0),
            ("done", 4, 1),
            ("n/a", 5, 1),
        ]
        db.executemany("INSERT INTO statuses (name, display_order, is_closed) VALUES (?, ?, ?)", seed)

    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def priority_dots(p):
    if p <= 0: return ""
    if p == 1: return "o"
    if p == 2: return "oo"
    if p == 3: return "ooo"
    return "!" * min(p, 5)


def resolve_user(db, name_or_id):
    """Resolve a user by name or ID. Returns row or None."""
    if name_or_id is None:
        return None
    try:
        uid = int(name_or_id)
        return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    except ValueError:
        return db.execute("SELECT * FROM users WHERE name=?", (name_or_id,)).fetchone()


def resolve_status(db, name_or_id):
    """Resolve a status by name or ID."""
    try:
        sid = int(name_or_id)
        return db.execute("SELECT * FROM statuses WHERE id=?", (sid,)).fetchone()
    except ValueError:
        return db.execute("SELECT * FROM statuses WHERE name=?", (name_or_id,)).fetchone()


def resolve_project(db, name_or_id):
    """Resolve a project by name or ID."""
    if name_or_id is None:
        return None
    try:
        pid = int(name_or_id)
        return db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    except ValueError:
        return db.execute("SELECT * FROM projects WHERE name=?", (name_or_id,)).fetchone()


def log_activity(db, ticket_id, user_id, action, detail=""):
    db.execute(
        "INSERT INTO activity_log (ticket_id, user_id, action, detail) VALUES (?, ?, ?, ?)",
        (ticket_id, user_id, action, detail),
    )


def post_to_messageboard(message):
    """Post a status change to the agent messageboard."""
    if not os.path.isdir(MESSAGEBOARD_DIR):
        return
    ts = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    filename = f"questboard-{ts}.md"
    filepath = os.path.join(MESSAGEBOARD_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# Questboard Update — {now()}\n\n{message}\n")


def get_ticket_labels(db, ticket_id):
    rows = db.execute("""
        SELECT l.name FROM labels l
        JOIN ticket_labels tl ON tl.label_id = l.id
        WHERE tl.ticket_id = ?
        ORDER BY l.name
    """, (ticket_id,)).fetchall()
    return [r["name"] for r in rows]


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def cmd_user_add(args):
    db = get_db()
    try:
        db.execute("INSERT INTO users (name, role) VALUES (?, ?)", (args.name, args.role))
        db.commit()
        print(f"User: {args.name} ({args.role})")
    except sqlite3.IntegrityError:
        print(f"User '{args.name}' already exists")
    db.close()


def cmd_user_list(args):
    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY name").fetchall()
    for r in rows:
        print(f"  {r['name']:20s} {r['role']}")
    db.close()


def cmd_project_add(args):
    db = get_db()
    desc = args.description or ""
    try:
        cur = db.execute("INSERT INTO projects (name, description) VALUES (?, ?)", (args.name, desc))
        db.commit()
        print(f"Project #{cur.lastrowid}: {args.name}")
    except sqlite3.IntegrityError:
        print(f"Project '{args.name}' already exists")
    db.close()


def cmd_project_list(args):
    db = get_db()
    show_archived = getattr(args, "archived", False)
    if show_archived:
        rows = db.execute("SELECT * FROM projects ORDER BY name").fetchall()
    else:
        rows = db.execute("SELECT * FROM projects WHERE archived=0 ORDER BY name").fetchall()
    for r in rows:
        open_count = db.execute("""
            SELECT COUNT(*) FROM tickets t
            JOIN statuses s ON s.id = t.status_id
            WHERE t.project_id = ? AND s.is_closed = 0
        """, (r["id"],)).fetchone()[0]
        arc = " [archived]" if r["archived"] else ""
        print(f"  #{r['id']:3d} {r['name']:30s} ({open_count} open){arc}")
    db.close()


def cmd_project_archive(args):
    db = get_db()
    proj = resolve_project(db, args.project)
    if not proj:
        print(f"Project not found: {args.project}")
        db.close()
        return
    db.execute("UPDATE projects SET archived=1 WHERE id=?", (proj["id"],))
    db.commit()
    print(f"Archived: {proj['name']}")
    db.close()


PROTECTED_PROJECTS = {"artificer"}  # agents cannot create tickets here directly


def cmd_add(args):
    db = get_db()
    proj = resolve_project(db, args.project)
    if not proj:
        print(f"Project not found: {args.project}")
        db.close()
        return

    # Policy: agents cannot write directly to protected projects
    creator = resolve_user(db, args.creator) if args.creator else None
    if proj["name"].lower() in PROTECTED_PROJECTS:
        if creator and creator["role"] == "agent":
            pings = db.execute("SELECT * FROM projects WHERE name='pings'").fetchone()
            if pings:
                print(f"Policy: agents cannot write to '{proj['name']}'. Routing to /pings.")
                proj = pings
            else:
                print(f"Policy: agents cannot write to '{proj['name']}'. Create a 'pings' project first.")
                db.close()
                return

    # Default status is queued (display_order 0)
    status = db.execute("SELECT * FROM statuses ORDER BY display_order LIMIT 1").fetchone()

    assignee = resolve_user(db, args.assign) if args.assign else None

    cur = db.execute(
        "INSERT INTO tickets (project_id, status_id, assigned_to, title, description, priority, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (proj["id"], status["id"], assignee["id"] if assignee else None, args.title,
         args.description or "", args.priority or 0, creator["id"] if creator else None),
    )
    ticket_id = cur.lastrowid

    log_activity(db, ticket_id, creator["id"] if creator else None, "created", args.title)

    # Add labels
    if args.label:
        for lname in args.label:
            label = db.execute("SELECT * FROM labels WHERE name=?", (lname,)).fetchone()
            if not label:
                lcur = db.execute("INSERT INTO labels (name) VALUES (?)", (lname,))
                label_id = lcur.lastrowid
            else:
                label_id = label["id"]
            try:
                db.execute("INSERT INTO ticket_labels (ticket_id, label_id) VALUES (?, ?)", (ticket_id, label_id))
            except sqlite3.IntegrityError:
                pass

    db.commit()

    assignee_str = f" @{assignee['name']}" if assignee else ""
    pri_str = f" {priority_dots(args.priority or 0)}" if args.priority else ""
    print(f"#{ticket_id} {args.title} [{status['name']}]{assignee_str}{pri_str}")
    db.close()


def cmd_edit(args):
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id=?", (args.ticket_id,)).fetchone()
    if not ticket:
        print(f"Ticket not found: {args.ticket_id}")
        db.close()
        return

    changes = []
    if args.title:
        old_title = ticket["title"]
        db.execute("UPDATE tickets SET title=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (args.title, args.ticket_id))
        log_activity(db, args.ticket_id, None, "edited", f"title: {old_title} -> {args.title}")
        changes.append(f"title -> {args.title}")

    if args.description is not None:
        db.execute("UPDATE tickets SET description=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (args.description, args.ticket_id))
        log_activity(db, args.ticket_id, None, "edited", f"description updated")
        changes.append("description updated")

    if args.priority is not None:
        db.execute("UPDATE tickets SET priority=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (args.priority, args.ticket_id))
        log_activity(db, args.ticket_id, None, "edited", f"priority -> {args.priority}")
        changes.append(f"priority -> {args.priority}")

    if not changes:
        print(f"#{args.ticket_id} — nothing to change (provide --title, --description, or --priority)")
        db.close()
        return

    db.commit()
    print(f"#{args.ticket_id} updated: {', '.join(changes)}")
    db.close()


def cmd_list(args):
    db = get_db()
    query = """
        SELECT t.*, s.name as status_name, s.is_closed,
               u.name as assignee_name, p.name as project_name
        FROM tickets t
        JOIN statuses s ON s.id = t.status_id
        LEFT JOIN users u ON u.id = t.assigned_to
        JOIN projects p ON p.id = t.project_id
        WHERE 1=1
    """
    params = []

    if args.project:
        proj = resolve_project(db, args.project)
        if proj:
            query += " AND t.project_id = ?"
            params.append(proj["id"])

    if args.status:
        st = resolve_status(db, args.status)
        if st:
            query += " AND t.status_id = ?"
            params.append(st["id"])

    if args.assign:
        user = resolve_user(db, args.assign)
        if user:
            query += " AND t.assigned_to = ?"
            params.append(user["id"])

    if args.label:
        query += " AND t.id IN (SELECT tl.ticket_id FROM ticket_labels tl JOIN labels l ON l.id = tl.label_id WHERE l.name = ?)"
        params.append(args.label)

    if not args.all and not args.status:
        query += " AND s.is_closed = 0"

    query += " ORDER BY t.priority DESC, t.id"

    rows = db.execute(query, params).fetchall()
    for r in rows:
        labels = get_ticket_labels(db, r["id"])
        assignee = f"@{r['assignee_name']}" if r["assignee_name"] else ""
        label_str = " ".join(labels)
        pri = priority_dots(r["priority"])
        done_mark = "x" if r["is_closed"] else " "
        print(f"  [{done_mark}] #{r['id']:4d} {r['title']:40s} {assignee:12s} {r['status_name']:14s} {label_str} {pri}")
    if not rows:
        print("  (no tickets)")
    db.close()


def cmd_show(args):
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id=?", (args.ticket_id,)).fetchone()
    if not ticket:
        print(f"Ticket not found: {args.ticket_id}")
        db.close()
        return

    proj = db.execute("SELECT * FROM projects WHERE id=?", (ticket["project_id"],)).fetchone()
    status = db.execute("SELECT * FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
    assignee = db.execute("SELECT * FROM users WHERE id=?", (ticket["assigned_to"],)).fetchone() if ticket["assigned_to"] else None
    creator = db.execute("SELECT * FROM users WHERE id=?", (ticket["created_by"],)).fetchone() if ticket["created_by"] else None
    labels = get_ticket_labels(db, ticket["id"])

    print(f"#{ticket['id']} {ticket['title']}")
    print(f"  Project:  {proj['name']} (#{proj['id']})")
    print(f"  Status:   {status['name']}")
    if assignee:
        print(f"  Assigned: {assignee['name']}")
    print(f"  Priority: {ticket['priority']} {priority_dots(ticket['priority'])}")
    if labels:
        print(f"  Labels:   {', '.join(labels)}")
    if creator:
        print(f"  Created:  {ticket['created_at']} by {creator['name']}")
    else:
        print(f"  Created:  {ticket['created_at']}")
    if ticket["description"]:
        print(f"  ---")
        print(f"  {ticket['description']}")

    # Comments
    comments = db.execute("""
        SELECT c.*, u.name as user_name FROM comments c
        LEFT JOIN users u ON u.id = c.user_id
        WHERE c.ticket_id = ? ORDER BY c.created_at
    """, (ticket["id"],)).fetchall()
    if comments:
        print(f"  ---")
        for c in comments:
            who = c["user_name"] or "system"
            print(f"  [{c['created_at']}] {who}: {c['body']}")

    db.close()


def cmd_status(args):
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id=?", (args.ticket_id,)).fetchone()
    if not ticket:
        print(f"Ticket not found: {args.ticket_id}")
        db.close()
        return

    new_status = resolve_status(db, args.status_name)
    if not new_status:
        print(f"Status not found: {args.status_name}")
        db.close()
        return

    old_status = db.execute("SELECT name FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
    db.execute("UPDATE tickets SET status_id=?, updated_at=datetime('now','localtime') WHERE id=?",
               (new_status["id"], args.ticket_id))
    log_activity(db, args.ticket_id, None, "status", f"{old_status['name']} -> {new_status['name']}")
    db.commit()

    print(f"#{args.ticket_id} -> {new_status['name']}")
    post_to_messageboard(f"Ticket #{args.ticket_id} ({ticket['title']}): {old_status['name']} -> {new_status['name']}")
    db.close()


def cmd_assign(args):
    db = get_db()
    user = resolve_user(db, args.user)
    if not user:
        print(f"User not found: {args.user}")
        db.close()
        return

    for tid in args.ticket_ids:
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not ticket:
            print(f"Ticket not found: {tid}")
            continue
        db.execute("UPDATE tickets SET assigned_to=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (user["id"], tid))
        log_activity(db, tid, user["id"], "assigned", f"-> @{user['name']}")
        print(f"#{tid} -> @{user['name']}")

    db.commit()
    db.close()


def cmd_move(args):
    db = get_db()
    proj = resolve_project(db, args.project)
    if not proj:
        print(f"Project not found: {args.project}")
        db.close()
        return

    for tid in args.ticket_ids:
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not ticket:
            print(f"Ticket not found: {tid}")
            continue
        db.execute("UPDATE tickets SET project_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (proj["id"], tid))
        log_activity(db, tid, None, "moved", f"-> {proj['name']} (#{proj['id']})")
        print(f"#{tid} moved to {proj['name']} (#{proj['id']})")

    db.commit()
    db.close()


def cmd_done(args):
    db = get_db()
    done_status = db.execute("SELECT * FROM statuses WHERE is_closed=1 ORDER BY display_order LIMIT 1").fetchone()
    if not done_status:
        print("No closed status defined")
        db.close()
        return

    for tid in args.ticket_ids:
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not ticket:
            print(f"Ticket not found: {tid}")
            continue
        old_status = db.execute("SELECT name FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
        db.execute("UPDATE tickets SET status_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (done_status["id"], tid))
        log_activity(db, tid, None, "status", f"{old_status['name']} -> {done_status['name']}")
        print(f"#{tid} -> {done_status['name']}")
        post_to_messageboard(f"Ticket #{tid} ({ticket['title']}): {old_status['name']} -> {done_status['name']}")

    db.commit()
    db.close()


def cmd_block(args):
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id=?", (args.ticket_id,)).fetchone()
    if not ticket:
        print(f"Ticket not found: {args.ticket_id}")
        db.close()
        return

    blocked_status = resolve_status(db, "blocked")
    if not blocked_status:
        print("No 'blocked' status found")
        db.close()
        return

    old_status = db.execute("SELECT name FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
    db.execute("UPDATE tickets SET status_id=?, updated_at=datetime('now','localtime') WHERE id=?",
               (blocked_status["id"], args.ticket_id))
    log_activity(db, args.ticket_id, None, "status", f"{old_status['name']} -> blocked")

    if args.reason:
        db.execute("INSERT INTO comments (ticket_id, body) VALUES (?, ?)", (args.ticket_id, args.reason))
        log_activity(db, args.ticket_id, None, "comment", args.reason)

    db.commit()
    print(f"#{args.ticket_id} -> blocked")
    if args.reason:
        print(f"  Comment: {args.reason}")
    post_to_messageboard(f"Ticket #{args.ticket_id} ({ticket['title']}): blocked" +
                         (f" — {args.reason}" if args.reason else ""))
    db.close()


def cmd_comment(args):
    db = get_db()
    ticket = db.execute("SELECT * FROM tickets WHERE id=?", (args.ticket_id,)).fetchone()
    if not ticket:
        print(f"Ticket not found: {args.ticket_id}")
        db.close()
        return

    user = resolve_user(db, args.user) if args.user else None
    db.execute("INSERT INTO comments (ticket_id, user_id, body) VALUES (?, ?, ?)",
               (args.ticket_id, user["id"] if user else None, args.text))
    log_activity(db, args.ticket_id, user["id"] if user else None, "comment", args.text)
    db.commit()
    print(f"Comment added to #{args.ticket_id}")
    db.close()


def cmd_label(args):
    db = get_db()
    label = db.execute("SELECT * FROM labels WHERE name=?", (args.label_name,)).fetchone()
    if not label:
        cur = db.execute("INSERT INTO labels (name) VALUES (?)", (args.label_name,))
        label_id = cur.lastrowid
    else:
        label_id = label["id"]

    for tid in args.ticket_ids:
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not ticket:
            print(f"Ticket not found: {tid}")
            continue
        try:
            db.execute("INSERT INTO ticket_labels (ticket_id, label_id) VALUES (?, ?)", (tid, label_id))
            log_activity(db, tid, None, "label", f"+{args.label_name}")
            print(f"Label {args.label_name} added to #{tid}")
        except sqlite3.IntegrityError:
            print(f"#{tid} already has label {args.label_name}")

    db.commit()
    db.close()


def cmd_unlabel(args):
    db = get_db()
    label = db.execute("SELECT * FROM labels WHERE name=?", (args.label_name,)).fetchone()
    if not label:
        print(f"Label not found: {args.label_name}")
        db.close()
        return
    for tid in args.ticket_ids:
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not ticket:
            print(f"Ticket not found: {tid}")
            continue
        db.execute("DELETE FROM ticket_labels WHERE ticket_id=? AND label_id=?", (tid, label["id"]))
        log_activity(db, tid, None, "label", f"-{args.label_name}")
        print(f"Label {args.label_name} removed from #{tid}")
    db.commit()
    db.close()


def cmd_promote(args):
    """Move ticket(s) from /pings to a target project (default: artificer)."""
    db = get_db()
    target = resolve_project(db, args.project or "artificer")
    if not target:
        print(f"Project not found: {args.project or 'artificer'}")
        db.close()
        return

    for tid in args.ticket_ids:
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not ticket:
            print(f"Ticket not found: {tid}")
            continue
        old_proj = db.execute("SELECT name FROM projects WHERE id=?", (ticket["project_id"],)).fetchone()
        db.execute("UPDATE tickets SET project_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (target["id"], tid))
        log_activity(db, tid, None, "promoted", f"{old_proj['name']} -> {target['name']}")
        print(f"#{tid} promoted to {target['name']} (#{target['id']})")

    db.commit()
    db.close()


def cmd_label_add(args):
    db = get_db()
    try:
        db.execute("INSERT INTO labels (name, color) VALUES (?, ?)", (args.name, args.color or ""))
        db.commit()
        print(f"Label: {args.name}")
    except sqlite3.IntegrityError:
        print(f"Label '{args.name}' already exists")
    db.close()


def cmd_label_list(args):
    db = get_db()
    rows = db.execute("SELECT * FROM labels ORDER BY name").fetchall()
    for r in rows:
        color = f"  ({r['color']})" if r["color"] else ""
        print(f"  {r['name']}{color}")
    db.close()


def cmd_status_list(args):
    db = get_db()
    rows = db.execute("SELECT * FROM statuses ORDER BY display_order").fetchall()
    for r in rows:
        closed = " (closed)" if r["is_closed"] else ""
        print(f"  {r['display_order']}: {r['name']}{closed}")
    db.close()


def cmd_status_add(args):
    db = get_db()
    closed = 1 if args.closed else 0
    try:
        db.execute("INSERT INTO statuses (name, display_order, is_closed) VALUES (?, ?, ?)",
                   (args.name, args.order, closed))
        db.commit()
        print(f"Status added: {args.name} (order {args.order})")
    except sqlite3.IntegrityError:
        print(f"Status '{args.name}' already exists")
    db.close()


def cmd_status_rename(args):
    db = get_db()
    result = db.execute("UPDATE statuses SET name=? WHERE name=?", (args.new_name, args.old_name))
    if result.rowcount == 0:
        print(f"Status not found: {args.old_name}")
    else:
        db.commit()
        print(f"Status renamed: {args.old_name} -> {args.new_name}")
    db.close()


def cmd_status_reorder(args):
    db = get_db()
    result = db.execute("UPDATE statuses SET display_order=? WHERE name=?", (args.order, args.name))
    if result.rowcount == 0:
        print(f"Status not found: {args.name}")
    else:
        db.commit()
        print(f"Status reorder: {args.name} -> position {args.order}")
    db.close()


# ---------------------------------------------------------------------------
# Web UI (Flask)
# ---------------------------------------------------------------------------

def cmd_serve(args):
    from flask import Flask, render_template_string, request, redirect, url_for

    _serve_dir = os.path.dirname(os.path.abspath(__file__))
    _static_dir = os.environ.get("QB_STATIC", os.path.join(_serve_dir, "visuals"))
    app = Flask(__name__, static_folder=_static_dir, static_url_path="/static")
    port = args.port or 5151

    # Track active DB path for the web session
    app.config["ACTIVE_DB"] = DB_PATH

    LAYOUT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Questboard{% if subtitle %} — {{ subtitle }}{% endif %}</title>
<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">
<link rel="icon" type="image/x-icon" href="/static/questboard.ico">
<link rel="apple-touch-icon" sizes="180x180" href="/static/questboard-mobile-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Questboard">
<meta name="mobile-web-app-capable" content="yes">
<link rel="manifest" href="/manifest.json">
<style>
:root, [data-theme="tavern"] {
    --bg: #1a1510;
    --bg2: #231e18;
    --bg3: #342a20;
    --fg: #e8e0d4;
    --fg2: #b0a898;
    --accent: #CDA473;
    --accent2: #665841;
    --green: #7F9D9D;
    --yellow: #CDA473;
    --red: #a05a3a;
    --blue: #B0AD92;
    --border: #3a3228;
    --card: #231e18;
    --card-hover: #2d261e;
}
[data-theme="goblin-forest"] {
    --bg: #141208;
    --bg2: #1e1a10;
    --bg3: #3A3424;
    --fg: #e4ddd0;
    --fg2: #B0A784;
    --accent: #B0A784;
    --accent2: #5B4730;
    --green: #6a7a4a;
    --yellow: #B0A784;
    --red: #8a4a2a;
    --blue: #908868;
    --border: #332e20;
    --card: #1e1a10;
    --card-hover: #282214;
}
[data-theme="arcane"] {
    --bg: #1a1a2e;
    --bg2: #22223a;
    --bg3: #3F3F6A;
    --fg: #e4e0ea;
    --fg2: #D6D0DD;
    --accent: #94A9C8;
    --accent2: #3F3F6A;
    --green: #7a8aaa;
    --yellow: #D6D0DD;
    --red: #8a5a7a;
    --blue: #8295BE;
    --border: #3a3a5a;
    --card: #22223a;
    --card-hover: #2a2a44;
}
[data-theme="cartographer"] {
    --bg: #1a1c20;
    --bg2: #24262a;
    --bg3: #42454D;
    --fg: #e4dcd6;
    --fg2: #9A9D97;
    --accent: #DC9584;
    --accent2: #42454D;
    --green: #68879C;
    --yellow: #DC9584;
    --red: #b06a5a;
    --blue: #68879C;
    --border: #383a40;
    --card: #24262a;
    --card-hover: #2e3034;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--fg); min-height: 100vh; }
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }

.topbar {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    align-items: center;
    gap: 24px;
}
.topbar h1 { font-size: 18px; color: var(--accent); font-weight: 700; letter-spacing: 1px; }
.topbar h1 a { color: var(--accent); text-decoration: none; }
.topbar h1 a:hover { text-decoration: none; opacity: 0.8; }
.topbar nav { display: flex; gap: 16px; }
.topbar nav a { color: var(--fg2); font-size: 14px; padding: 4px 8px; border-radius: 4px; }
.topbar nav a:hover, .topbar nav a.active { color: var(--fg); background: var(--bg3); text-decoration: none; }

.filters {
    padding: 12px 24px;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
}
.filters select, .filters input {
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 13px;
}
.filters label { color: var(--fg2); font-size: 13px; }

.kanban {
    display: flex;
    gap: 16px;
    padding: 20px 24px;
    overflow-x: auto;
    min-height: calc(100vh - 120px);
    align-items: flex-start;
}
.kanban-col {
    min-width: 280px;
    max-width: 320px;
    flex: 1;
    background: var(--bg2);
    border-radius: 8px;
    border: 1px solid var(--border);
}
.kanban-col-header {
    padding: 12px 16px;
    font-weight: 600;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--fg2);
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.kanban-col-header .count {
    background: var(--bg);
    color: var(--fg2);
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
}
.kanban-cards { padding: 8px; display: flex; flex-direction: column; gap: 8px; }

.card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    cursor: grab;
    transition: background 0.15s, opacity 0.15s, transform 0.15s;
}
.card:active { cursor: grabbing; }
.card.dragging { opacity: 0.4; transform: scale(0.95); }
.card:hover { background: var(--card-hover); border-color: var(--accent2); }
.kanban-col.drag-over { background: var(--bg3); border-color: var(--accent); }
.kanban-cards.drag-over { min-height: 60px; }
.card-id { color: var(--fg2); font-size: 11px; }
.card-title { font-size: 14px; margin: 4px 0 8px 0; line-height: 1.3; }
.card-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.card-assignee { font-size: 12px; color: var(--blue); }
.card-priority { font-size: 12px; color: var(--yellow); font-weight: 700; }
.card-label {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--accent2);
    color: var(--fg);
}
.card-project { font-size: 11px; color: var(--fg2); }

/* Ticket detail */
.ticket-detail {
    max-width: 800px;
    margin: 24px auto;
    padding: 0 24px;
}
.ticket-detail h1 { font-size: 22px; margin-bottom: 16px; }
.ticket-detail .meta-grid {
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 8px 16px;
    margin-bottom: 20px;
    font-size: 14px;
}
.ticket-detail .meta-grid dt { color: var(--fg2); }
.ticket-detail .meta-grid dd { color: var(--fg); }
.ticket-detail .description {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 16px;
    margin-bottom: 20px;
    line-height: 1.6;
    white-space: pre-wrap;
}
.ticket-detail .comment {
    border-left: 3px solid var(--accent2);
    padding: 8px 16px;
    margin-bottom: 12px;
    background: var(--bg2);
    border-radius: 0 6px 6px 0;
}
.ticket-detail .comment .who { color: var(--blue); font-weight: 600; font-size: 13px; }
.ticket-detail .comment .when { color: var(--fg2); font-size: 12px; margin-left: 8px; }
.ticket-detail .comment .body { margin-top: 4px; font-size: 14px; line-height: 1.5; }

.activity-log { margin-top: 20px; }
.activity-log table { width: 100%; border-collapse: collapse; font-size: 13px; }
.activity-log th { text-align: left; color: var(--fg2); padding: 6px 8px; border-bottom: 1px solid var(--border); }
.activity-log td { padding: 6px 8px; border-bottom: 1px solid var(--border); color: var(--fg); }

/* List view */
.list-view { padding: 20px 24px; }
.list-view table { width: 100%; border-collapse: collapse; }
.list-view th { text-align: left; color: var(--fg2); padding: 8px 12px; border-bottom: 2px solid var(--border); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
.list-view td { padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 14px; }
.list-view tr:hover { background: var(--bg2); }

.status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 12px;
    font-weight: 600;
}
.status-queued { background: var(--bg3); color: var(--fg); }
.status-in-progress { background: var(--blue); color: #fff; }
.status-blocked { background: var(--red); color: #fff; }
.status-review { background: var(--yellow); color: #000; }
.status-done { background: var(--green); color: #fff; }
.status-na { background: var(--fg2); color: var(--bg); }

/* Edit forms */
.tag-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: var(--accent2);
    color: var(--fg);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
}
.tag-x {
    cursor: pointer;
    font-size: 14px;
    color: var(--fg2);
    margin-left: 2px;
}
.tag-x:hover { color: var(--red); }
.pri-dot:hover { color: var(--yellow) !important; }

.theme-select {
    margin-left: auto;
    background: var(--bg);
    color: var(--fg2);
    border: 1px solid var(--border);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
}
.theme-select:hover { color: var(--fg); border-color: var(--accent); }

.edit-form {
    max-width: 600px;
    margin: 24px auto;
    padding: 0 24px;
}
.edit-form .field { margin-bottom: 16px; }
.edit-form label { display: block; color: var(--fg2); font-size: 13px; margin-bottom: 4px; }
.edit-form input, .edit-form select, .edit-form textarea {
    width: 100%;
    background: var(--bg);
    color: var(--fg);
    border: 1px solid var(--border);
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 14px;
}
.edit-form textarea { min-height: 100px; resize: vertical; }
.edit-form button {
    background: var(--accent);
    color: #fff;
    border: none;
    padding: 8px 20px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
}
.edit-form button:hover { opacity: 0.9; }

/* Mobile responsive */
@media (max-width: 768px) {
    .topbar { padding: 8px 12px; gap: 8px; flex-wrap: wrap; }
    .topbar h1 { font-size: 15px; }
    .topbar nav { gap: 8px; }
    .topbar nav a { font-size: 13px; padding: 6px 10px; }
    .filters { padding: 8px 12px; gap: 8px; }
    .filters select, .filters input { font-size: 14px; padding: 8px; }
    .filters label { font-size: 12px; }
    .kanban { flex-direction: column; padding: 12px; gap: 12px; }
    .kanban-col { min-width: 100%; max-width: 100%; }
    .card { padding: 10px; }
    .card-title { font-size: 15px; }
    .card-meta { gap: 6px; }
    .list-view { padding: 12px; overflow-x: auto; }
    .list-view table { font-size: 13px; }
    .list-view th, .list-view td { padding: 6px 8px; }
    .ticket-detail { padding: 0 12px; margin: 12px auto; }
    .ticket-detail h1 { font-size: 18px; }
    .ticket-detail .meta-grid { grid-template-columns: 90px 1fr; font-size: 13px; }
    .theme-select { font-size: 11px; }
}
</style>
</head>
<body>
<div class="topbar">
    <h1><a href="/">QUESTBOARD</a></h1>
    <nav>
        <a href="/" class="{{ 'active' if view == 'kanban' else '' }}">Kanban</a>
        <a href="/list" class="{{ 'active' if view == 'list' else '' }}">List</a>
    </nav>
    <form method="post" action="/switch-db" style="margin-left:auto;display:flex;align-items:center;gap:8px;">
        <label style="color:var(--fg2);font-size:13px;">DB:</label>
        <select name="db" onchange="this.form.submit()" style="background:var(--bg);color:var(--fg);border:1px solid var(--border);padding:4px 8px;border-radius:4px;font-size:13px;">
            {% for dbname in available_dbs %}
            <option value="{{ dbname }}" {{ 'selected' if dbname == active_db }}>{{ dbname }}</option>
            {% endfor %}
        </select>
    </form>
    <button id="push-btn" onclick="enablePush()" style="display:none;margin-left:8px;background:var(--accent);color:#fff;border:none;padding:4px 10px;border-radius:4px;font-size:12px;cursor:pointer;">Enable Notifications</button>
    <select class="theme-select" id="theme-toggle" onchange="setTheme(this.value)">
        <option value="tavern">Tavern</option>
        <option value="goblin-forest">Goblin Forest</option>
        <option value="arcane">Arcane</option>
        <option value="cartographer">Cartographer</option>
    </select>
</div>
{% block content %}{% endblock %}
<script>
function setTheme(name) {
    document.documentElement.setAttribute('data-theme', name);
    localStorage.setItem('qb-theme', name);
}
(function() {
    var saved = localStorage.getItem('qb-theme') || 'tavern';
    document.documentElement.setAttribute('data-theme', saved);
    var sel = document.getElementById('theme-toggle');
    if (sel) sel.value = saved;
})();

// --- Push notification registration ---
if ('serviceWorker' in navigator && 'PushManager' in window) {
    navigator.serviceWorker.register('/sw.js').then(function(reg) {
        console.log('SW registered');
        // Check if already subscribed
        reg.pushManager.getSubscription().then(function(sub) {
            if (!sub) {
                // Show enable button
                var btn = document.getElementById('push-btn');
                if (btn) btn.style.display = 'inline-block';
            } else {
                var btn = document.getElementById('push-btn');
                if (btn) btn.textContent = 'Notifications ON';
            }
        });
    });
}
function enablePush() {
    fetch('/api/vapid-key').then(function(r){return r.json()}).then(function(data) {
        var key = data.key;
        var padding = '='.repeat((4 - key.length % 4) % 4);
        var raw = atob(key.replace(/-/g,'+').replace(/_/g,'/') + padding);
        var arr = new Uint8Array(raw.length);
        for (var i=0;i<raw.length;i++) arr[i] = raw.charCodeAt(i);
        navigator.serviceWorker.ready.then(function(reg) {
            reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: arr
            }).then(function(sub) {
                fetch('/api/push-subscribe', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(sub.toJSON())
                }).then(function() {
                    var btn = document.getElementById('push-btn');
                    if (btn) btn.textContent = 'Notifications ON';
                });
            });
        });
    });
}
</script>
</body>
</html>"""

    KANBAN_PAGE = """{% extends layout %}
{% block content %}
<form class="filters" method="get">
    <label>Project:</label>
    <select name="project" onchange="this.form.submit()">
        <option value="">All Projects</option>
        {% for p in projects %}
        <option value="{{ p.id }}" {{ 'selected' if p.id == current_project }}>{{ p.name }}</option>
        {% endfor %}
    </select>
    <label>Assignee:</label>
    <select name="assignee" onchange="this.form.submit()">
        <option value="">Everyone</option>
        {% for u in users %}
        <option value="{{ u.id }}" {{ 'selected' if u.id == current_assignee }}>{{ u.name }}</option>
        {% endfor %}
    </select>
    <label>Label:</label>
    <select name="label" onchange="this.form.submit()">
        <option value="">Any</option>
        {% for l in labels %}
        <option value="{{ l.name }}" {{ 'selected' if l.name == current_label }}>{{ l.name }}</option>
        {% endfor %}
    </select>
</form>
<div class="kanban">
    {% for status in statuses %}
    <div class="kanban-col" data-status-id="{{ status.id }}"
         ondragover="onDragOver(event)" ondragleave="onDragLeave(event)" ondrop="onDrop(event)">
        <div class="kanban-col-header">
            {{ status.name }}
            <span class="count">{{ columns[status.id]|length }}</span>
        </div>
        <div class="kanban-cards"
             ondragover="onDragOver(event)" ondragleave="onDragLeave(event)" ondrop="onDrop(event)">
            {% for t in columns[status.id] %}
            <div class="card" draggable="true" data-ticket-id="{{ t.id }}"
                 ondragstart="onDragStart(event)" ondragend="onDragEnd(event)"
                 onclick="window.location='/ticket/{{ t.id }}'">
                <div class="card-id">#{{ t.id }}{% if t.project_name %} <span class="card-project">{{ t.project_name }}</span>{% endif %}</div>
                <div class="card-title">{{ t.title }}</div>
                <div class="card-meta">
                    {% if t.assignee_name %}<span class="card-assignee">@{{ t.assignee_name }}</span>{% endif %}
                    {% if t.priority > 0 %}<span class="card-priority">{{ '!' * t.priority }}</span>{% endif %}
                    {% for l in t.labels %}<span class="card-label" {% if l.color %}style="background:{{ l.color }}"{% endif %}>{{ l.name }}</span>{% endfor %}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</div>
<script>
let draggedId = null;

function onDragStart(e) {
    draggedId = e.target.closest('.card').dataset.ticketId;
    e.target.closest('.card').classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', draggedId);
}

function onDragEnd(e) {
    e.target.closest('.card').classList.remove('dragging');
    document.querySelectorAll('.kanban-col').forEach(c => c.classList.remove('drag-over'));
}

function onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const col = e.target.closest('.kanban-col');
    if (col) col.classList.add('drag-over');
}

function onDragLeave(e) {
    const col = e.target.closest('.kanban-col');
    if (col && !col.contains(e.relatedTarget)) col.classList.remove('drag-over');
}

function onDrop(e) {
    e.preventDefault();
    const col = e.target.closest('.kanban-col');
    if (!col || !draggedId) return;
    col.classList.remove('drag-over');
    const statusId = col.dataset.statusId;
    fetch('/api/ticket/' + draggedId + '/status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status_id: parseInt(statusId)})
    }).then(r => {
        if (r.ok) window.location.reload();
    });
}
</script>
{% endblock %}"""

    LIST_PAGE = """{% extends layout %}
{% block content %}
<form class="filters" method="get">
    <label>Project:</label>
    <select name="project" onchange="this.form.submit()">
        <option value="">All Projects</option>
        {% for p in projects %}
        <option value="{{ p.id }}" {{ 'selected' if p.id == current_project }}>{{ p.name }}</option>
        {% endfor %}
    </select>
    <label>Assignee:</label>
    <select name="assignee" onchange="this.form.submit()">
        <option value="">Everyone</option>
        {% for u in users %}
        <option value="{{ u.id }}" {{ 'selected' if u.id == current_assignee }}>{{ u.name }}</option>
        {% endfor %}
    </select>
    <label>Show closed:</label>
    <input type="checkbox" name="show_closed" {{ 'checked' if show_closed }} onchange="this.form.submit()" style="width:auto;">
</form>
<div class="list-view">
<table>
    <thead>
        <tr>
            <th>#</th>
            <th>Title</th>
            <th>Project</th>
            <th>Status</th>
            <th>Assignee</th>
            <th>Priority</th>
            <th>Labels</th>
        </tr>
    </thead>
    <tbody>
        {% for t in tickets %}
        <tr>
            <td><a href="/ticket/{{ t.id }}">#{{ t.id }}</a></td>
            <td><a href="/ticket/{{ t.id }}">{{ t.title }}</a></td>
            <td>{{ t.project_name }}</td>
            <td><span class="status-badge status-{{ t.status_name|replace(' ', '-') }}">{{ t.status_name }}</span></td>
            <td>{% if t.assignee_name %}@{{ t.assignee_name }}{% endif %}</td>
            <td>{{ '!' * t.priority if t.priority > 0 else '' }}</td>
            <td>{% for l in t.labels %}<span class="card-label" {% if l.color %}style="background:{{ l.color }}"{% endif %}>{{ l.name }}</span> {% endfor %}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
</div>
{% endblock %}"""

    TICKET_PAGE = """{% extends layout %}
{% block content %}
<div class="ticket-detail">
    <h1>#{{ ticket.id }} {{ ticket.title }}</h1>
    <dl class="meta-grid">
        <dt>Project</dt><dd><a href="/?project={{ ticket.project_id }}">{{ project_name }}</a></dd>
        <dt>Status</dt><dd>
            <form method="post" action="/ticket/{{ ticket.id }}/status" style="display:inline;">
                <select name="status_id" onchange="this.form.submit()">
                    {% for s in statuses %}
                    <option value="{{ s.id }}" {{ 'selected' if s.id == ticket.status_id }}>{{ s.name }}</option>
                    {% endfor %}
                </select>
            </form>
        </dd>
        <dt>Assigned to</dt><dd>
                <select id="assign-select" onchange="updateAssign(this.value)">
                    <option value="">Unassigned</option>
                    {% for u in users %}
                    <option value="{{ u.id }}" {{ 'selected' if ticket.assigned_to == u.id }}>{{ u.name }}</option>
                    {% endfor %}
                </select>
        </dd>
        <dt>Priority</dt><dd>
            <div id="priority-toggle" style="display:inline-flex;gap:4px;">
                {% for i in range(1,6) %}
                <span class="pri-dot" data-val="{{ i }}" onclick="setPriority({{ i }})"
                      style="cursor:pointer;font-size:16px;color:{{ 'var(--yellow)' if i <= ticket.priority else 'var(--border)' }};">!</span>
                {% endfor %}
                <span style="color:var(--fg2);font-size:12px;margin-left:6px;" id="pri-label">{{ ticket.priority }}</span>
            </div>
        </dd>
        <dt>Labels</dt><dd>
            <div id="tag-container" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
                {% for l in labels %}
                <span class="tag-pill" data-label="{{ l }}">{{ l }}<span class="tag-x" onclick="removeLabel('{{ l }}')">&times;</span></span>
                {% endfor %}
                <input type="text" id="tag-input" placeholder="add label..."
                       style="background:transparent;border:none;color:var(--fg);font-size:13px;outline:none;width:100px;"
                       onkeydown="if(event.key==='Enter'){event.preventDefault();addLabel(this.value);this.value='';}">
            </div>
        </dd>
        <dt>Created</dt><dd>{{ ticket.created_at }}{% if creator_name %} by {{ creator_name }}{% endif %}</dd>
        <dt>Updated</dt><dd>{{ ticket.updated_at }}</dd>
    </dl>

    {% if ticket.description %}
    <div class="description">{{ ticket.description }}</div>
    {% endif %}

    <h3 style="color:var(--fg2);font-size:14px;margin-bottom:12px;">Comments</h3>
    {% for c in comments %}
    <div class="comment">
        <span class="who">{{ c.user_name or 'system' }}</span>
        <span class="when">{{ c.created_at }}</span>
        <div class="body">{{ c.body }}</div>
    </div>
    {% endfor %}

    <form method="post" action="/ticket/{{ ticket.id }}/comment" style="margin-top:16px;">
        <textarea name="body" placeholder="Add a comment..." style="width:100%;background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:8px;min-height:60px;resize:vertical;"></textarea>
        <div style="display:flex;gap:8px;align-items:center;margin-top:8px;">
            <select name="user_id" style="background:var(--bg);color:var(--fg);border:1px solid var(--border);padding:6px 10px;border-radius:4px;font-size:13px;">
                {% for u in users %}
                <option value="{{ u.id }}">{{ u.name }}</option>
                {% endfor %}
            </select>
            <button type="submit" style="background:var(--accent);color:#fff;border:none;padding:6px 16px;border-radius:4px;cursor:pointer;">Comment</button>
        </div>
    </form>
    <script>
    function updateAssign(userId) {
        fetch('/ticket/{{ ticket.id }}/assign', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({user_id: userId || null})
        });
    }
    function setPriority(val) {
        fetch('/api/ticket/{{ ticket.id }}/priority', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({priority: val})
        }).then(function() {
            document.querySelectorAll('.pri-dot').forEach(function(dot) {
                dot.style.color = parseInt(dot.dataset.val) <= val ? 'var(--yellow)' : 'var(--border)';
            });
            document.getElementById('pri-label').textContent = val;
        });
    }
    function addLabel(name) {
        name = name.trim();
        if (!name) return;
        fetch('/api/ticket/{{ ticket.id }}/label', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({label: name})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (data.ok) {
                var pill = document.createElement('span');
                pill.className = 'tag-pill';
                pill.dataset.label = name;
                pill.innerHTML = name + '<span class="tag-x" onclick="removeLabel(\'' + name + '\')">&times;</span>';
                var input = document.getElementById('tag-input');
                input.parentNode.insertBefore(pill, input);
            }
        });
    }
    function removeLabel(name) {
        fetch('/api/ticket/{{ ticket.id }}/unlabel', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({label: name})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (data.ok) {
                var pills = document.querySelectorAll('.tag-pill');
                pills.forEach(function(p) { if (p.dataset.label === name) p.remove(); });
            }
        });
    }
    </script>

    <div class="activity-log">
        <h3 style="color:var(--fg2);font-size:14px;margin:20px 0 12px 0;">Activity Log</h3>
        <table>
            <thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>
                {% for a in activity %}
                <tr>
                    <td>{{ a.created_at }}</td>
                    <td>{{ a.user_name or 'system' }}</td>
                    <td>{{ a.action }}</td>
                    <td>{{ a.detail }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}"""

    from jinja2 import BaseLoader, TemplateNotFound

    class InlineLoader(BaseLoader):
        def __init__(self, templates):
            self.templates = templates
        def get_source(self, environment, template):
            if template in self.templates:
                return self.templates[template], template, lambda: True
            raise TemplateNotFound(template)

    app.jinja_loader = InlineLoader({
        "layout": LAYOUT,
        "kanban.html": KANBAN_PAGE,
        "list.html": LIST_PAGE,
        "ticket.html": TICKET_PAGE,
    })

    def get_filter_context(req):
        db = get_db(app.config["ACTIVE_DB"])
        projects = db.execute("SELECT * FROM projects WHERE archived=0 ORDER BY name").fetchall()
        users = db.execute("SELECT * FROM users ORDER BY name").fetchall()
        labels = db.execute("SELECT * FROM labels ORDER BY name").fetchall()

        current_project = int(req.args.get("project", 0) or 0)
        current_assignee = int(req.args.get("assignee", 0) or 0)
        current_label = req.args.get("label", "")

        return db, projects, users, labels, current_project, current_assignee, current_label

    VAPID_APP_KEY = os.environ.get("VAPID_APP_KEY", "BFH8VT5osM1IR6nIIzD0HlXxTw14VoRhkPPV5gylxWvMAVahBGzwwI4h6K-vJCFPRPZMhnCBMn0SjkiPjWFy-Ls")
    PUSH_SUBS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "push_subscriptions.json")

    @app.route("/manifest.json")
    def manifest():
        return json.dumps({
            "name": "Questboard",
            "short_name": "Questboard",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#1a1510",
            "theme_color": "#CDA473",
            "icons": [
                {"src": "/static/questboard-android-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/questboard-desktop-256.png", "sizes": "256x256", "type": "image/png"},
            ]
        }), 200, {"Content-Type": "application/json"}

    @app.route("/sw.js")
    def service_worker():
        from flask import send_from_directory
        return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")

    @app.route("/api/vapid-key")
    def vapid_key():
        return json.dumps({"key": VAPID_APP_KEY}), 200, {"Content-Type": "application/json"}

    @app.route("/api/push-subscribe", methods=["POST"])
    def push_subscribe():
        sub = request.get_json()
        subs = []
        if os.path.exists(PUSH_SUBS_FILE):
            with open(PUSH_SUBS_FILE, "r") as f:
                subs = json.load(f)
        # Avoid duplicates
        endpoints = [s.get("endpoint") for s in subs]
        if sub.get("endpoint") not in endpoints:
            subs.append(sub)
            with open(PUSH_SUBS_FILE, "w") as f:
                json.dump(subs, f)
        return json.dumps({"ok": True, "count": len(subs)}), 200

    @app.context_processor
    def inject_db_info():
        return {
            "available_dbs": list_dbs(),
            "active_db": os.path.basename(app.config["ACTIVE_DB"]),
        }

    @app.route("/switch-db", methods=["POST"])
    def switch_db():
        chosen = request.form.get("db", DB_DEFAULT)
        if chosen in list_dbs():
            app.config["ACTIVE_DB"] = os.path.join(DB_DIR, chosen)
        return redirect(request.referrer or "/")

    def build_ticket_query(current_project, current_assignee, current_label, show_closed=False):
        query = """
            SELECT t.*, s.name as status_name, s.is_closed, s.display_order,
                   u.name as assignee_name, p.name as project_name
            FROM tickets t
            JOIN statuses s ON s.id = t.status_id
            LEFT JOIN users u ON u.id = t.assigned_to
            JOIN projects p ON p.id = t.project_id
            WHERE p.archived = 0
        """
        params = []
        if current_project:
            query += " AND t.project_id = ?"
            params.append(current_project)
        if current_assignee:
            query += " AND t.assigned_to = ?"
            params.append(current_assignee)
        if current_label:
            query += " AND t.id IN (SELECT tl.ticket_id FROM ticket_labels tl JOIN labels l ON l.id = tl.label_id WHERE l.name = ?)"
            params.append(current_label)
        if not show_closed:
            query += " AND s.is_closed = 0"
        query += " ORDER BY t.priority DESC, t.id"
        return query, params

    @app.route("/")
    def kanban():
        db, projects, users, labels, cp, ca, cl = get_filter_context(request)
        statuses = db.execute("SELECT * FROM statuses WHERE is_closed=0 ORDER BY display_order").fetchall()
        query, params = build_ticket_query(cp, ca, cl, show_closed=False)
        tickets = db.execute(query, params).fetchall()

        # Attach labels to tickets
        enriched = []
        for t in tickets:
            t_labels = db.execute("""
                SELECT l.name, l.color FROM labels l
                JOIN ticket_labels tl ON tl.label_id = l.id WHERE tl.ticket_id = ?
            """, (t["id"],)).fetchall()
            enriched.append({**dict(t), "labels": [dict(l) for l in t_labels]})

        columns = {s["id"]: [] for s in statuses}
        for t in enriched:
            if t["status_id"] in columns:
                columns[t["status_id"]].append(t)

        db.close()
        return render_template_string(
            "{% extends 'kanban.html' %}",
            layout="layout",
            view="kanban",
            subtitle="Kanban",
            statuses=statuses,
            columns=columns,
            projects=projects,
            users=users,
            labels=labels,
            current_project=cp,
            current_assignee=ca,
            current_label=cl,
        )

    @app.route("/list")
    def list_view():
        db, projects, users, labels, cp, ca, cl = get_filter_context(request)
        show_closed = request.args.get("show_closed") == "on"
        query, params = build_ticket_query(cp, ca, cl, show_closed)
        tickets = db.execute(query, params).fetchall()

        enriched = []
        for t in tickets:
            t_labels = db.execute("""
                SELECT l.name, l.color FROM labels l
                JOIN ticket_labels tl ON tl.label_id = l.id WHERE tl.ticket_id = ?
            """, (t["id"],)).fetchall()
            enriched.append({**dict(t), "labels": [dict(l) for l in t_labels]})

        db.close()
        return render_template_string(
            "{% extends 'list.html' %}",
            layout="layout",
            view="list",
            subtitle="List",
            tickets=enriched,
            projects=projects,
            users=users,
            labels=labels,
            current_project=cp,
            current_assignee=ca,
            current_label=cl,
            show_closed=show_closed,
        )

    @app.route("/ticket/<int:ticket_id>")
    def ticket_detail(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            return "Ticket not found", 404

        project = db.execute("SELECT * FROM projects WHERE id=?", (ticket["project_id"],)).fetchone()
        statuses = db.execute("SELECT * FROM statuses ORDER BY display_order").fetchall()
        users = db.execute("SELECT * FROM users ORDER BY name").fetchall()
        labels = get_ticket_labels(db, ticket_id)
        creator = db.execute("SELECT name FROM users WHERE id=?", (ticket["created_by"],)).fetchone() if ticket["created_by"] else None

        comments = db.execute("""
            SELECT c.*, u.name as user_name FROM comments c
            LEFT JOIN users u ON u.id = c.user_id
            WHERE c.ticket_id = ? ORDER BY c.created_at
        """, (ticket_id,)).fetchall()

        activity = db.execute("""
            SELECT a.*, u.name as user_name FROM activity_log a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.ticket_id = ? ORDER BY a.created_at
        """, (ticket_id,)).fetchall()

        db.close()
        return render_template_string(
            "{% extends 'ticket.html' %}",
            layout="layout",
            view="ticket",
            subtitle=f"#{ticket_id}",
            ticket=ticket,
            project_name=project["name"],
            statuses=statuses,
            users=users,
            labels=labels,
            creator_name=creator["name"] if creator else None,
            comments=comments,
            activity=activity,
        )

    @app.route("/ticket/<int:ticket_id>/status", methods=["POST"])
    def update_ticket_status(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        new_status_id = int(request.form["status_id"])
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        old_status = db.execute("SELECT name FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
        new_status = db.execute("SELECT name FROM statuses WHERE id=?", (new_status_id,)).fetchone()
        db.execute("UPDATE tickets SET status_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (new_status_id, ticket_id))
        log_activity(db, ticket_id, None, "status", f"{old_status['name']} -> {new_status['name']}")
        db.commit()
        post_to_messageboard(f"Ticket #{ticket_id} ({ticket['title']}): {old_status['name']} -> {new_status['name']}")
        db.close()
        return redirect(f"/ticket/{ticket_id}")

    @app.route("/api/ticket/<int:ticket_id>/status", methods=["POST"])
    def api_update_ticket_status(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        new_status_id = int(data["status_id"])
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        old_status = db.execute("SELECT name FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
        new_status = db.execute("SELECT name FROM statuses WHERE id=?", (new_status_id,)).fetchone()
        if old_status["name"] == new_status["name"]:
            db.close()
            return json.dumps({"ok": True, "changed": False})
        db.execute("UPDATE tickets SET status_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (new_status_id, ticket_id))
        log_activity(db, ticket_id, None, "status", f"{old_status['name']} -> {new_status['name']}")
        db.commit()
        post_to_messageboard(f"Ticket #{ticket_id} ({ticket['title']}): {old_status['name']} -> {new_status['name']}")
        db.close()
        return json.dumps({"ok": True, "changed": True})

    @app.route("/ticket/<int:ticket_id>/assign", methods=["POST"])
    def update_ticket_assign(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        # Support both form and JSON
        if request.is_json:
            data = request.get_json()
            user_id = data.get("user_id")
        else:
            user_id = request.form.get("user_id")
        user_id = int(user_id) if user_id else None
        db.execute("UPDATE tickets SET assigned_to=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (user_id, ticket_id))
        assignee_name = None
        if user_id:
            user = db.execute("SELECT name FROM users WHERE id=?", (user_id,)).fetchone()
            assignee_name = user["name"]
            log_activity(db, ticket_id, user_id, "assigned", f"-> @{user['name']}")
        else:
            log_activity(db, ticket_id, None, "unassigned", "")
        db.commit()
        db.close()
        if request.is_json:
            return json.dumps({"ok": True, "assignee": assignee_name})
        return redirect(f"/ticket/{ticket_id}")

    @app.route("/ticket/<int:ticket_id>/comment", methods=["POST"])
    def add_ticket_comment(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        body = request.form.get("body", "").strip()
        user_id = request.form.get("user_id")
        user_id = int(user_id) if user_id else None
        if body:
            db.execute("INSERT INTO comments (ticket_id, user_id, body) VALUES (?, ?, ?)",
                       (ticket_id, user_id, body))
            log_activity(db, ticket_id, user_id, "comment", body[:100])
            db.commit()
        db.close()
        return redirect(f"/ticket/{ticket_id}")

    @app.route("/api/ticket/<int:ticket_id>/priority", methods=["POST"])
    def api_update_priority(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        priority = int(data["priority"])
        priority = max(0, min(5, priority))
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        db.execute("UPDATE tickets SET priority=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (priority, ticket_id))
        log_activity(db, ticket_id, None, "edited", f"priority -> {priority}")
        db.commit()
        db.close()
        return json.dumps({"ok": True, "priority": priority})

    @app.route("/api/ticket/<int:ticket_id>/label", methods=["POST"])
    def api_add_label(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        label_name = data["label"].strip()
        if not label_name:
            db.close()
            return json.dumps({"error": "empty label"}), 400
        label = db.execute("SELECT * FROM labels WHERE name=?", (label_name,)).fetchone()
        if not label:
            cur = db.execute("INSERT INTO labels (name) VALUES (?)", (label_name,))
            label_id = cur.lastrowid
        else:
            label_id = label["id"]
        try:
            db.execute("INSERT INTO ticket_labels (ticket_id, label_id) VALUES (?, ?)", (ticket_id, label_id))
            log_activity(db, ticket_id, None, "label", f"+{label_name}")
            db.commit()
        except sqlite3.IntegrityError:
            db.close()
            return json.dumps({"ok": True, "existing": True})
        db.close()
        return json.dumps({"ok": True})

    @app.route("/api/ticket/<int:ticket_id>/unlabel", methods=["POST"])
    def api_remove_label(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        label_name = data["label"].strip()
        label = db.execute("SELECT * FROM labels WHERE name=?", (label_name,)).fetchone()
        if not label:
            db.close()
            return json.dumps({"error": "label not found"}), 404
        db.execute("DELETE FROM ticket_labels WHERE ticket_id=? AND label_id=?", (ticket_id, label["id"]))
        log_activity(db, ticket_id, None, "label", f"-{label_name}")
        db.commit()
        db.close()
        return json.dumps({"ok": True})

    # ------------------------------------------------------------------
    # JSON API — full CRUD for remote CLI mode
    # ------------------------------------------------------------------

    def ticket_to_dict(db, row):
        """Convert a ticket row to a JSON-safe dict."""
        labels = get_ticket_labels(db, row["id"])
        proj = db.execute("SELECT name FROM projects WHERE id=?", (row["project_id"],)).fetchone()
        status = db.execute("SELECT name FROM statuses WHERE id=?", (row["status_id"],)).fetchone()
        assignee = db.execute("SELECT name FROM users WHERE id=?", (row["assigned_to"],)).fetchone() if row["assigned_to"] else None
        creator = db.execute("SELECT name FROM users WHERE id=?", (row["created_by"],)).fetchone() if row["created_by"] else None
        return {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "priority": row["priority"],
            "project": proj["name"] if proj else None,
            "project_id": row["project_id"],
            "status": status["name"] if status else None,
            "status_id": row["status_id"],
            "assignee": assignee["name"] if assignee else None,
            "assigned_to": row["assigned_to"],
            "creator": creator["name"] if creator else None,
            "labels": labels,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @app.route("/api/tickets", methods=["GET"])
    def api_list_tickets():
        db = get_db(app.config["ACTIVE_DB"])
        query = """
            SELECT t.*, s.name as status_name, s.is_closed
            FROM tickets t
            JOIN statuses s ON s.id = t.status_id
            WHERE 1=1
        """
        params = []
        if request.args.get("project"):
            proj = resolve_project(db, request.args["project"])
            if proj:
                query += " AND t.project_id = ?"
                params.append(proj["id"])
        if request.args.get("status"):
            st = resolve_status(db, request.args["status"])
            if st:
                query += " AND t.status_id = ?"
                params.append(st["id"])
        if request.args.get("assignee"):
            user = resolve_user(db, request.args["assignee"])
            if user:
                query += " AND t.assigned_to = ?"
                params.append(user["id"])
        if request.args.get("label"):
            query += " AND t.id IN (SELECT tl.ticket_id FROM ticket_labels tl JOIN labels l ON l.id = tl.label_id WHERE l.name = ?)"
            params.append(request.args["label"])
        if not request.args.get("all"):
            query += " AND s.is_closed = 0"
        query += " ORDER BY t.priority DESC, t.id"
        rows = db.execute(query, params).fetchall()
        result = [ticket_to_dict(db, r) for r in rows]
        db.close()
        return json.dumps(result), 200, {"Content-Type": "application/json"}

    @app.route("/api/tickets", methods=["POST"])
    def api_add_ticket():
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        if not data or not data.get("title"):
            db.close()
            return json.dumps({"error": "title required"}), 400
        if not data.get("creator"):
            db.close()
            return json.dumps({"error": "creator required — every ticket needs a name"}), 400
        proj = resolve_project(db, data.get("project", "pings"))
        if not proj:
            db.close()
            return json.dumps({"error": f"project not found: {data.get('project')}"}), 404
        creator = resolve_user(db, data.get("creator")) if data.get("creator") else None
        if proj["name"].lower() in PROTECTED_PROJECTS and creator and creator["role"] == "agent":
            pings = db.execute("SELECT * FROM projects WHERE name='pings'").fetchone()
            if pings:
                proj = pings
        status = db.execute("SELECT * FROM statuses ORDER BY display_order LIMIT 1").fetchone()
        assignee = resolve_user(db, data.get("assignee")) if data.get("assignee") else None
        cur = db.execute(
            "INSERT INTO tickets (project_id, status_id, assigned_to, title, description, priority, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (proj["id"], status["id"], assignee["id"] if assignee else None, data["title"],
             data.get("description", ""), data.get("priority", 0), creator["id"] if creator else None),
        )
        ticket_id = cur.lastrowid
        log_activity(db, ticket_id, creator["id"] if creator else None, "created", data["title"])
        for lname in data.get("labels", []):
            label = db.execute("SELECT * FROM labels WHERE name=?", (lname,)).fetchone()
            if not label:
                lcur = db.execute("INSERT INTO labels (name) VALUES (?)", (lname,))
                label_id = lcur.lastrowid
            else:
                label_id = label["id"]
            try:
                db.execute("INSERT INTO ticket_labels (ticket_id, label_id) VALUES (?, ?)", (ticket_id, label_id))
            except sqlite3.IntegrityError:
                pass
        db.commit()
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        result = ticket_to_dict(db, ticket)
        db.close()
        return json.dumps(result), 201, {"Content-Type": "application/json"}

    @app.route("/api/tickets/<int:ticket_id>", methods=["GET"])
    def api_show_ticket(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        result = ticket_to_dict(db, ticket)
        comments = db.execute("""
            SELECT c.*, u.name as user_name FROM comments c
            LEFT JOIN users u ON u.id = c.user_id
            WHERE c.ticket_id = ? ORDER BY c.created_at
        """, (ticket_id,)).fetchall()
        result["comments"] = [{"user": c["user_name"] or "system", "body": c["body"], "created_at": c["created_at"]} for c in comments]
        db.close()
        return json.dumps(result), 200, {"Content-Type": "application/json"}

    @app.route("/api/tickets/<int:ticket_id>/status", methods=["PUT"])
    def api_set_status(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        new_status = resolve_status(db, data.get("status") or data.get("status_id"))
        if not new_status:
            db.close()
            return json.dumps({"error": "status not found"}), 404
        old_status = db.execute("SELECT name FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
        db.execute("UPDATE tickets SET status_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (new_status["id"], ticket_id))
        log_activity(db, ticket_id, None, "status", f"{old_status['name']} -> {new_status['name']}")
        db.commit()
        post_to_messageboard(f"Ticket #{ticket_id} ({ticket['title']}): {old_status['name']} -> {new_status['name']}")
        db.close()
        return json.dumps({"ok": True, "status": new_status["name"]})

    @app.route("/api/tickets/<int:ticket_id>/block", methods=["POST"])
    def api_block_ticket(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json() or {}
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        blocked_status = resolve_status(db, "blocked")
        if not blocked_status:
            db.close()
            return json.dumps({"error": "no blocked status"}), 500
        old_status = db.execute("SELECT name FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
        db.execute("UPDATE tickets SET status_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (blocked_status["id"], ticket_id))
        log_activity(db, ticket_id, None, "status", f"{old_status['name']} -> blocked")
        reason = data.get("reason", "")
        if reason:
            db.execute("INSERT INTO comments (ticket_id, body) VALUES (?, ?)", (ticket_id, reason))
            log_activity(db, ticket_id, None, "comment", reason)
        db.commit()
        post_to_messageboard(f"Ticket #{ticket_id} ({ticket['title']}): blocked" + (f" — {reason}" if reason else ""))
        db.close()
        return json.dumps({"ok": True, "status": "blocked"})

    @app.route("/api/tickets/<int:ticket_id>/done", methods=["POST"])
    def api_done_ticket(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        done_status = db.execute("SELECT * FROM statuses WHERE is_closed=1 ORDER BY display_order LIMIT 1").fetchone()
        if not done_status:
            db.close()
            return json.dumps({"error": "no closed status"}), 500
        old_status = db.execute("SELECT name FROM statuses WHERE id=?", (ticket["status_id"],)).fetchone()
        db.execute("UPDATE tickets SET status_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (done_status["id"], ticket_id))
        log_activity(db, ticket_id, None, "status", f"{old_status['name']} -> {done_status['name']}")
        db.commit()
        post_to_messageboard(f"Ticket #{ticket_id} ({ticket['title']}): {old_status['name']} -> {done_status['name']}")
        db.close()
        return json.dumps({"ok": True, "status": done_status["name"]})

    @app.route("/api/tickets/<int:ticket_id>/assign", methods=["PUT"])
    def api_assign_ticket(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        user = resolve_user(db, data.get("assignee"))
        if not user:
            db.close()
            return json.dumps({"error": f"user not found: {data.get('assignee')}"}), 404
        db.execute("UPDATE tickets SET assigned_to=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (user["id"], ticket_id))
        log_activity(db, ticket_id, user["id"], "assigned", f"-> @{user['name']}")
        db.commit()
        db.close()
        return json.dumps({"ok": True, "assignee": user["name"]})

    @app.route("/api/tickets/<int:ticket_id>/move", methods=["PUT"])
    def api_move_ticket(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        proj = resolve_project(db, data.get("project"))
        if not proj:
            db.close()
            return json.dumps({"error": f"project not found: {data.get('project')}"}), 404
        db.execute("UPDATE tickets SET project_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (proj["id"], ticket_id))
        log_activity(db, ticket_id, None, "moved", f"-> {proj['name']} (#{proj['id']})")
        db.commit()
        db.close()
        return json.dumps({"ok": True, "project": proj["name"]})

    @app.route("/api/tickets/<int:ticket_id>/comment", methods=["POST"])
    def api_add_comment(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json()
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        body = data.get("body", "").strip()
        if not body:
            db.close()
            return json.dumps({"error": "body required"}), 400
        user = resolve_user(db, data.get("user")) if data.get("user") else None
        db.execute("INSERT INTO comments (ticket_id, user_id, body) VALUES (?, ?, ?)",
                   (ticket_id, user["id"] if user else None, body))
        log_activity(db, ticket_id, user["id"] if user else None, "comment", body[:100])
        db.commit()
        db.close()
        return json.dumps({"ok": True})

    @app.route("/api/tickets/<int:ticket_id>/promote", methods=["POST"])
    def api_promote_ticket(ticket_id):
        db = get_db(app.config["ACTIVE_DB"])
        data = request.get_json() or {}
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not ticket:
            db.close()
            return json.dumps({"error": "not found"}), 404
        target = resolve_project(db, data.get("project", "artificer"))
        if not target:
            db.close()
            return json.dumps({"error": "target project not found"}), 404
        old_proj = db.execute("SELECT name FROM projects WHERE id=?", (ticket["project_id"],)).fetchone()
        db.execute("UPDATE tickets SET project_id=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (target["id"], ticket_id))
        log_activity(db, ticket_id, None, "promoted", f"{old_proj['name']} -> {target['name']}")
        db.commit()
        db.close()
        return json.dumps({"ok": True, "project": target["name"]})

    @app.route("/api/projects", methods=["GET"])
    def api_list_projects():
        db = get_db(app.config["ACTIVE_DB"])
        rows = db.execute("SELECT * FROM projects WHERE archived=0 ORDER BY name").fetchall()
        result = []
        for r in rows:
            count = db.execute("SELECT COUNT(*) as c FROM tickets t JOIN statuses s ON s.id=t.status_id WHERE t.project_id=? AND s.is_closed=0", (r["id"],)).fetchone()
            result.append({"id": r["id"], "name": r["name"], "description": r["description"], "open_tickets": count["c"]})
        db.close()
        return json.dumps(result), 200, {"Content-Type": "application/json"}

    @app.route("/api/users", methods=["GET"])
    def api_list_users():
        db = get_db(app.config["ACTIVE_DB"])
        rows = db.execute("SELECT * FROM users ORDER BY name").fetchall()
        result = [{"id": r["id"], "name": r["name"], "role": r["role"]} for r in rows]
        db.close()
        return json.dumps(result), 200, {"Content-Type": "application/json"}

    @app.route("/api/statuses", methods=["GET"])
    def api_list_statuses():
        db = get_db(app.config["ACTIVE_DB"])
        rows = db.execute("SELECT * FROM statuses ORDER BY display_order").fetchall()
        result = [{"id": r["id"], "name": r["name"], "display_order": r["display_order"], "is_closed": bool(r["is_closed"])} for r in rows]
        db.close()
        return json.dumps(result), 200, {"Content-Type": "application/json"}

    @app.route("/api/help")
    def api_help():
        help_text = {
            "name": "Questboard",
            "description": "Agent-native project management. CLI + web UI + JSON API.",
            "remote_cli": "Set QB_REMOTE=https://questboard-ec2.tail7f6073.ts.net then use 'python questboard.py <command>' normally.",
            "policy": "Agents cannot write to the 'artificer' project. Route tickets to 'pings'. Human promotes via 'qb promote <id>'.",
            "notifications": "Only 'blocked' status on /pings triggers phone/desktop notifications. Use 'qb block <id> \"reason\"' when you need human attention.",
            "commands": {
                "add": "qb add \"title\" -p <project> [-a user] [-l label] [--priority N] [-c creator]",
                "list": "qb list [-p project] [-s status] [-a user] [--all]",
                "show": "qb show <id>",
                "status": "qb status <id> <status-name>",
                "block": "qb block <id> [\"reason\"] — sets blocked + optional comment, triggers notification",
                "done": "qb done <id> [<id>...]",
                "assign": "qb assign <id> [<id>...] -u <user>",
                "comment": "qb comment <id> \"text\" [-u user]",
                "move": "qb move <id> [<id>...] -p <project>",
                "label": "qb label <id> [<id>...] -l <label>",
                "promote": "qb promote <id> [<id>...] [-p project] — move from /pings to target (default: artificer)",
                "project-list": "qb project-list",
            },
            "api_base": "https://questboard-ec2.tail7f6073.ts.net",
            "api_endpoints": {
                "GET /api/tickets": "List tickets (?project=&status=&assignee=&label=&all=1)",
                "POST /api/tickets": "Create ticket ({title, project, priority, assignee, creator, labels})",
                "GET /api/tickets/<id>": "Show ticket + comments",
                "PUT /api/tickets/<id>/status": "Change status ({status})",
                "POST /api/tickets/<id>/block": "Block ({reason})",
                "POST /api/tickets/<id>/done": "Close",
                "PUT /api/tickets/<id>/assign": "Assign ({assignee})",
                "POST /api/tickets/<id>/comment": "Comment ({body, user})",
                "PUT /api/tickets/<id>/move": "Move ({project})",
                "POST /api/tickets/<id>/promote": "Promote ({project})",
                "GET /api/projects": "List projects",
                "GET /api/users": "List users",
                "GET /api/statuses": "List statuses",
            },
        }
        return json.dumps(help_text, indent=2), 200, {"Content-Type": "application/json"}

    print(f"Questboard serving at http://localhost:{port}")
    host = os.environ.get("QB_HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)


# ---------------------------------------------------------------------------
# Import from Vikunja
# ---------------------------------------------------------------------------

def cmd_import_vikunja(args):
    """Import projects, tasks, and labels from Vikunja API."""
    import urllib.request
    import urllib.error

    abadar_dir = os.path.expanduser("~/library/0-system/credentials")
    abadar_py = os.path.join(abadar_dir, "abadar.py")
    abadar_key = os.environ.get("ABADAR_KEY", "rabada")

    import subprocess
    def abadar_read(name):
        env = os.environ.copy()
        env["ABADAR_KEY"] = abadar_key
        result = subprocess.run(
            [sys.executable, abadar_py, "read", name],
            capture_output=True, text=True, env=env, cwd=abadar_dir,
        )
        return result.stdout.strip()

    base_url = abadar_read("vikunja_url").rstrip("/")
    token = abadar_read("vikunja_api_token")

    def vk_get(path):
        url = f"{base_url}/api/v1{path}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    db = get_db()
    init_db()

    # Ensure we have an artificer user
    if not db.execute("SELECT * FROM users WHERE name='artificer'").fetchone():
        db.execute("INSERT INTO users (name, role) VALUES ('artificer', 'human')")

    # Get the default (queued) status
    queued = db.execute("SELECT * FROM statuses ORDER BY display_order LIMIT 1").fetchone()

    # Import labels
    print("Importing labels...")
    vk_labels = vk_get("/labels")
    label_map = {}
    for vl in vk_labels:
        existing = db.execute("SELECT * FROM labels WHERE name=?", (vl["title"],)).fetchone()
        if existing:
            label_map[vl["id"]] = existing["id"]
        else:
            cur = db.execute("INSERT INTO labels (name, color) VALUES (?, ?)",
                           (vl["title"], vl.get("hex_color", "")))
            label_map[vl["id"]] = cur.lastrowid
        print(f"  Label: {vl['title']}")

    # Import projects
    print("Importing projects...")
    vk_projects = vk_get("/projects")
    proj_map = {}
    for vp in vk_projects:
        if vp["title"] == "Inbox":
            continue
        existing = db.execute("SELECT * FROM projects WHERE name=?", (vp["title"],)).fetchone()
        if existing:
            proj_map[vp["id"]] = existing["id"]
        else:
            cur = db.execute("INSERT INTO projects (name, description) VALUES (?, ?)",
                           (vp["title"], vp.get("description", "")))
            proj_map[vp["id"]] = cur.lastrowid
        print(f"  Project: {vp['title']}")

    # Import tasks per project
    print("Importing tickets...")
    artificer = db.execute("SELECT id FROM users WHERE name='artificer'").fetchone()
    for vp_id, qb_proj_id in proj_map.items():
        tasks = vk_get(f"/projects/{vp_id}/tasks?per_page=100")
        for vt in tasks:
            existing = db.execute("SELECT * FROM tickets WHERE title=? AND project_id=?",
                                (vt["title"], qb_proj_id)).fetchone()
            if existing:
                print(f"  Skip (exists): #{existing['id']} {vt['title']}")
                continue

            cur = db.execute(
                "INSERT INTO tickets (project_id, status_id, title, description, priority, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                (qb_proj_id, queued["id"], vt["title"], vt.get("description", ""), vt.get("priority", 0),
                 artificer["id"]),
            )
            tid = cur.lastrowid
            log_activity(db, tid, artificer["id"], "created", f"imported from Vikunja")

            # Attach labels
            for vl in (vt.get("labels") or []):
                if vl["id"] in label_map:
                    try:
                        db.execute("INSERT INTO ticket_labels (ticket_id, label_id) VALUES (?, ?)",
                                 (tid, label_map[vl["id"]]))
                    except sqlite3.IntegrityError:
                        pass

            print(f"  #{tid} {vt['title']}")

    db.commit()
    db.close()
    print("Import complete.")


# ---------------------------------------------------------------------------
# Argument Parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog="qb", description="Questboard — agent-native project management")
    parser.add_argument("--db", help="Database filename in db/ directory (e.g. questboard.db)")
    sub = parser.add_subparsers(dest="command")

    # user
    u_add = sub.add_parser("user-add")
    u_add.add_argument("name")
    u_add.add_argument("--role", default="agent", choices=["human", "agent"])

    sub.add_parser("user-list")

    # project
    p_add = sub.add_parser("project-add")
    p_add.add_argument("name")
    p_add.add_argument("--description", "-d")

    p_list = sub.add_parser("project-list")
    p_list.add_argument("--archived", action="store_true")

    p_arc = sub.add_parser("project-archive")
    p_arc.add_argument("project")

    # tickets
    add = sub.add_parser("add")
    add.add_argument("title")
    add.add_argument("--project", "-p", required=True)
    add.add_argument("--assign", "-a")
    add.add_argument("--priority", type=int, default=0)
    add.add_argument("--label", "-l", action="append")
    add.add_argument("--description", "-d")
    add.add_argument("--creator", "-c", required=True, help="Who is creating this ticket (required)")

    ls = sub.add_parser("list")
    ls.add_argument("--project", "-p")
    ls.add_argument("--status", "-s")
    ls.add_argument("--assign", "-a")
    ls.add_argument("--label", "-l")
    ls.add_argument("--all", action="store_true", help="Include closed tickets")

    show = sub.add_parser("show")
    show.add_argument("ticket_id", type=int)

    edit = sub.add_parser("edit")
    edit.add_argument("ticket_id", type=int)
    edit.add_argument("--title", "-t")
    edit.add_argument("--description", "-d")
    edit.add_argument("--priority", type=int)

    st = sub.add_parser("status")
    st.add_argument("ticket_id", type=int)
    st.add_argument("status_name")

    assign = sub.add_parser("assign")
    assign.add_argument("ticket_ids", type=int, nargs="+")
    assign.add_argument("--user", "-u", required=True)

    mv = sub.add_parser("move")
    mv.add_argument("ticket_ids", type=int, nargs="+")
    mv.add_argument("--project", "-p", required=True)

    dn = sub.add_parser("done")
    dn.add_argument("ticket_ids", type=int, nargs="+")

    blk = sub.add_parser("block")
    blk.add_argument("ticket_id", type=int)
    blk.add_argument("reason", nargs="?")

    cmt = sub.add_parser("comment")
    cmt.add_argument("ticket_id", type=int)
    cmt.add_argument("text")
    cmt.add_argument("--user", "-u")

    lbl = sub.add_parser("label")
    lbl.add_argument("ticket_ids", type=int, nargs="+")
    lbl.add_argument("--label", "-l", dest="label_name", required=True)

    ulbl = sub.add_parser("unlabel")
    ulbl.add_argument("ticket_ids", type=int, nargs="+")
    ulbl.add_argument("--label", "-l", dest="label_name", required=True)

    # promote
    prm = sub.add_parser("promote")
    prm.add_argument("ticket_ids", type=int, nargs="+")
    prm.add_argument("--project", "-p", default=None, help="Target project (default: artificer)")

    # label management
    la = sub.add_parser("label-add")
    la.add_argument("name")
    la.add_argument("--color")

    sub.add_parser("label-list")

    # status management
    sub.add_parser("status-list")

    sa = sub.add_parser("status-add")
    sa.add_argument("name")
    sa.add_argument("--order", type=int, required=True)
    sa.add_argument("--closed", action="store_true")

    sr = sub.add_parser("status-rename")
    sr.add_argument("old_name")
    sr.add_argument("new_name")

    so = sub.add_parser("status-reorder")
    so.add_argument("name")
    so.add_argument("order", type=int)

    # serve
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=5151)

    # import
    sub.add_parser("import-vikunja")

    return parser


# ---------------------------------------------------------------------------
# Remote Mode — CLI over API when QB_REMOTE is set
# ---------------------------------------------------------------------------

QB_REMOTE = os.environ.get("QB_REMOTE", "")  # e.g. https://questboard-ec2.tail7f6073.ts.net


def _api(method, path, data=None, params=None):
    """Make an HTTP request to the remote Questboard API."""
    import urllib.request
    import urllib.error
    import urllib.parse

    url = QB_REMOTE.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
            print(f"Error: {err.get('error', e.code)}")
        except (json.JSONDecodeError, ValueError):
            print(f"Error {e.code}: {body[:200]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection failed: {e.reason}")
        sys.exit(1)


def remote_list(args):
    params = {}
    if args.project: params["project"] = args.project
    if args.status: params["status"] = args.status
    if args.assign: params["assignee"] = args.assign
    if args.label: params["label"] = args.label
    if args.all: params["all"] = "1"
    tickets = _api("GET", "/api/tickets", params=params)
    for t in tickets:
        assignee = f"@{t['assignee']}" if t["assignee"] else ""
        labels = " ".join(t.get("labels", []))
        pri = priority_dots(t["priority"])
        done_mark = "x" if t["status"] in ("done", "n/a") else " "
        print(f"  [{done_mark}] #{t['id']:4d} {t['title']:40s} {assignee:12s} {t['status']:14s} {labels} {pri}")
    if not tickets:
        print("  (no tickets)")


def remote_show(args):
    t = _api("GET", f"/api/tickets/{args.ticket_id}")
    print(f"#{t['id']} {t['title']}")
    print(f"  Project:  {t['project']} (#{t['project_id']})")
    print(f"  Status:   {t['status']}")
    if t["assignee"]:
        print(f"  Assigned: {t['assignee']}")
    print(f"  Priority: {t['priority']} {priority_dots(t['priority'])}")
    if t.get("labels"):
        print(f"  Labels:   {', '.join(t['labels'])}")
    if t.get("creator"):
        print(f"  Created:  {t['created_at']} by {t['creator']}")
    else:
        print(f"  Created:  {t['created_at']}")
    if t.get("description"):
        print(f"  ---")
        print(f"  {t['description']}")
    for c in t.get("comments", []):
        print(f"  [{c['created_at']}] {c['user']}: {c['body']}")


def remote_add(args):
    data = {"title": args.title, "project": args.project, "priority": args.priority or 0}
    if args.assign: data["assignee"] = args.assign
    if args.description: data["description"] = args.description
    if args.creator: data["creator"] = args.creator
    if args.label: data["labels"] = args.label
    t = _api("POST", "/api/tickets", data)
    assignee_str = f" @{t['assignee']}" if t.get("assignee") else ""
    pri_str = f" {priority_dots(t['priority'])}" if t["priority"] else ""
    print(f"#{t['id']} {t['title']} [{t['status']}]{assignee_str}{pri_str}")


def remote_status(args):
    result = _api("PUT", f"/api/tickets/{args.ticket_id}/status", {"status": args.status_name})
    print(f"#{args.ticket_id} -> {result['status']}")


def remote_assign(args):
    for tid in args.ticket_ids:
        result = _api("PUT", f"/api/tickets/{tid}/assign", {"assignee": args.user})
        print(f"#{tid} -> @{result['assignee']}")


def remote_move(args):
    for tid in args.ticket_ids:
        result = _api("PUT", f"/api/tickets/{tid}/move", {"project": args.project})
        print(f"#{tid} moved to {result['project']}")


def remote_done(args):
    for tid in args.ticket_ids:
        result = _api("POST", f"/api/tickets/{tid}/done")
        print(f"#{tid} -> {result['status']}")


def remote_block(args):
    data = {}
    if args.reason: data["reason"] = args.reason
    result = _api("POST", f"/api/tickets/{args.ticket_id}/block", data)
    print(f"#{args.ticket_id} -> blocked")
    if args.reason:
        print(f"  Comment: {args.reason}")


def remote_comment(args):
    data = {"body": args.text}
    if args.user: data["user"] = args.user
    _api("POST", f"/api/tickets/{args.ticket_id}/comment", data)
    print(f"Comment added to #{args.ticket_id}")


def remote_label(args):
    for tid in args.ticket_ids:
        _api("POST", f"/api/tickets/{tid}/label", {"label": args.label_name})
        print(f"Label {args.label_name} added to #{tid}")


def remote_unlabel(args):
    for tid in args.ticket_ids:
        _api("POST", f"/api/tickets/{tid}/unlabel", {"label": args.label_name})
        print(f"Label {args.label_name} removed from #{tid}")


def remote_promote(args):
    for tid in args.ticket_ids:
        data = {"project": args.project} if args.project else {}
        result = _api("POST", f"/api/tickets/{tid}/promote", data)
        print(f"#{tid} promoted to {result['project']}")


def remote_project_list(args):
    projects = _api("GET", "/api/projects")
    for p in projects:
        print(f"  #{p['id']} {p['name']} ({p['open_tickets']} open)")


def remote_user_list(args):
    users = _api("GET", "/api/users")
    for u in users:
        print(f"  {u['name']:20s} {u['role']}")


def remote_status_list(args):
    statuses = _api("GET", "/api/statuses")
    for s in statuses:
        closed = " (closed)" if s["is_closed"] else ""
        print(f"  {s['display_order']}: {s['name']}{closed}")


REMOTE_COMMANDS = {
    "list": remote_list,
    "show": remote_show,
    "add": remote_add,
    "status": remote_status,
    "assign": remote_assign,
    "move": remote_move,
    "done": remote_done,
    "block": remote_block,
    "comment": remote_comment,
    "label": remote_label,
    "unlabel": remote_unlabel,
    "promote": remote_promote,
    "project-list": remote_project_list,
    "user-list": remote_user_list,
    "status-list": remote_status_list,
}


def main():
    global DB_PATH
    parser = build_parser()
    args = parser.parse_args()

    # Remote mode: route through API
    if QB_REMOTE and args.command in REMOTE_COMMANDS:
        REMOTE_COMMANDS[args.command](args)
        return

    if QB_REMOTE and args.command == "serve":
        pass  # serve always runs locally
    elif QB_REMOTE and args.command not in REMOTE_COMMANDS:
        print(f"Command '{args.command}' not available in remote mode")
        return

    if args.db:
        DB_PATH = os.path.join(DB_DIR, args.db)

    init_db()

    commands = {
        "user-add": cmd_user_add,
        "user-list": cmd_user_list,
        "project-add": cmd_project_add,
        "project-list": cmd_project_list,
        "project-archive": cmd_project_archive,
        "add": cmd_add,
        "edit": cmd_edit,
        "list": cmd_list,
        "show": cmd_show,
        "status": cmd_status,
        "assign": cmd_assign,
        "move": cmd_move,
        "done": cmd_done,
        "block": cmd_block,
        "comment": cmd_comment,
        "label": cmd_label,
        "unlabel": cmd_unlabel,
        "promote": cmd_promote,
        "label-add": cmd_label_add,
        "label-list": cmd_label_list,
        "status-list": cmd_status_list,
        "status-add": cmd_status_add,
        "status-rename": cmd_status_rename,
        "status-reorder": cmd_status_reorder,
        "serve": cmd_serve,
        "import-vikunja": cmd_import_vikunja,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
