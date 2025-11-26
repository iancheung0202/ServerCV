import firebase_admin
import uuid
from time import time

from firebase_admin import credentials, db
from config.settings import FIREBASE_CRED, DATABASE_URL

cred = credentials.Certificate(FIREBASE_CRED)
default_app = firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})

def save_user_to_firebase(user, token):
    db.reference(f"Dashboard Users/{user['id']}").update({
        "username": user["username"],
        "avatar": user.get("avatar", ""),
        "discord_token": token
    })

def save_experience_request(user_id, server_id, server_name, role_title, start_month, start_year, end_month, end_year, description, requester_role, server_icon=None):
    exp_id = str(uuid.uuid4())
    data = {
        "user_id": user_id,
        "server_id": server_id,
        "server_name": server_name,
        "role_title": role_title,
        "start_month": start_month,
        "start_year": start_year,
        "end_month": end_month,
        "end_year": end_year,
        "description": description,
        "requester_role": requester_role,
        "status": "pending",
        "requested_at": time()
    }
    if server_icon:
        data["server_icon"] = server_icon
        
    db.reference(f"Experiences/{exp_id}").set(data)
    return exp_id

def approve_experience(exp_id, approved_by):
    db.reference(f"Experiences/{exp_id}").update({
        "approved_by": approved_by,
        "approved_at": time(),
        "status": "approved"
    })

def reject_experience(exp_id):
    db.reference(f"Experiences/{exp_id}").delete()

def get_user_info_short(user_id):
    if not user_id:
        return {"name": "", "slug": ""}
    user = db.reference(f"Dashboard Users/{user_id}").get()
    if not user:
        return {"name": user_id, "slug": user_id}
    
    name = user.get("username", user_id)
    slug = user.get("vanity_url") if user.get("premium", False) and user.get("vanity_url") else user_id
    return {"name": name, "slug": slug}

def get_username(user_id):
    return get_user_info_short(user_id)["name"]

def get_all_experiences_for_server(server_id):
    ref = db.reference("Experiences")
    experiences = ref.order_by_child("server_id").equal_to(server_id).get()
    all_exp = []
    if experiences:
        for k, exp in experiences.items():
            exp_copy = exp.copy()
            exp_copy["id"] = k
            
            user_info = get_user_info_short(exp["user_id"])
            exp_copy["user_name"] = user_info["name"]
            exp_copy["user_slug"] = user_info["slug"]
            
            if exp.get("approved_by"):
                approver_info = get_user_info_short(exp["approved_by"])
                exp_copy["approver_name"] = approver_info["name"]
                exp_copy["approver_slug"] = approver_info["slug"]
            else:
                exp_copy["approver_name"] = ""
                exp_copy["approver_slug"] = ""
                
            all_exp.append(exp_copy)
    return all_exp

def get_user_experiences(user_id):
    ref = db.reference("Experiences")
    experiences = ref.order_by_child("user_id").equal_to(user_id).get()
    approved = []
    if experiences:
        for k, exp in experiences.items():
            if exp.get("status") == "approved":
                exp_copy = exp.copy()
                exp_copy["id"] = k
                
                if exp.get("approved_by"):
                    approver_info = get_user_info_short(exp["approved_by"])
                    exp_copy["approved_by_name"] = approver_info["name"]
                    exp_copy["approved_by_slug"] = approver_info["slug"]
                else:
                    exp_copy["approved_by_name"] = "Unknown"
                    exp_copy["approved_by_slug"] = ""
                    
                approved.append(exp_copy)
    return approved

def update_experience_end_date(exp_id, end_month, end_year):
    db.reference(f"Experiences/{exp_id}").update({
        "end_month": end_month,
        "end_year": end_year
    })

def get_user_data(user_id):
    return db.reference(f"Dashboard Users/{user_id}").get()