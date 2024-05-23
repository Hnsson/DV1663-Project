import sqlite3
from flask import g

DATABASE = 'db/database.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")  # Enable foreign key support
    return db

def close_db(exception=None):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ---------------- QUERYING FUNCTIONS --------------
def query_db(query, args=(), one=False, commit=False):
    db = get_db()
    cur = db.execute(query, args)
    if commit:
        db.commit()
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def get_unread_notifications(user_id):
    return query_db("SELECT * FROM notifications WHERE user_id = ? AND read = 0", [user_id])

# When teardown context we close the database.
def init_db(app):
    app.teardown_appcontext(close_db)
