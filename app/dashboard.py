import requests
import html
from time import time
from datetime import datetime
import re
from urllib.parse import quote

from firebase_admin import db
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, session, redirect, jsonify

from config.settings import API_BASE, BOT_TOKEN, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, PAYPAL_CLIENT_ID, PREMIUM_ONE_TIME_PRICE
from utils.firebase import save_user_to_firebase, save_experience_request, get_user_experiences, approve_experience, reject_experience, update_experience_end_date, get_all_experiences_for_server, get_user_data
from utils.request import requests_session
from utils.theme import wrap_page, error_page

PERMISSIONS = {
    1: "Create Instant Invite",
    2: "Kick Members",
    4: "Ban Members",
    8: "Administrator",
    16: "Manage Channels",
    32: "Manage Guild",
    64: "Add Reactions",
    128: "View Audit Log",
    256: "Priority Speaker",
    512: "Stream",
    1024: "View Channel",
    2048: "Send Messages",
    4096: "Send TTS Messages",
    8192: "Manage Messages",
    16384: "Embed Links",
    32768: "Attach Files",
    65536: "Read Message History",
    131072: "Mention Everyone",
    262144: "Use External Emojis",
    524288: "View Guild Insights",
    1048576: "Connect",
    2097152: "Speak",
    4194304: "Mute Members",
    8388608: "Deafen Members",
    16777216: "Move Members",
    33554432: "Use VAD",
    67108864: "Change Nickname",
    134217728: "Manage Nicknames",
    268435456: "Manage Roles",
    536870912: "Manage Webhooks",
    1073741824: "Manage Emojis and Stickers",
    2147483648: "Use Application Commands",
    4294967296: "Request to Speak",
    8589934592: "Manage Events",
    17179869184: "Manage Threads",
    34359738368: "Create Public Threads",
    68719476736: "Create Private Threads",
    137438953472: "Use External Stickers",
    274877906944: "Send Messages in Threads",
    549755813888: "Use Embedded Activities",
    1099511627776: "Moderate Members",
}

MOD_PERMS = ["Manage Channels", "Manage Guild", "Kick Members", "Ban Members", "Manage Messages", "Manage Nicknames", "Manage Roles", "Manage Webhooks"]

# Feature Limits
EXP_LIMIT_FREE = 5

DESC_LIMIT_FREE = 200
DESC_LIMIT_PREMIUM = 3000

SOCIAL_LIMIT_FREE = 3
SOCIAL_LIMIT_PREMIUM = 10

last_requests = {}

def get_permissions_list(perm_int):
    perms = []
    for bit, name in PERMISSIONS.items():
        if perm_int & bit:
            perms.append(name)
    return perms

def get_user_role_and_guild(user_id, server_id, discord_token):
    guilds = requests_session.get(f"{API_BASE}/users/@me/guilds", headers={"Authorization": f"Bearer {discord_token}"}).json()
    for g in guilds:
        if str(g['id']) == server_id:
            perms = get_permissions_list(int(g.get("permissions", 0)))
            if g.get("owner"):
                return "Server Owner", g
            elif "Administrator" in perms:
                return "Administrator", g
            elif any(perm in perms for perm in MOD_PERMS):
                return "Moderator", g
            else:
                return "Member", g
    return None, None

def get_user_role_in_server(user_id, server_id, discord_token):
    role, _ = get_user_role_and_guild(user_id, server_id, discord_token)
    return role

dashboard = Blueprint('dashboard', __name__)

