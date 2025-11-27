import os

from flask import Flask, redirect, request, session, abort, render_template
from config.settings import API_BASE, CLIENT_ID, REDIRECT_URI

from app.dashboard import dashboard

app = Flask(__name__, static_url_path="")
app.secret_key = os.urandom(24)
app.url_map.strict_slashes = False

blueprints = [dashboard]
for blueprint in blueprints:
    app.register_blueprint(blueprint)

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500

@app.route("/")
def home():
    return app.send_static_file("index.html")

@app.route("/terms")
def terms():
    return app.send_static_file("terms.html")

@app.route("/privacy")
def privacy():
    return app.send_static_file("privacy.html")

@app.route("/partners")
def partners():
    return app.send_static_file("partners.html")

@app.route("/login")
def login():
    redirect_to = request.args.get("redirect_to")
    if redirect_to:
        session["redirect_to"] = redirect_to
        
    scope = "identify guilds"
    return redirect(
        f"{API_BASE}/oauth2/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&scope={scope}"
        f"&prompt=none"
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1234)