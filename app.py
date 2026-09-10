#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from functools import wraps
from datetime import timedelta
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify)
from flask_session import Session
from dotenv import load_dotenv

load_dotenv()
from analyzer import analyze_chart, CONFIG as A_CONF

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_change_me_12345")
app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR="/tmp/po_sessions",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    JSON_AS_ASCII=False,
)
os.makedirs("/tmp/po_sessions", exist_ok=True)
Session(app)

USERS = {
    os.environ.get("APP_USER", "admin"): {
        "password": os.environ.get("APP_PASS", "changeme123"),
        "display": "Operator",
    },
}

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*a, **k)
    return w

@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        info = USERS.get(u)
        if info and info["password"] == p:
            session.permanent = True
            session["logged_in"] = True
            session["username"] = u
            session["display"] = info["display"]
            return redirect(url_for("dashboard"))
        error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        username=session.get("display"),
        po_url=A_CONF["po_url"],
        assets=A_CONF["assets"],
        periods=A_CONF["periods"],
    )

@app.route("/popup")
@login_required
def popup():
    return render_template(
        "popup.html",
        assets=A_CONF["assets"],
        periods=A_CONF["periods"],
    )

@app.route("/api/analyze", methods=["POST"])
@login_required
def api_analyze():
    data = request.get_json(silent=True) or {}
    asset = data.get("asset", "EURUSD_otc")
    period = int(data.get("period", 60))
    stype = data.get("session_type", "demo")

    try:
        r = analyze_chart(asset=asset, period=period, session_type=stype)
        return jsonify({"ok": True, **r})
    except Exception as e:
        import traceback
        return jsonify({
            "ok": False,
            "error": "%s: %s" % (type(e).__name__, e),
            "trace": traceback.format_exc(),
        }), 500

@app.route("/api/health")
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