@dashboard.route("/dashboard")
def view_dashboard():
    code = request.args.get("code")
    if code:
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "scope": "identify guilds",
        }

        r = requests_session.post(f"{API_BASE}/oauth2/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code != 200:
            return error_page(f"Token exchange failed: {r.text}", 400)

        tokens = r.json()
        session["discord_token"] = tokens["access_token"]

        user = requests_session.get(f"{API_BASE}/users/@me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()
        save_user_to_firebase(user, tokens["access_token"])
        session["user_id"] = str(user["id"])

        redirect_to = session.pop("redirect_to", None)
        if redirect_to:
            return redirect(redirect_to)
        return redirect("/dashboard")

    user_agent = request.headers.get('User-Agent', '').lower()
    bot_keywords = ['bot', 'crawler', 'spider', 'scraper', 'discordbot', 'twitterbot', 'facebookexternalhit']
    is_bot = any(keyword in user_agent for keyword in bot_keywords)
    
    if is_bot:
        return """<!DOCTYPE html>
            <html lang="en">
            <head>
                <title>ServerCV | Show Your Verified Discord Experience</title>
                <meta name="description" content="Build a verified portfolio of your server contributions. Perfect for staff applications and sharing your achievements in the Discord community.">
                <meta name="author" content="ServerCV">
                <meta name="keywords" content="Discord Resume, Discord Portfolio, Discord Staff, Server Contributions, Discord Experience, Verified History, Discord Community, Staff Application, ServerCV">
                <meta name="creator" content="ServerCV">
                <meta name="publisher" content="ServerCV">
                <meta name="robots" content="index, follow">
                <meta property="og:title" content="ServerCV | Show Your Verified Discord Experience">
                <meta property="og:description" content="Build a verified portfolio of your server contributions. Perfect for staff applications and sharing your achievements in the Discord community.">
                <meta property="og:type" content="website">
                <meta property="og:site_name" content="ServerCV">
                <meta property="og:image" content="https://servercv.com/assets/logo.png">
                <meta name="twitter:card" content="summary">
                <meta name="twitter:title" content="ServerCV | Show Your Verified Discord Experience">
                <meta name="twitter:description" content="Build a verified portfolio of your server contributions. Perfect for staff applications and sharing your achievements in the Discord community.">
                <meta name="twitter:image" content="https://servercv.com/assets/logo.png">
            </head>
            <body>
                <h1>ServerCV - Professional Discord Staff Portfolios</h1>
                <p>ServerCV is the standard for tracking and verifying Discord staff experience. Create your profile today to showcase your contributions to communities.</p>
                <a href="/login">Get Started</a>
            </body>
            </html>"""

    if "discord_token" not in session:
        return redirect(f"/login?redirect_to={quote(request.full_path)}")

    discord_token = session['discord_token']
    user = requests_session.get(f"{API_BASE}/users/@me", headers={"Authorization": f"Bearer {discord_token}"}).json()
    
    user_data = get_user_data(str(user["id"]))
    is_premium = user_data.get('premium', False)
    
    premium_price = PREMIUM_ONE_TIME_PRICE
    user_id = str(user["id"])
    
    profile_url = f"/u/{user['id']}"
    if is_premium and user_data.get("vanity_url"):
        profile_url = f"/u/{user_data['vanity_url']}"
    
    content = f"""
        <div class="grid gap-8">
            <div class="glass p-6 rounded-xl">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 sm:gap-0 mb-6">
                    <h2 class="text-2xl font-semibold text-white">Your Experience Timeline</h2>
                    <a href="{profile_url}" class="text-sm text-indigo-400 hover:text-indigo-300 transition-colors">View Public Profile &rarr;</a>
                </div>
                <div id="experience-timeline" class="space-y-4">
                    <div class="animate-pulse flex space-x-4">
                        <div class="flex-1 space-y-4 py-1">
                            <div class="h-4 bg-gray-700 rounded w-3/4"></div>
                            <div class="space-y-2">
                                <div class="h-4 bg-gray-700 rounded"></div>
                                <div class="h-4 bg-gray-700 rounded w-5/6"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="glass p-6 rounded-xl">
                <h2 class="text-2xl font-semibold mb-6 text-white">Pending Experiences</h2>
                <div id="pending-experiences" class="space-y-4">
                    <div class="text-gray-400">Loading pending experiences...</div>
                </div>
            </div>

            <div class="glass p-6 rounded-xl">
                <h2 class="text-2xl font-semibold mb-6 text-white">Server Management</h2>
                <div id="guilds-container" class="space-y-4">
                    <div class="text-gray-400">Loading your guilds...</div>
                </div>
            </div>
        </div>

        <script>
            const userId = '{user["id"]}';
            const isPremium = {str(is_premium).lower()};
            let experienceCount = 0;

            function getPremiumButtonHtml() {{
                return '<a href="/premium" class="block w-full bg-transparent border-2 border-yellow-500 hover:border-orange-600 text-yellow-500 hover:text-orange-600 px-4 py-3 rounded-lg font-semibold transition-all transform hover:scale-[1.02] shadow-lg text-center"><span title="Verified Premium Member"><svg class="w-6 h-6 text-yellow-500 inline-block align-text-bottom" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></span> Unlock the full potential of ServerCV with Premium</a>';
            }}
            
            fetch('/api/guilds')
                .then(response => response.json())
                .then(data => {{
                    if (data.error) {{
                        document.getElementById('guilds-container').innerHTML = `<div class="text-red-400">${{data.error}}</div>`;
                        return;
                    }}

                    const servers = data.servers || [];
                    if (servers.length === 0) {{
                        document.getElementById('guilds-container').innerHTML = '<div class="text-gray-400">No guilds found.</div>';
                        return;
                    }}

                    let requestEligible = servers.filter(s => ['Server Owner', 'Administrator', 'Moderator'].includes(s.label));
                    let viewEligible = servers.filter(s => ['Server Owner', 'Administrator'].includes(s.label));
                    
                    let html = '<div class="space-y-6">';
                    
                    html += '<div><h3 class="text-lg font-semibold mb-1 text-gray-200">Submit Endorsement Request</h3>';
                    html += '<p class="text-sm text-gray-400 mb-3">Select a server to request verification for your Discord experience in the server.</p>';
                    html += '<div class="flex flex-col sm:flex-row gap-2">';
                    html += '<select id="request-select" class="bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500 w-full sm:flex-grow">';
                    html += '<option value="">Choose a server...</option>';
                    requestEligible.forEach(s => {{
                        html += `<option value="${{s.id}}|${{s.name.replace(/'/g, "\\\\'")}}">${{s.name}} (${{s.id}}) - ${{s.label}}</option>`;
                    }});
                    html += '</select>';
                    html += '<button onclick="submitRequest(this)" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg font-medium transition-colors w-full sm:w-auto">Submit</button>';
                    html += '</div></div>';

                    html += '<div><h3 class="text-lg font-semibold mb-1 text-gray-200">View/Approve Endorsement Requests</h3>';
                    html += '<p class="text-sm text-gray-400 mb-3">Manage incoming and accepted requests for servers you administer or own.</p>';
                    html += '<div class="flex flex-col sm:flex-row gap-2">';
                    html += '<select id="view-select" class="bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500 w-full sm:flex-grow">';
                    html += '<option value="">Choose a server...</option>';
                    viewEligible.forEach(s => {{
                        html += `<option value="${{s.id}}">${{s.name}} (${{s.id}}) - ${{s.label}}</option>`;
                    }});
                    html += '</select>';
                    html += '<button onclick="viewPending(this)" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg font-medium transition-colors w-full sm:w-auto">View</button>';
                    html += '</div></div>';
                    
                    if (!isPremium) {{
                        html += `<div class="pt-4 border-t border-gray-700">${{getPremiumButtonHtml()}}</div>`;
                    }} else {{
                        html += '<div class="pt-4 border-t border-gray-700"><div class="text-green-400 font-semibold"><span title="Verified Premium Member"><svg class="w-6 h-6 text-yellow-500 inline-block align-text-bottom" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></span> You have Verified Premium Member access permanently. Enjoy adding unlimited experiences!</div></div>';
                    }}
                    
                    html += '</div>';

                    document.getElementById('guilds-container').innerHTML = html;
                }})
                .catch(error => {{
                    console.error('Error loading content:', error);
                    document.getElementById('guilds-container').innerHTML = '<div class="text-red-400">Failed to load content. Please refresh the page.</div>';
                }});

            fetch('/api/experiences')
                .then(response => response.json())
                .then(data => {{
                    const experiences = data.experiences || [];
                    experienceCount = experiences.length;
                    if (experiences.length === 0) {{
                        document.getElementById('experience-timeline').innerHTML = '<div class="text-gray-400">No experiences found.</div>';
                        return;
                    }}
                    
                    let html = '<div class="space-y-4">';
                    experiences.forEach(exp => {{
                        const end = exp.end_month ? `${{exp.end_month}}/${{exp.end_year}}` : '<span class="text-green-400">Present</span>';
                        html += `<div class="bg-gray-800/50 p-4 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">`;
                        html += `<div class="flex justify-between items-start gap-4">`;
                        html += `<div class="min-w-0 flex-1">`;
                        html += `<h3 class="font-semibold text-lg text-white break-words">${{exp.role_title}} <span class="text-gray-400 font-normal">at</span> <a href="/s/${{exp.server_id}}" class="hover:text-indigo-400 transition-colors" target="_blank">${{exp.server_name}}</a></h3>`;
                        html += `<div class="text-sm text-indigo-400 mb-2">${{exp.start_month}}/${{exp.start_year}} - ${{end}}</div>`;
                        if (exp.description) {{
                            html += `<p class="text-gray-300 text-sm mb-2 break-words">${{exp.description}}</p>`;
                        }}
                        html += `<div class="text-xs text-gray-500">Approved by: <a href="/u/${{exp.approved_by_slug || exp.approved_by}}" target="_blank" class="hover:underline hover:text-indigo-400 transition-colors">${{exp.approved_by_name}}</a></div>`;
                        html += `</div>`;
                        html += `<div class="flex flex-col gap-2 flex-shrink-0">`;
                        if (isPremium) {{
                            if (exp.is_pinned) {{
                                html += `<button onclick="unpinExperience('${{exp.id}}', this)" class="text-xs bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-500 px-2 py-1 rounded transition-colors">Unpin</button>`;
                            }} else {{
                                html += `<button onclick="pinExperience('${{exp.id}}', this)" class="text-xs bg-gray-700 hover:bg-gray-600 text-white px-2 py-1 rounded transition-colors">Pin</button>`;
                            }}
                        }}
                        if (!exp.end_year) {{
                            html += `<button onclick="editEndDate('${{exp.id}}')" class="text-xs bg-gray-700 hover:bg-gray-600 text-white px-2 py-1 rounded transition-colors">End Date</button>`;
                        }}
                        html += `<button onclick="deleteExperience('${{exp.id}}', this)" class="text-xs bg-red-900/50 hover:bg-red-900 text-red-200 px-2 py-1 rounded transition-colors">Delete</button>`;
                        html += `</div>`;
                        html += `</div>`;
                        html += `</div>`;
                    }});
                    html += '</div>';
                    document.getElementById('experience-timeline').innerHTML = html;
                }})
                .catch(error => {{
                    console.error('Error loading timeline:', error);
                    document.getElementById('experience-timeline').innerHTML = '<div class="text-red-400">Failed to load timeline.</div>';
                }});

            fetch('/api/pending_experiences')
                .then(response => response.json())
                .then(data => {{
                    const pending = data.pending || [];
                    if (pending.length === 0) {{
                        document.getElementById('pending-experiences').innerHTML = '<div class="text-gray-400">No pending requests.</div>';
                        return;
                    }}
                    
                    let html = '<div class="space-y-4">';
                    pending.forEach(exp => {{
                        const end = exp.end_month ? `${{exp.end_month}}/${{exp.end_year}}` : 'Present';
                        html += `<div class="bg-gray-800/50 p-4 rounded-lg border border-gray-700 border-l-4 border-l-yellow-500">`;
                        html += `<h3 class="font-semibold text-lg text-white">${{exp.role_title}} <span class="text-gray-400 font-normal">at</span> ${{exp.server_name}}</h3>`;
                        html += `<div class="text-sm text-gray-400 mb-2">${{exp.start_month}}/${{exp.start_year}} - ${{end}}</div>`;
                        if (exp.description) {{
                            html += `<p class="text-gray-300 text-sm mb-2">${{exp.description}}</p>`;
                        }}
                        html += `<div class="flex justify-between items-center">`;
                        html += `<div class="text-xs text-yellow-500 font-medium uppercase tracking-wide">Pending Approval</div>`;
                        html += `<div class="flex gap-2">`;
                        html += `<button onclick="editPendingExperience('${{exp.id}}')" class="text-xs bg-gray-700 hover:bg-gray-600 text-white px-2 py-1 rounded transition-colors">Edit</button>`;
                        html += `<button onclick="deletePendingExperience('${{exp.id}}', this)" class="text-xs bg-red-900/50 hover:bg-red-900 text-red-200 px-2 py-1 rounded transition-colors">Delete</button>`;
                        html += `</div></div>`;
                        html += `</div>`;
                    }});
                    html += '</div>';
                    document.getElementById('pending-experiences').innerHTML = html;
                }})
                .catch(error => {{
                    console.error('Error loading pending:', error);
                    document.getElementById('pending-experiences').innerHTML = '<div class="text-red-400">Failed to load pending requests.</div>';
                }});

            function editPendingExperience(expId) {{
                window.location.href = `/edit_pending/${{expId}}`;
            }}
            function deletePendingExperience(expId, btn) {{
                if (confirm('Are you sure you want to delete this pending request?')) {{
                    if (btn) {{
                        btn.disabled = true;
                        btn.innerHTML = '...';
                    }}
                    fetch(`/delete_pending/${{expId}}`, {{method: 'POST'}}).then(() => location.reload());
                }}
            }}

            function submitRequest(btn) {{
                const select = document.getElementById('request-select');
                const val = select.value;
                if (val) {{
                    if (!isPremium && experienceCount >= 5) {{
                        window.location.href = '/premium';
                        return;
                    }}
                    if (btn) {{
                        btn.disabled = true;
                        btn.classList.add('opacity-50', 'cursor-not-allowed');
                        btn.innerHTML = '<svg class="animate-spin h-5 w-5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
                    }}
                    const [id, name] = val.split('|');
                    window.location.href = `/request/${{id}}?name=${{encodeURIComponent(name)}}`;
                }}
            }}
            function viewPending(btn) {{
                const select = document.getElementById('view-select');
                const id = select.value;
                if (id) {{
                    if (btn) {{
                        btn.disabled = true;
                        btn.classList.add('opacity-50', 'cursor-not-allowed');
                        btn.innerHTML = '<svg class="animate-spin h-5 w-5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
                    }}
                    window.location.href = `/view/${{id}}`;
                }}
            }}
            function editEndDate(expId) {{
                window.location.href = `/end/${{expId}}`;
            }}
            function pinExperience(expId, btn) {{
                if (btn) {{
                    btn.disabled = true;
                    btn.innerHTML = '...';
                }}
                fetch(`/pin/${{expId}}`, {{method: 'POST'}})
                    .then(res => res.json())
                    .then(data => {{
                        if (data.error) alert(data.error);
                        else location.reload();
                    }});
            }}
            function unpinExperience(expId, btn) {{
                if (btn) {{
                    btn.disabled = true;
                    btn.innerHTML = '...';
                }}
                fetch(`/unpin/${{expId}}`, {{method: 'POST'}})
                    .then(res => res.json())
                    .then(data => {{
                        if (data.error) alert(data.error);
                        else location.reload();
                    }});
            }}
            function deleteExperience(expId, btn) {{
                if (confirm('Are you sure you want to delete this experience?')) {{
                    if (btn) {{
                        const container = btn.closest('.flex');
                        if (container) {{
                            const buttons = container.querySelectorAll('button');
                            buttons.forEach(b => {{
                                b.disabled = true;
                                b.classList.add('opacity-50', 'cursor-not-allowed');
                            }});
                        }}
                        btn.innerHTML = '<svg class="animate-spin h-5 w-5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
                    }}
                    fetch(`/delete/${{expId}}`, {{method: 'POST'}}).then(() => location.reload());
                }}
            }}
        </script>
    """
    
    return wrap_page("Dashboard", content, nav_links=[("/dashboard", "Dashboard", "bg-gray-800"), ("/settings", "Settings", ""), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/settings", methods=["GET", "POST"])
def settings():
    if "discord_token" not in session:
        return redirect(f"/login?redirect_to={quote(request.full_path)}")
    
    user = requests_session.get(f"{API_BASE}/users/@me", headers={"Authorization": f"Bearer {session['discord_token']}"}).json()
    user_id = str(user["id"])
    user_data = get_user_data(user_id)
    is_premium = user_data.get("premium", False)
    
    if request.method == "POST":
        # Handle Vanity URL
        vanity_url = request.form.get("vanity_url", "").strip()
        if vanity_url:
            if not is_premium:
                return error_page("Vanity URLs are a Premium feature.", 403)
            if not re.match(r"^[a-zA-Z0-9_]+$", vanity_url):
                return error_page("Invalid Vanity URL. Only alphanumeric characters and underscores allowed.", 400)
            
            # Check uniqueness
            ref = db.reference("Dashboard Users")
            existing = ref.order_by_child("vanity_url").equal_to(vanity_url).get()
            if existing and list(existing.keys())[0] != user_id:
                return error_page("Vanity URL already taken.", 400)
            
            db.reference(f"Dashboard Users/{user_id}").update({"vanity_url": vanity_url})
        elif is_premium:
            # Allow clearing vanity URL if premium
            db.reference(f"Dashboard Users/{user_id}").update({"vanity_url": ""})

        # Handle Social Links
        socials = request.form.getlist("socials[]")
        socials = [s.strip() for s in socials if s.strip()]
        
        limit = SOCIAL_LIMIT_PREMIUM if is_premium else SOCIAL_LIMIT_FREE
        if len(socials) > limit:
             return error_page(f"You can only have {limit} social links.", 400)
        
        db.reference(f"Dashboard Users/{user_id}").update({"socials": socials})
        
        return redirect("/settings?saved=true")

    current_vanity = user_data.get("vanity_url", "")
    current_socials = user_data.get("socials", [])
    
    social_inputs = ""
    limit = SOCIAL_LIMIT_PREMIUM if is_premium else SOCIAL_LIMIT_FREE
    
    # Render existing
    for link in current_socials:
        social_inputs += f'<input type="url" name="socials[]" value="{html.escape(link)}" class="w-full bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2 mb-2 focus:outline-none focus:border-indigo-500" placeholder="https://twitter.com/username">'
    
    # Render remaining slots
    remaining = limit - len(current_socials)
    if remaining > 0:
        for _ in range(remaining):
             social_inputs += '<input type="url" name="socials[]" class="w-full bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2 mb-2 focus:outline-none focus:border-indigo-500" placeholder="Add social link...">'

    success_html = ""
    if request.args.get("saved"):
        success_html = """
        <div class="bg-green-900/50 border border-green-500 text-green-200 px-4 py-3 rounded-lg mb-6" role="alert">
            <strong class="font-bold">Success!</strong>
            <span class="block sm:inline">Your settings have been saved.</span>
        </div>
        """

    content = f"""
    <div class="max-w-2xl mx-auto">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 sm:gap-0 mb-8">
            <h1 class="text-3xl font-semibold text-white">Settings</h1>
            <a href="/dashboard" class="text-sm text-indigo-400 hover:text-indigo-300 transition-colors">&larr; Back to Dashboard</a>
        </div>
        
        {success_html}
        
        <form method="POST" class="space-y-8">
            <div class="glass p-6 rounded-xl">
                <h2 class="text-xl font-semibold text-white mb-4">Profile Settings</h2>
                
                <div class="mb-6">
                    <label class="block text-gray-400 text-sm font-bold mb-2">Vanity URL {'' if is_premium else '(Premium Only)'}</label>
                    <div class="flex flex-col sm:flex-row sm:items-center gap-2">
                        <span class="text-gray-500 whitespace-nowrap">servercv.com/u/</span>
                        <input type="text" name="vanity_url" value="{html.escape(current_vanity)}" {'disabled' if not is_premium else ''} class="w-full sm:flex-grow bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500 {'opacity-50 cursor-not-allowed' if not is_premium else ''}" placeholder="custom_name">
                    </div>
                    {f'<p class="text-sm text-yellow-500 mt-1">Upgrade to Premium to set a custom URL.</p>' if not is_premium else ''}
                </div>
                
                <div>
                    <label class="block text-gray-400 text-sm font-bold mb-2">Social Links (Max {limit})</label>
                    {social_inputs}
                </div>
            </div>
            
            <div class="flex justify-end">
                <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg font-semibold transition-colors">Save Changes</button>
            </div>
        </form>
    </div>
    """
    return wrap_page("Settings", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", "text-white bg-gray-800"), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/pin/<exp_id>", methods=["POST"])
def pin_experience(exp_id):
    if "discord_token" not in session:
        return jsonify({"error": "Not authenticated"}), 401
        
    user = requests_session.get(f"{API_BASE}/users/@me", headers={"Authorization": f"Bearer {session['discord_token']}"}).json()
    user_id = str(user["id"])
    user_data = get_user_data(user_id)
    
    if not user_data.get("premium", False):
        return jsonify({"error": "Premium required"}), 403
        
    # Verify ownership
    ref = db.reference(f"Experiences/{exp_id}")
    exp = ref.get()
    if not exp or str(exp.get("user_id")) != user_id:
        return jsonify({"error": "Experience not found or unauthorized"}), 404
        
    ref.update({"is_pinned": True})
    return jsonify({"success": True})

@dashboard.route("/unpin/<exp_id>", methods=["POST"])
def unpin_experience(exp_id):
    if "discord_token" not in session:
        return jsonify({"error": "Not authenticated"}), 401
        
    user = requests_session.get(f"{API_BASE}/users/@me", headers={"Authorization": f"Bearer {session['discord_token']}"}).json()
    user_id = str(user["id"])
    
    # Verify ownership
    ref = db.reference(f"Experiences/{exp_id}")
    exp = ref.get()
    if not exp or str(exp.get("user_id")) != user_id:
        return jsonify({"error": "Experience not found or unauthorized"}), 404
        
    ref.update({"is_pinned": False})
    return jsonify({"success": True})

@dashboard.route("/api/guilds")
def api_dashboard_guilds():
    if "discord_token" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    user_id = session.get("user_id")
    if user_id:
        current_time = time()
        if user_id in last_requests:
            if current_time - last_requests[user_id] < 5:
                return jsonify({"error": "Rate limit exceeded. Please wait 5 seconds and reload the page."}), 429
        last_requests[user_id] = current_time

    try:
        discord_token = session['discord_token']
        guilds = requests_session.get(f"{API_BASE}/users/@me/guilds", headers={"Authorization": f"Bearer {discord_token}"}).json()

        if not isinstance(guilds, list):
            return jsonify({"error": "Failed to load guilds"}), 500

        guilds_sorted = sorted(guilds, key=lambda g: (g.get("name") or "").lower())

        servers = []
        for g in guilds_sorted:
            perms = get_permissions_list(int(g.get("permissions", 0)))

            if g.get("owner"):
                label = "Server Owner"
            elif "Administrator" in perms:
                label = "Administrator"
            elif any(perm in perms for perm in MOD_PERMS):
                label = "Moderator"
            else:
                label = "Member"

            icon = f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png?size=128" if g.get("icon") else None

            servers.append({
                "name": html.escape(g.get('name', 'Unknown Server')),
                "id": str(g.get('id')),
                "label": label,
                "icon": icon,
            })

        return jsonify({"servers": servers})
    
    except Exception as e:
        return jsonify({"error": f"Failed to load guilds: {str(e)}"}), 500

@dashboard.route("/api/experiences")
def api_experiences():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    user_id = session["user_id"]
    experiences = get_user_experiences(user_id)
    # Sort: Pinned first, then by date (newest first)
    experiences.sort(key=lambda x: (x.get('is_pinned', False), int(x["start_year"]), int(x["start_month"])), reverse=True)
    return jsonify({"experiences": experiences})

@dashboard.route("/api/pending_experiences")
def api_pending_experiences():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    user_id = session["user_id"]
    ref = db.reference("Experiences")
    experiences = ref.order_by_child("user_id").equal_to(user_id).get()
    pending = []
    if experiences:
        for k, exp in experiences.items():
            if exp.get("status") == "pending":
                exp_copy = exp.copy()
                exp_copy["id"] = k
                pending.append(exp_copy)
    return jsonify({"pending": pending})

@dashboard.route("/request/<server_id>", methods=["GET", "POST"])
def request_endorsement(server_id):
    if "user_id" not in session:
        return redirect(f"/login?redirect_to={quote(request.full_path)}")
    user_id = session["user_id"]

    user_data = get_user_data(user_id)
    is_premium = user_data.get('premium', False)
    
    if not is_premium:
        experiences = get_user_experiences(user_id)
        ref = db.reference("Experiences")
        pending_query = ref.order_by_child("user_id").equal_to(user_id).get()
        pending = [exp for exp in pending_query.values() if exp.get("status") == "pending"] if pending_query else []
        total = len(experiences) + len(pending)
        if total >= EXP_LIMIT_FREE:
            return redirect("/premium")

    discord_token = session['discord_token']
    role, guild_data = get_user_role_and_guild(user_id, server_id, discord_token)
    if role not in ["Server Owner", "Administrator", "Moderator"]:
        return error_page("Not authorized", 403)
    server_name = request.args.get("name", "Unknown Server")
    if request.method == "POST":
        experiences = get_user_experiences(user_id)
        ref = db.reference("Experiences")
        pending_query = ref.order_by_child("user_id").equal_to(user_id).get()
        pending = [exp for exp in pending_query.values() if exp.get("status") == "pending"] if pending_query else []
        total = len(experiences) + len(pending)
        user_data = get_user_data(user_id)
        is_premium = user_data.get('premium', False)
        if total >= EXP_LIMIT_FREE and not is_premium:
            return redirect("/premium")
        role_title = request.form.get("role_title")
        start_month = request.form.get("start_month")
        start_year = request.form.get("start_year")
        end_month = request.form.get("end_month")
        end_year = request.form.get("end_year")
        description = request.form.get("description")
        
        # Validation
        try:
            sm = int(start_month)
            sy = int(start_year)
            if end_month and end_year:
                em = int(end_month)
                ey = int(end_year)
                if ey < sy or (ey == sy and em < sm):
                    return error_page("End date cannot be before start date.", 400)
        except ValueError:
            return error_page("Invalid date format.", 400)

        limit = DESC_LIMIT_PREMIUM if is_premium else DESC_LIMIT_FREE
        if description and len(description) > limit:
            return error_page(f"Description exceeds limit of {limit} characters.", 400)
        
        # Get server icon
        server_icon = guild_data.get("icon") if guild_data else None
                
        save_experience_request(user_id, server_id, server_name, role_title, start_month, request.form.get("start_year"), end_month, end_year, description, role, server_icon)
        return redirect("/dashboard")
    content = f"""
    <div class="max-w-2xl mx-auto">
        <div class="glass p-8 rounded-2xl">
            <h2 class="text-2xl font-semibold mb-6 text-white">Request Experience for {html.escape(server_name)}</h2>
            <form method="post" class="space-y-4" onsubmit="const btn = this.querySelector('button[type=submit]'); btn.disabled = true; btn.classList.add('opacity-50', 'cursor-not-allowed'); btn.innerHTML = 'Submitting...';">
                <div>
                    <label class="block text-sm font-medium text-gray-400 mb-1">Role Title</label>
                    <input name="role_title" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">Start Month</label>
                        <input name="start_month" type="number" min="1" max="12" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">Start Year</label>
                        <input name="start_year" type="number" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">End Month</label>
                        <input name="end_month" type="number" min="1" max="12" placeholder="Present" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">End Year</label>
                        <input name="end_year" type="number" placeholder="Present" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                </div>
                
                <div>
                    <label class="block text-sm font-medium text-gray-400 mb-1">Description (Max {DESC_LIMIT_PREMIUM if is_premium else DESC_LIMIT_FREE} chars)</label>
                    <textarea name="description" rows="4" maxlength="{DESC_LIMIT_PREMIUM if is_premium else DESC_LIMIT_FREE}" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors"></textarea>
                </div>
                
                <div class="flex gap-4 pt-4">
                    <button type="submit" class="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg font-semibold transition-all transform hover:scale-[1.02]">Submit Request</button>
                    <a href="/dashboard" class="px-6 py-3 rounded-lg font-medium text-gray-400 hover:text-white hover:bg-gray-800 transition-colors flex items-center justify-center">Cancel</a>
                </div>
            </form>
        </div>
    </div>
    """
    return wrap_page(f"Request Experience - {server_name}", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", ""), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/view/<server_id>")
def view(server_id):
    if "user_id" not in session:
        return redirect(f"/login?redirect_to={quote(request.full_path)}")
    
    content = f"""
    <div class="max-w-4xl mx-auto">
        <div class="glass p-8 rounded-2xl mb-8">
            <div class="mb-6">
                <div class="flex justify-between items-center mb-2">
                    <a href="/dashboard" class="text-sm text-gray-400 hover:text-white transition-colors">&larr; Back to Dashboard</a>
                    <a href="/s/{server_id}" class="text-sm text-indigo-400 hover:text-indigo-300 transition-colors" target="_blank">View Public Server Profile &rarr;</a>
                </div>
                <h2 id="server-title" class="text-2xl font-semibold text-white"><span class="animate-pulse bg-gray-700 rounded h-6 w-32 inline-block align-middle ml-2"></span></h2>
            </div>

            <div id="server-info-container"></div>
            
            <div id="server-settings-container"></div>

            <div id="view-content" class="space-y-8">
                <div class="animate-pulse space-y-4">
                    <div class="h-8 bg-gray-700 rounded w-1/4"></div>
                    <div class="h-32 bg-gray-700 rounded"></div>
                    <div class="h-32 bg-gray-700 rounded"></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
    const serverId = '{server_id}';
    const clientId = '{CLIENT_ID}';
    
    function disableBtn(btn) {{
        if (!btn) return;
        const container = btn.closest('.flex');
        if (container) {{
            const buttons = container.querySelectorAll('button');
            buttons.forEach(b => {{
                b.disabled = true;
                b.classList.add('opacity-50', 'cursor-not-allowed');
            }});
        }}
        btn.innerHTML = '<svg class="animate-spin h-5 w-5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
    }}

    function renderView(data) {{
        if (data.error) {{
            document.getElementById('view-content').innerHTML = `<div class="text-red-400">${{data.error}}</div>`;
            return;
        }}

        // Update Title
        document.getElementById('server-title').innerHTML = `Experience Requests for <a href="/s/${{serverId}}" class="hover:text-indigo-400 transition-colors" target="_blank">${{data.server_name}}</a>`;

        // Server ID and Ownership
        const isOwner = data.is_owner ? '<span class="text-green-400 font-medium">(Server Owner)</span>' : '(Server Administrator)';
        document.getElementById('server-info-container').innerHTML = `
            <div class="mb-6">
                <div class="text-sm text-gray-400">Server ID: <span class="text-gray-200 font-mono">${{serverId}}</span> ${{isOwner}}</div>
            </div>`;

        // Server Settings
        if (data.is_owner) {{
            const isPremium = data.is_premium;
            const disabledAttr = isPremium ? '' : 'disabled';
            const opacityClass = isPremium ? '' : 'opacity-50 cursor-not-allowed';
            const premiumMessage = isPremium ? '' : '<p class="text-sm text-yellow-500 mt-1">Upgrade to Premium to set a custom URL.</p>';
            const buttonHtml = isPremium 
                ? `<button onclick="saveServerSettings(this)" class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg font-semibold transition-colors h-[42px]">Save</button>`
                : `<a href="/premium" class="bg-yellow-600 hover:bg-yellow-700 text-white px-6 py-2 rounded-lg font-semibold transition-colors h-[42px] flex items-center justify-center whitespace-nowrap">Get Premium</a>`;

            document.getElementById('server-settings-container').innerHTML = `
            <div class="glass p-6 rounded-xl mb-8 border border-yellow-500/30">
                <h3 class="text-xl font-semibold text-white mb-4">Server Settings ${{isPremium ? '(Premium)' : '(Premium Only)'}}</h3>
                <div class="flex flex-col sm:flex-row items-end gap-4">
                    <div class="flex-grow w-full">
                        <label class="block text-gray-400 text-sm font-bold mb-2">Server Vanity URL</label>
                        <div class="flex items-center gap-2">
                            <span class="text-gray-500 whitespace-nowrap">servercv.com/s/</span>
                            <input type="text" id="server-vanity" value="${{data.server_vanity || ''}}" ${{disabledAttr}} class="w-full bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500 ${{opacityClass}}" placeholder="custom_server_name">
                        </div>
                        ${{premiumMessage}}
                    </div>
                    ${{buttonHtml}}
                </div>
            </div>`;
        }}

        let html = '';

        // Pending
        html += `
            <div>
                <h3 class="text-xl font-semibold text-white mb-4 flex items-center gap-2">
                    <span class="w-2 h-2 bg-yellow-500 rounded-full"></span>
                    Pending Requests
                </h3>`;
                
        if (!data.bot_in_server) {{
            html += `
                <div class="bg-indigo-900/30 border border-indigo-500/30 p-4 rounded-xl mb-6 flex items-start gap-4">
                    <div class="p-2 bg-indigo-500/20 rounded-lg text-indigo-400">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"></path></svg>
                    </div>
                    <div>
                        <h4 class="text-white font-medium mb-1">Get Notified!</h4>
                        <p class="text-sm text-gray-400 mb-3">Invite our Discord bot to your server to get instant notifications when someone submits an experience request. Run <code class="bg-gray-800 px-1 py-0.5 rounded text-gray-300 text-xs">/setup</code> in your server to configure the notification channel.</p>
                        <a href="https://discord.com/api/oauth2/authorize?client_id=${{clientId}}&permissions=2048&scope=bot%20applications.commands" target="_blank" class="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            Invite Bot
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                        </a>
                    </div>
                </div>`;
        }} else if (!data.notification_channel_id) {{
            html += `
                <div class="bg-yellow-900/30 border border-yellow-500/30 p-4 rounded-xl mb-6 flex items-center gap-4">
                    <div class="p-2 bg-yellow-500/20 rounded-lg text-yellow-400">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                    </div>
                    <div>
                        <h4 class="text-white font-medium">Setup Required</h4>
                        <p class="text-sm text-gray-400">Our Discord bot is in your server, but notifications aren't configured. Run <code class="bg-gray-800 px-1 py-0.5 rounded text-gray-300 text-xs">/setup</code> in your server to select a channel.</p>
                    </div>
                </div>`;
        }} else {{
            html += `
                <div class="mb-6 flex items-center gap-2 text-sm text-gray-400">
                    <svg class="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                    <span>Any notifications will be sent to <span class="text-gray-300 font-medium">#${{data.notification_channel_name}}</span> <span class="text-gray-600 text-xs">(${{data.notification_channel_id}})</span></span>
                </div>`;
        }}

        html += `<div class="space-y-4">`;

        if (data.pending && data.pending.length > 0) {{
            data.pending.forEach(exp => {{
                html += `
                <div class="bg-gray-800/50 p-6 rounded-xl border border-gray-700 border-l-4 border-l-yellow-500">
                    <div class="flex justify-between items-start mb-4">
                        <div>
                            <div class="font-semibold text-lg text-white">${{exp.role_title}}</div>
                            <div class="text-indigo-400 text-sm">User: <a href="/u/${{exp.user_id}}" target="_blank" class="hover:underline hover:text-indigo-300">${{exp.user_name}}</a> <span class="text-gray-500">(${{exp.user_id}})</span></div>
                        </div>
                        <div class="text-sm font-mono text-gray-400 bg-gray-900/50 px-3 py-1 rounded-full">
                            ${{exp.start_month}}/${{exp.start_year}} - ${{exp.end_month}}/${{exp.end_year}}
                        </div>
                    </div>
                    
                    <div class="bg-gray-900/30 p-4 rounded-lg text-gray-300 text-sm mb-4">
                        ${{exp.description}}
                    </div>
                    
                    `;

                if (exp.can_approve || exp.can_reject || exp.can_edit) {{
                    html += `<div class="flex justify-end items-center gap-3">`;
                }}
                
                if (exp.can_approve) {{
                    html += `<button onclick="approve('${{exp.id}}', this)" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">Approve</button>`;
                }}
                if (exp.can_reject) {{
                    html += `<button onclick="reject('${{exp.id}}', this)" class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">Reject</button>`;
                }}
                if (exp.can_edit) {{
                    html += `<button onclick="edit_pending('${{exp.id}}')" class="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">Edit</button>`;
                }}
                if (exp.can_approve || exp.can_reject || exp.can_edit) {{ 
                    html += `</div>`;
                }}
                
                html += `</div>`;
            }});
        }} else {{
            html += `<div class="bg-gray-800/30 p-6 rounded-xl text-center text-gray-500">No pending requests.</div>`;
        }}
        html += '</div></div>';

        // Approved
        html += `
            <div class="mt-8">
                <h3 class="text-xl font-semibold text-white mb-4 flex items-center gap-2">
                    <span class="w-2 h-2 bg-green-500 rounded-full"></span>
                    Accepted Experiences
                </h3>
                <div class="space-y-4">`;

        if (data.approved && data.approved.length > 0) {{
            data.approved.forEach(exp => {{
                html += `
                <div class="bg-gray-800/50 p-6 rounded-xl border border-gray-700 opacity-75 hover:opacity-100 transition-opacity">
                    <div class="flex justify-between items-start mb-4">
                        <div>
                            <div class="font-semibold text-lg text-white">${{exp.role_title}}</div>
                            <div class="text-indigo-400 text-sm">User: <a href="/u/${{exp.user_id}}" target="_blank" class="hover:underline hover:text-indigo-300">${{exp.user_name}}</a> <span class="text-gray-500">(${{exp.user_id}})</span></div>
                        </div>
                        <div class="text-sm font-mono text-gray-400 bg-gray-900/50 px-3 py-1 rounded-full">
                            ${{exp.start_month}}/${{exp.start_year}} - ${{exp.end_display}}
                        </div>
                    </div>
                    
                    <div class="bg-gray-900/30 p-4 rounded-lg text-gray-300 text-sm mb-4">
                        ${{exp.description}}
                    </div>
                    
                    <div class="flex justify-between items-center">
                        <div class="text-xs text-gray-500">Approved by: <a href="/u/${{exp.approver_id}}" target="_blank" class="hover:underline hover:text-indigo-400 transition-colors">${{exp.approver_name}}</a></div>
                        <div class="flex gap-3">`;
                
                if (exp.can_edit) {{
                    html += `<button onclick="edit_accepted('${{exp.id}}')" class="bg-gray-700 hover:bg-gray-600 text-white px-3 py-1.5 rounded text-xs font-medium transition-colors">Edit</button>`;
                }}
                if (exp.can_delete) {{
                    html += `<button onclick="delete_experience('${{exp.id}}', this)" class="bg-red-900/50 hover:bg-red-900 text-red-200 px-3 py-1.5 rounded text-xs font-medium transition-colors">Delete</button>`;
                }}
                
                html += `</div></div></div>`;
            }});
        }} else {{
            html += `<div class="bg-gray-800/30 p-6 rounded-xl text-center text-gray-500">No accepted experiences.</div>`;
        }}
        html += '</div></div>';

        document.getElementById('view-content').innerHTML = html;
    }}

    function loadData() {{
        fetch(`/api/guild/${{serverId}}`)
            .then(res => res.json())
            .then(data => renderView(data))
            .catch(err => {{
                console.error(err);
                document.getElementById('view-content').innerHTML = '<div class="text-red-400">Failed to load content.</div>';
            }});
    }}

    function approve(id, btn) {{
        disableBtn(btn);
        fetch(`/approve/${{id}}`, {{method: 'POST'}})
            .then(res => res.json())
            .then(data => {{
                if (data.success) {{
                    loadData();
                }} else {{
                    alert(data.error || 'Failed');
                    location.reload();
                }}
            }})
            .catch(() => location.reload());
    }}
    function reject(id, btn) {{
        disableBtn(btn);
        fetch(`/reject/${{id}}`, {{method: 'POST'}})
            .then(res => res.json())
            .then(data => {{
                if (data.success) {{
                    loadData();
                }} else {{
                    alert(data.error || 'Failed');
                    location.reload();
                }}
            }})
            .catch(() => location.reload());
    }}
    function edit_pending(id) {{
        window.location.href = `/edit_pending/${{id}}`;
    }}
    function edit_accepted(id) {{
        window.location.href = `/edit_accepted/${{id}}`;
    }}
    function delete_experience(id, btn) {{
        if (confirm('Are you sure you want to delete this experience?')) {{
            disableBtn(btn);
            fetch(`/delete/${{id}}`, {{method: 'POST'}}).then(() => location.reload());
        }}
    }}

    function saveServerSettings(btn) {{
        const vanity = document.getElementById('server-vanity').value;
        disableBtn(btn);
        
        const formData = new FormData();
        formData.append('vanity_url', vanity);
        
        fetch(`/api/server_settings/${{serverId}}`, {{
            method: 'POST',
            body: formData
        }})
        .then(response => response.json())
        .then(data => {{
            if (data.error) {{
                alert(data.error);
                btn.disabled = false;
                btn.classList.remove('opacity-50', 'cursor-not-allowed');
                btn.innerHTML = 'Save';
            }} else {{
                alert('Settings saved successfully!');
                location.reload();
            }}
        }})
        .catch(err => {{
            alert('Failed to save settings');
            console.error(err);
            btn.disabled = false;
            btn.classList.remove('opacity-50', 'cursor-not-allowed');
            btn.innerHTML = 'Save';
        }});
    }}

    loadData();
    </script>
    """
    
    return wrap_page(f"Manage Server", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", ""), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/api/guild/<server_id>")
def api_server_view(server_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    user_id = session["user_id"]
    discord_token = session['discord_token']
    
    try:
        role, guild_data = get_user_role_and_guild(user_id, server_id, discord_token)
        if role not in ["Server Owner", "Administrator"]:
            return jsonify({"error": "Not authorized"}), 403
        
        all_exp = get_all_experiences_for_server(server_id)
        pending_list = [exp for exp in all_exp if exp.get("status") == "pending"]
        approved_list = [exp for exp in all_exp if exp.get("status") == "approved"]
        
        # Get server name
        server_name = guild_data.get("name", "Unknown Server") if guild_data else "Unknown Server"
        
        # Process pending
        pending_data = []
        for exp in pending_list:
            if role == "Server Owner":
                can_approve = True
            elif role == "Administrator":
                requester_role = exp.get("requester_role")
                can_approve = requester_role not in ["Server Owner", "Administrator"] and exp['user_id'] != user_id
            else:
                can_approve = False
            
            pending_data.append({
                "id": exp['id'],
                "role_title": html.escape(exp['role_title']),
                "user_name": html.escape(exp['user_name']),
                "user_id": exp['user_id'],
                "start_month": exp['start_month'],
                "start_year": exp['start_year'],
                "end_month": exp.get('end_month', 'N/A'),
                "end_year": exp.get('end_year', 'N/A'),
                "description": html.escape(exp.get('description', 'No description provided.')),
                "can_approve": can_approve,
                "can_reject": can_approve,
                "can_edit": can_approve
            })

        # Process approved
        approved_data = []
        for exp in approved_list:
            exp_user_role = exp.get("requester_role", "Member")
            can_edit = False
            can_delete = False
            if role == "Server Owner":
                can_edit = True
                can_delete = True
            elif role == "Administrator":
                if exp_user_role not in ["Server Owner", "Administrator"] and exp['user_id'] != user_id:
                    can_edit = True
            
            end = f"{exp.get('end_month')}/{exp.get('end_year')}" if exp.get('end_month') else 'Present'
            
            approved_data.append({
                "id": exp['id'],
                "role_title": html.escape(exp['role_title']),
                "user_name": html.escape(exp['user_name']),
                "user_id": exp['user_id'],
                "start_month": exp['start_month'],
                "start_year": exp['start_year'],
                "end_display": end,
                "description": html.escape(exp.get('description', '')),
                "approver_name": html.escape(exp.get('approver_name', 'Unknown')),
                "approver_id": exp.get('approved_by'),
                "can_edit": can_edit,
                "can_delete": can_delete
            })

        user_data = get_user_data(user_id)
        is_premium = user_data.get("premium", False)
        is_owner = role == "Server Owner"
        
        server_vanity = "";
        if is_owner and is_premium:
            server_data = db.reference(f"Dashboard Servers/{server_id}").get()
            if server_data:
                server_vanity = server_data.get("vanity_url", "")

        # Check bot status
        bot_in_server = False
        notification_channel_name = None
        notification_channel_id = None
        
        try:
            # Check if bot is in server
            bot_guild_res = requests_session.get(
                f"{API_BASE}/guilds/{server_id}",
                headers={"Authorization": f"Bot {BOT_TOKEN}"}
            )
            
            if bot_guild_res.status_code == 200:
                bot_in_server = True
                
                # Check for notification channel config
                config_ref = db.reference(f'Request Notification Config/{server_id}/notification_channel')
                channel_id = config_ref.get()
                
                if channel_id:
                    notification_channel_id = channel_id
                    # Try to get channel name
                    channel_res = requests_session.get(
                        f"{API_BASE}/channels/{channel_id}",
                        headers={"Authorization": f"Bot {BOT_TOKEN}"}
                    )
                    if channel_res.status_code == 200:
                        notification_channel_name = channel_res.json().get('name')
                    else:
                        notification_channel_name = "Unknown Channel"
        except Exception as e:
            print(f"Error checking bot status: {e}")

        return jsonify({
            "server_name": html.escape(server_name),
            "pending": pending_data,
            "approved": approved_data,
            "is_premium": is_premium,
            "is_owner": is_owner,
            "server_vanity": server_vanity,
            "bot_in_server": bot_in_server,
            "notification_channel_id": notification_channel_id,
            "notification_channel_name": notification_channel_name
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@dashboard.route("/api/server_settings/<server_id>", methods=["POST"])
def save_server_settings(server_id):
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_id = session["user_id"]
    discord_token = session['discord_token']
    
    # Check premium
    user_data = get_user_data(user_id)
    if not user_data.get("premium", False):
        return jsonify({"error": "Premium required"}), 403
        
    # Check owner
    role = get_user_role_in_server(user_id, server_id, discord_token)
    if role != "Server Owner":
        return jsonify({"error": "Only server owner can change settings"}), 403
        
    vanity_url = request.form.get("vanity_url", "").strip()
    
    if vanity_url:
        if not re.match("^[a-zA-Z0-9_]+$", vanity_url):
             return jsonify({"error": "Invalid vanity URL format"}), 400
        
        # Check if taken by another server
        servers_ref = db.reference("Dashboard Servers")
        existing = servers_ref.order_by_child("vanity_url").equal_to(vanity_url).get()
        if existing:
            for key in existing:
                if key != server_id:
                    return jsonify({"error": "Vanity URL already taken"}), 400
    
    db.reference(f"Dashboard Servers/{server_id}").update({"vanity_url": vanity_url})
    return jsonify({"success": True})

@dashboard.route("/approve/<exp_id>", methods=["POST"])
def approve(exp_id):
    if "user_id" not in session:
        return "Not logged in", 401
    user_id = session["user_id"]
    discord_token = session['discord_token']
    exp = db.reference(f"Experiences/{exp_id}").get()
    if not exp:
        return "Not found", 404
    server_id = exp["server_id"]
    role = get_user_role_in_server(user_id, server_id, discord_token)
    if role not in ["Server Owner", "Administrator"]:
        return "Not authorized", 403
    if role == "Server Owner":
        can_approve = True
    elif role == "Administrator":
        requester_role = exp.get("requester_role")
        can_approve = requester_role not in ["Server Owner", "Administrator"] and exp['user_id'] != user_id
    else:
        can_approve = False
    if not can_approve:
        return jsonify({"error": "Cannot approve this request"}), 403
    approve_experience(exp_id, user_id)
    return jsonify({"success": True})

@dashboard.route("/reject/<exp_id>", methods=["POST"])
def reject(exp_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    user_id = session["user_id"]
    discord_token = session['discord_token']
    exp = db.reference(f"Experiences/{exp_id}").get()
    if not exp:
        return jsonify({"error": "Not found"}), 404
    server_id = exp["server_id"]
    role = get_user_role_in_server(user_id, server_id, discord_token)
    if role not in ["Server Owner", "Administrator"]:
        return jsonify({"error": "Not authorized"}), 403
    reject_experience(exp_id)
    return jsonify({"success": True})

@dashboard.route("/edit_pending/<exp_id>", methods=["GET", "POST"])
def edit_pending(exp_id):
    if "user_id" not in session:
        return redirect(f"/login?redirect_to={quote(request.full_path)}")
    user_id = session["user_id"]
    discord_token = session['discord_token']
    exp = db.reference(f"Experiences/{exp_id}").get()
    if not exp:
        return error_page("Not found", 404)
    server_id = exp["server_id"]
    role = get_user_role_in_server(user_id, server_id, discord_token)
    
    # Allow if server owner/admin OR if it's the user's own request
    if role not in ["Server Owner", "Administrator"] and str(exp.get("user_id")) != user_id:
        return error_page("Not authorized", 403)
    
    exp_user_id = str(exp["user_id"])
    user_data = get_user_data(exp_user_id)
    is_premium = user_data.get("premium", False)
    limit = DESC_LIMIT_PREMIUM if is_premium else DESC_LIMIT_FREE

    if request.method == "POST":
        # Validation
        start_month = request.form.get("start_month")
        start_year = request.form.get("start_year")
        end_month = request.form.get("end_month")
        end_year = request.form.get("end_year")
        
        try:
            sm = int(start_month)
            sy = int(start_year)
            if end_month and end_year:
                em = int(end_month)
                ey = int(end_year)
                if ey < sy or (ey == sy and em < sm):
                    return error_page("End date cannot be before start date.", 400)
        except ValueError:
            return error_page("Invalid date format.", 400)

        description = request.form.get("description")
        if description and len(description) > limit:
             return error_page(f"Description exceeds limit of {limit} characters.", 400)

        updates = {}
        for field in ["role_title", "start_month", "start_year", "end_month", "end_year", "description"]:
            val = request.form.get(field)
            if val or field in ["end_month", "end_year", "description"]:  # allow empty for end and description
                updates[field] = val if val else None
        db.reference(f"Experiences/{exp_id}").update(updates)
        
        if role in ["Server Owner", "Administrator"]:
            return redirect(f"/view/{server_id}")
        else:
            return redirect("/dashboard")
    
    content = f"""
    <div class="max-w-2xl mx-auto">
        <div class="glass p-8 rounded-2xl">
            <h2 class="text-2xl font-semibold mb-6 text-white">Edit Experience</h2>
            <form method="post" class="space-y-4" onsubmit="const btn = this.querySelector('button[type=submit]'); btn.disabled = true; btn.classList.add('opacity-50', 'cursor-not-allowed'); btn.innerHTML = 'Updating...';">
                <div>
                    <label class="block text-sm font-medium text-gray-400 mb-1">Role Title</label>
                    <input name="role_title" value="{html.escape(exp.get('role_title', ''))}" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">Start Month</label>
                        <input name="start_month" value="{html.escape(str(exp.get('start_month', '')))}" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">Start Year</label>
                        <input name="start_year" value="{html.escape(str(exp.get('start_year', '')))}" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">End Month</label>
                        <input name="end_month" value="{html.escape(str(exp.get('end_month') or ''))}" placeholder="Present" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">End Year</label>
                        <input name="end_year" value="{html.escape(str(exp.get('end_year') or ''))}" placeholder="Present" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                </div>
                
                <div>
                    <label class="block text-sm font-medium text-gray-400 mb-1">Description (Max {limit} chars)</label>
                    <textarea name="description" rows="4" maxlength="{limit}" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">{html.escape(exp.get('description', ''))}</textarea>
                </div>
                
                <div class="flex gap-4 pt-4">
                    <button type="submit" class="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg font-semibold transition-all transform hover:scale-[1.02]">Update</button>
                    <a href="/dashboard" class="px-6 py-3 rounded-lg font-medium text-gray-400 hover:text-white hover:bg-gray-800 transition-colors flex items-center justify-center">Cancel</a>
                </div>
            </form>
        </div>
    </div>
    """
    return wrap_page("Edit Experience", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", ""), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/edit_accepted/<exp_id>", methods=["GET", "POST"])
def edit_accepted(exp_id):
    if "user_id" not in session:
        return redirect(f"/login?redirect_to={quote(request.full_path)}")
    user_id = session["user_id"]
    discord_token = session['discord_token']
    exp = db.reference(f"Experiences/{exp_id}").get()
    if not exp or exp.get("status") != "approved":
        return error_page("Not found or not approved", 404)
    server_id = exp["server_id"]
    role = get_user_role_in_server(user_id, server_id, discord_token)
    if role not in ["Server Owner", "Administrator"]:
        return error_page("Not authorized", 403)
    if role == "Administrator":
        exp_user_role = get_user_role_in_server(exp['user_id'], server_id, discord_token)
        if exp_user_role in ["Server Owner", "Administrator"] or exp['user_id'] == user_id:
            return error_page("Cannot edit this experience", 403)
            
    exp_user_id = str(exp["user_id"])
    user_data = get_user_data(exp_user_id)
    is_premium = user_data.get("premium", False)
    limit = DESC_LIMIT_PREMIUM if is_premium else DESC_LIMIT_FREE

    if request.method == "POST":
        # Validation
        start_month = request.form.get("start_month")
        start_year = request.form.get("start_year")
        end_month = request.form.get("end_month")
        end_year = request.form.get("end_year")
        
        try:
            sm = int(start_month)
            sy = int(start_year)
            if end_month and end_year:
                em = int(end_month)
                ey = int(end_year)
                if ey < sy or (ey == sy and em < sm):
                    return error_page("End date cannot be before start date.", 400)
        except ValueError:
            return error_page("Invalid date format.", 400)

        description = request.form.get("description")
        if description and len(description) > limit:
             return error_page(f"Description exceeds limit of {limit} characters.", 400)

        updates = {}
        for field in ["role_title", "start_month", "start_year", "end_month", "end_year", "description"]:
            val = request.form.get(field)
            if val or field in ["end_month", "end_year", "description"]:  # allow empty for end and description
                updates[field] = val if val else None
        db.reference(f"Experiences/{exp_id}").update(updates)
        return redirect(f"/view/{server_id}")
    
    content = f"""
    <div class="max-w-2xl mx-auto">
        <div class="glass p-8 rounded-2xl">
            <h2 class="text-2xl font-semibold mb-6 text-white">Edit Accepted Experience</h2>
            <form method="post" class="space-y-4" onsubmit="const btn = this.querySelector('button[type=submit]'); btn.disabled = true; btn.classList.add('opacity-50', 'cursor-not-allowed'); btn.innerHTML = 'Updating...';">
                <div>
                    <label class="block text-sm font-medium text-gray-400 mb-1">Role Title</label>
                    <input name="role_title" value="{html.escape(exp.get('role_title', ''))}" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">Start Month</label>
                        <input name="start_month" value="{html.escape(str(exp.get('start_month', '')))}" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">Start Year</label>
                        <input name="start_year" value="{html.escape(str(exp.get('start_year', '')))}" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">End Month</label>
                        <input name="end_month" value="{html.escape(str(exp.get('end_month') or ''))}" placeholder="Present" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">End Year</label>
                        <input name="end_year" value="{html.escape(str(exp.get('end_year') or ''))}" placeholder="Present" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                </div>
                
                <div>
                    <label class="block text-sm font-medium text-gray-400 mb-1">Description (Max {limit} chars)</label>
                    <textarea name="description" rows="4" maxlength="{limit}" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">{html.escape(exp.get('description', ''))}</textarea>
                </div>
                
                <div class="flex gap-4 pt-4">
                    <button type="submit" class="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg font-semibold transition-all transform hover:scale-[1.02]">Update</button>
                    <a href="/view/{server_id}" class="px-6 py-3 rounded-lg font-medium text-gray-400 hover:text-white hover:bg-gray-800 transition-colors flex items-center justify-center">Cancel</a>
                </div>
            </form>
        </div>
    </div>
    """
    return wrap_page("Edit Accepted Experience", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", ""), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/end/<exp_id>", methods=["GET", "POST"])
def end(exp_id):
    exp = db.reference(f"Experiences/{exp_id}").get()
    if not exp or exp["user_id"] != session.get("user_id"):
        return error_page("Not authorized", 403)
    if request.method == "POST":
        end_month = request.form.get("end_month")
        end_year = request.form.get("end_year")
        
        if end_month and end_year:
            try:
                start_month = int(exp["start_month"])
                start_year = int(exp["start_year"])
                if int(end_year) < start_year or (int(end_year) == start_year and int(end_month) < start_month):
                     return error_page("End date cannot be before start date.", 400)
            except ValueError:
                return error_page("Invalid date format.", 400)

        update_experience_end_date(exp_id, end_month, end_year)
        return redirect("/dashboard")
    
    content = f"""
    <div class="max-w-md mx-auto">
        <div class="glass p-8 rounded-2xl">
            <h2 class="text-2xl font-semibold mb-6 text-white">Edit End Date</h2>
            <form method="post" class="space-y-4" onsubmit="const btn = this.querySelector('button[type=submit]'); btn.disabled = true; btn.classList.add('opacity-50', 'cursor-not-allowed'); btn.innerHTML = 'Updating...';">
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">End Month</label>
                        <input name="end_month" type="number" min="1" max="12" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-400 mb-1">End Year</label>
                        <input name="end_year" type="number" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500 transition-colors">
                    </div>
                </div>
                
                <div class="flex gap-4 pt-4">
                    <button type="submit" class="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg font-semibold transition-all transform hover:scale-[1.02]">Update</button>
                    <a href="/dashboard" class="px-6 py-3 rounded-lg font-medium text-gray-400 hover:text-white hover:bg-gray-800 transition-colors flex items-center justify-center">Cancel</a>
                </div>
            </form>
        </div>
    </div>
    """
    return wrap_page("Edit End Date", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", ""), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/delete/<exp_id>", methods=["POST"])
def delete(exp_id):
    if "user_id" not in session:
        return "Not logged in", 401
    user_id = session["user_id"]
    discord_token = session['discord_token']
    exp = db.reference(f"Experiences/{exp_id}").get()
    if not exp or exp.get("status") != "approved":
        return "Not found or not approved", 404
    
    # Allow if user is the creator OR Server Owner
    if str(exp.get("user_id")) != user_id:
        server_id = exp["server_id"]
        role = get_user_role_in_server(user_id, server_id, discord_token)
        if role != "Server Owner":
            return "Not authorized", 403

    reject_experience(exp_id)
    return "Deleted"

@dashboard.route("/delete_pending/<exp_id>", methods=["POST"])
def delete_pending(exp_id):
    if "user_id" not in session:
        return "Not logged in", 401
    user_id = session["user_id"]
    
    exp_ref = db.reference(f"Experiences/{exp_id}")
    exp = exp_ref.get()
    if not exp:
        return "Not found", 404
        
    if exp.get("status") != "pending":
        return "Not a pending request", 400
        
    # Allow if user is the creator
    if str(exp.get("user_id")) != user_id:
        return "Not authorized", 403
        
    exp_ref.delete()
    return "Deleted"

@dashboard.route("/u/<user_id>")
def public_timeline(user_id):
    # Check for vanity URL first
    if not user_id.isdigit():
        ref = db.reference("Dashboard Users")
        users = ref.order_by_child("vanity_url").equal_to(user_id).get()
        if users:
            user_id = list(users.keys())[0]
        else:
            return error_page("User not found", 404)

    experiences = get_user_experiences(user_id)
    # Sort: Pinned first, then by date (newest first)
    # Pinned (True) > Unpinned (False), so reverse=True puts Pinned first.
    experiences.sort(key=lambda x: (x.get('is_pinned', False), int(x["start_year"]), int(x["start_month"])), reverse=True)
    
    user_data = get_user_data(user_id)
    if not user_data:
        return error_page("User not found", 404)
    username = user_data.get("username", "Unknown User")
    avatar = user_data.get("avatar")
    avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png?size=128" if avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
    
    is_premium = user_data.get("premium", False)
    socials = user_data.get("socials", [])
    
    # Social Icons Mapping
    def get_social_icon(url):
        url = url.lower()
        if "twitter.com" in url or "x.com" in url:
            return '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>'
        elif "github.com" in url:
            return '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clip-rule="evenodd"/></svg>'
        elif "linkedin.com" in url:
            return '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" clip-rule="evenodd"/></svg>'
        elif "youtube.com" in url:
            return '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z" clip-rule="evenodd"/></svg>'
        else:
            return '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>'

    socials_html = ""
    if socials:
        socials_html = '<div class="flex flex-wrap justify-center gap-3 mb-6">'
        for link in socials:
            socials_html += f'<a href="{html.escape(link)}" target="_blank" class="p-2 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white rounded-full transition-colors">{get_social_icon(link)}</a>'
        socials_html += '</div>'

    content = f"""
    <div class="max-w-4xl mx-auto">
        <div class="glass p-8 rounded-2xl mb-8 text-center relative overflow-hidden">
            {f'<div class="absolute top-0 right-0 bg-yellow-500 text-black text-xs font-bold px-3 py-1 rounded-bl-lg">PREMIUM MEMBER</div>' if is_premium else ''}
            <img src="{avatar_url}" alt="{html.escape(username)}" class="w-32 h-32 rounded-full mx-auto mb-4 border-4 border-indigo-500/30 shadow-xl">
            <h1 class="text-3xl font-semibold mb-2 flex items-center justify-center gap-2">
                {html.escape(username)}
                {f'<span title="Verified Premium Member"><svg class="w-6 h-6 text-yellow-500" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></span>' if is_premium else ''}
            </h1>
            
            {socials_html}

            <div class="flex flex-wrap justify-center gap-6 text-sm text-gray-400 mb-6">
                User ID: {html.escape(user_id)}
            </div>
            <p class="text-gray-400 font-medium border-t border-gray-700 pt-6">User Experience Timeline</p>
        </div>
        
        <div class="space-y-6">
    """
    
    if not experiences:
        content += """
        <div class="glass p-8 rounded-xl text-center text-gray-400">
            No experiences found.
        </div>
        """
    else:
        for exp in experiences:
            end = f"{exp.get('end_month', '')}/{exp.get('end_year', '')}" if exp.get('end_month') else '<span class="text-green-400">Present</span>'
            is_pinned = exp.get('is_pinned', False)
            
            border_class = "border-yellow-500/50 shadow-[0_0_15px_rgba(234,179,8,0.1)]" if is_pinned else "hover:bg-white/5"
            pin_badge = '<div class="absolute top-0 right-0 bg-yellow-500 text-black text-[10px] font-bold px-2 py-0.5 rounded-bl-lg z-10">PINNED</div>' if is_pinned else '';
            
            content += f"""
            <div class="glass p-6 rounded-xl {border_class} transition-colors relative overflow-hidden group">
                {pin_badge}
                <div class="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-indigo-500 to-purple-500"></div>
                <div class="flex flex-col md:flex-row justify-between items-start gap-4">
                    <div class="flex-grow">
                        <h3 class="text-xl font-semibold text-white mb-1">{html.escape(exp['role_title'])}</h3>
                        <div class="text-indigo-400 font-medium mb-2">
                            <a href="/s/{exp['server_id']}" class="hover:underline" target="_blank">{html.escape(exp['server_name'])}</a>
                        </div>
                        <p class="text-gray-300 text-sm leading-relaxed mb-4">{html.escape(exp.get('description', ''))}</p>
                        <div class="flex items-center gap-2 text-xs text-gray-500">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                            Verified by <a href="/u/{exp.get('approved_by_slug') or exp['approved_by']}" target="_blank" class="hover:underline hover:text-indigo-400 transition-colors">{html.escape(exp['approved_by_name'])}</a>
                        </div>
                    </div>
                    <div class="text-right min-w-[100px]">
                        <div class="text-sm font-mono text-gray-400 bg-gray-800/50 px-3 py-1 rounded-full inline-block">
                            {exp['start_month']}/{exp['start_year']} - {end}
                        </div>
                    </div>
                </div>
            </div>
            """
            
    content += "</div></div>"
    
    return wrap_page(f"{username}'s Timeline", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", ""), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/s/<server_id>")
def public_server_profile(server_id):
    # Check for vanity URL
    if not server_id.isdigit():
        servers_ref = db.reference("Dashboard Servers")
        result = servers_ref.order_by_child("vanity_url").equal_to(server_id).get()
        if result:
            server_id = list(result.keys())[0]
        else:
            return error_page("Server not found", 404)

    # Fetch guild info using Bot Token
    r = requests_session.get(f"{API_BASE}/guilds/{server_id}", params={"with_counts": "true"}, headers={"Authorization": f"Bot {BOT_TOKEN}"})
    
    server_name = "Unknown Server"
    icon_url = "https://cdn.discordapp.com/embed/avatars/0.png"
    member_count = None
    created_at = "Unknown"
    description = None
    
    all_exp = get_all_experiences_for_server(server_id)
    
    if r.status_code == 200:
        guild = r.json()
        server_name = guild.get("name", "Unknown Server")
        icon = guild.get("icon")
        icon_url = f"https://cdn.discordapp.com/icons/{server_id}/{icon}.png?size=128" if icon else "https://cdn.discordapp.com/embed/avatars/0.png"
        member_count = guild.get("approximate_member_count", 0)
        description = guild.get("description")
    else:
        if not all_exp:
            return error_page("Server not found or bot not in server", 404)
        
        # Sort by requested_at to get latest info
        sorted_exp = sorted(all_exp, key=lambda x: x.get("requested_at", 0), reverse=True)
        latest = sorted_exp[0]
        server_name = latest.get("server_name", "Unknown Server")
        icon = latest.get("server_icon")
        if icon:
            icon_url = f"https://cdn.discordapp.com/icons/{server_id}/{icon}.png?size=128"

    # Calculate creation date from snowflake
    try:
        snowflake = int(server_id)
        timestamp = ((snowflake >> 22) + 1420070400000) / 1000
        created_at = datetime.fromtimestamp(timestamp).strftime("%B %d, %Y")
    except:
        pass

    approved_list = [exp for exp in all_exp if exp.get("status") == "approved"]
    approved_list.sort(key=lambda x: (int(x["start_year"]), int(x["start_month"])), reverse=True)

    member_count_html = ""
    if member_count is not None:
        member_count_html = f"""
                <div class="flex items-center gap-2 bg-gray-800/50 px-3 py-1 rounded-full">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                    <span>{member_count:,} Members</span>
                </div>
        """

    content = f"""
    <div class="max-w-4xl mx-auto">
        <div class="glass p-8 rounded-2xl mb-8 text-center">
            <img src="{icon_url}" alt="{html.escape(server_name)}" class="w-32 h-32 rounded-full mx-auto mb-4 border-4 border-indigo-500/30 shadow-xl">
            <h1 class="text-3xl font-semibold mb-2">{html.escape(server_name)}</h1>
            
            <div class="flex flex-wrap justify-center gap-6 text-sm text-gray-400 mb-6">
                Server ID: {server_id}
            </div>
            
            <div class="flex flex-wrap justify-center gap-6 text-sm text-gray-400 mb-6">
                {member_count_html}
                <div class="flex items-center gap-2 bg-gray-800/50 px-3 py-1 rounded-full">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                    <span>Created {created_at}</span>
                </div>
            </div>
            
            {f'<p class="text-gray-300 max-w-2xl mx-auto mb-6 leading-relaxed">{html.escape(description)}</p>' if description else ''}
            
            <p class="text-gray-400 font-medium border-t border-gray-700 pt-6">Server Experience Registry</p>
        </div>
        
        <div class="space-y-6">
    """
    
    if not approved_list:
        content += """
        <div class="glass p-8 rounded-xl text-center text-gray-400">
            No experiences found for this server.
        </div>
        """
    else:
        for exp in approved_list:
            end = f"{exp.get('end_month')}/{exp.get('end_year')}" if exp.get('end_month') else '<span class="text-green-400">Present</span>'
            
            approver_name = exp.get('approver_name') or 'Unknown';
            
            content += f"""
            <div class="glass p-6 rounded-xl hover:bg-white/5 transition-colors relative overflow-hidden group">
                <div class="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-indigo-500 to-purple-500"></div>
                <div class="flex flex-col md:flex-row justify-between items-start gap-4">
                    <div class="flex-grow">
                        <h3 class="text-xl font-semibold text-white mb-1">{html.escape(exp['role_title'])}</h3>
                        <div class="text-indigo-400 font-medium mb-2">
                            <a href="/u/{exp.get('user_slug') or exp['user_id']}" class="hover:underline" target="_blank">{html.escape(exp['user_name'])}</a>
                        </div>
                        <p class="text-gray-300 text-sm leading-relaxed mb-4">{html.escape(exp.get('description', ''))}</p>
                        <div class="flex items-center gap-2 text-xs text-gray-500">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                            Verified by <a href="/u/{exp.get('approver_slug') or exp.get('approved_by')}" target="_blank" class="hover:underline hover:text-indigo-400 transition-colors">{html.escape(approver_name)}</a>
                        </div>
                    </div>
                    <div class="text-right min-w-[100px]">
                        <div class="text-sm font-mono text-gray-400 bg-gray-800/50 px-3 py-1 rounded-full inline-block">
                            {exp['start_month']}/{exp['start_year']} - {end}
                        </div>
                    </div>
                </div>
            </div>
            """
            
    content += "</div></div>"
    
    return wrap_page(f"{server_name} - Server Profile", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", ""), ("/premium", "Premium", ""), ("/logout", "Logout", "")])

@dashboard.route("/payment/activate", methods=["POST"])
def activate_premium():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
        
    data = request.get_json()
    user_id = data.get("user_id")
    order_id = data.get("order_id")
    
    if session["user_id"] != user_id:
        return jsonify({"error": "Unauthorized"}), 403
        
    try:
        # Update user premium status
        ref = db.reference(f"Dashboard Users/{user_id}")
        ref.update({
            "premium": True,
            "premium_since": int(time()),
            "paypal_order_id": order_id,
            "payment_details": data.get("payment_details")
        })
        return jsonify({"success": True})
    except Exception as e:
        print(f"Payment activation error: {e}")
        return jsonify({"error": str(e)}), 500

@dashboard.route("/premium")
def premium_page():
    if "user_id" not in session:
        return redirect(f"/login?redirect_to={quote(request.full_path)}")
    
    user_id = session["user_id"]
    user_data = get_user_data(user_id)
    is_premium = user_data.get('premium', False)
    premium_price = PREMIUM_ONE_TIME_PRICE
    
    content = f"""
    <div class="max-w-4xl mx-auto">
        <div class="text-center mb-12">
            <h1 class="text-4xl font-bold text-white mb-4">Choose Your Plan</h1>
            <p class="text-xl text-gray-400">Unlock the full potential of ServerCV while supporting its development. Thank you for your support!</p>
        </div>

        <div class="grid md:grid-cols-2 gap-8">
            <!-- Free Plan -->
            <div class="glass p-8 rounded-2xl border-2 border-gray-700 flex flex-col">
                <div class="mb-8">
                    <h2 class="text-2xl font-semibold text-white mb-2">Free</h2>
                    <div class="text-4xl font-bold text-white">$0</div>
                    <div class="text-gray-400">Forever</div>
                </div>
                <ul class="space-y-4 mb-8 flex-1">
                    <li class="flex items-center text-gray-300">
                        <svg class="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        Up to {EXP_LIMIT_FREE} Experiences
                    </li>
                    <li class="flex items-center text-gray-300">
                        <svg class="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        Basic User and Server Profiles
                    </li>
                    <li class="flex items-center text-gray-300">
                        <svg class="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        {DESC_LIMIT_FREE:,} Character Description Limit
                    </li>
                    <li class="flex items-center text-gray-300">
                        <svg class="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        {SOCIAL_LIMIT_FREE} Social Links
                    </li>
                </ul>
                <div class="mt-auto">
                    <button class="w-full bg-gray-700 text-gray-300 font-semibold py-3 px-6 rounded-lg cursor-default">Current Plan</button>
                </div>
            </div>

            <!-- Premium Plan -->
            <div class="glass p-8 rounded-2xl border-2 border-indigo-500 relative flex flex-col">
                <div class="absolute top-0 right-0 bg-indigo-500 text-white text-xs font-bold px-3 py-1 rounded-bl-lg rounded-tr-lg">RECOMMENDED</div>
                <div class="mb-8">
                    <h2 class="text-2xl font-semibold text-white mb-2">Premium <span title="Verified Premium Member"><svg class="w-6 h-6 text-yellow-500 inline-block align-text-bottom" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></span></h2>
                    <div class="text-4xl font-bold text-white">${premium_price}</div>
                    <div class="text-indigo-300">One-time Purchase <small class="text-gray-400"> (in USD)</small></div>
                </div>
                <ul class="space-y-4 mb-8 flex-1">
                    <li class="flex items-center text-white">
                        <svg class="w-5 h-5 text-indigo-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        Unlimited Experiences
                    </li>
                    <li class="flex items-center text-white">
                        <svg class="w-5 h-5 text-indigo-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        User Vanity URL
                    </li>
                    <li class="flex items-center text-white">
                        <svg class="w-5 h-5 text-indigo-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        Premium Profile Badge
                    </li>
                    <li class="flex items-center text-white">
                        <svg class="w-5 h-5 text-indigo-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        Pin Experiences
                    </li>
                    <li class="flex items-center text-white">
                        <svg class="w-5 h-5 text-indigo-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        {DESC_LIMIT_PREMIUM:,} Character Description Limit
                    </li>
                    <li class="flex items-center text-white">
                        <svg class="w-5 h-5 text-indigo-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        {SOCIAL_LIMIT_PREMIUM} Social Links
                    </li>
                    <li class="flex items-center text-white">
                        <svg class="w-5 h-5 text-indigo-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                        Server Vanity URL for servers you own
                    </li>
                </ul>
                <div class="mt-auto" id="paypal-button-container">
                    <!-- PayPal Button will be rendered here -->
                </div>
            </div>
        </div>
    </div>

    <script src="https://www.paypal.com/sdk/js?client-id={PAYPAL_CLIENT_ID}&intent=capture&enable-funding=venmo&currency=USD"></script>
    <script>
        const isPremium = {str(is_premium).lower()};
        
        if (isPremium) {{
            document.getElementById('paypal-button-container').innerHTML = '<div class="w-full bg-green-600 text-white font-semibold py-3 px-6 rounded-lg text-center">Plan Active</div>';
        }} else {{
            paypal.Buttons({{
                createOrder: function(data, actions) {{
                    return actions.order.create({{
                        purchase_units: [{{
                            amount: {{ value: '{premium_price}', currency_code: 'USD' }},
                            description: 'Premium Access for ServerCV',
                            custom_id: '{user_id}'
                        }}],
                        application_context: {{ shipping_preference: 'NO_SHIPPING' }}
                    }});
                }},
                onApprove: function(data, actions) {{
                    return actions.order.capture().then(function(details) {{
                        document.getElementById('paypal-button-container').innerHTML = '<div class="text-center text-white">Processing payment...</div>';
                        return fetch('/payment/activate', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ user_id: "{user_id}", order_id: data.orderID, payment_details: details }})
                        }}).then(response => {{
                            if (response.ok) window.location.href = '/dashboard';
                            else alert('Payment processed but activation failed. Contact support.');
                        }});
                    }});
                }},
                onError: function(err) {{
                    console.error('PayPal button error:', err);
                    alert('Payment system error. Please refresh the page and try again.');
                }},
                style: {{ layout: 'vertical', color: 'blue', shape: 'rect', label: 'paypal', height: 40 }}
            }}).render('#paypal-button-container');
        }}
    </script>
    """
    
    return wrap_page("Premium", content, nav_links=[("/dashboard", "Dashboard", ""), ("/settings", "Settings", ""), ("/premium", "Premium", "text-white bg-gray-800"), ("/logout", "Logout", "")])

