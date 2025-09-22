from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, Response
import sqlite3
import hashlib
import requests
import time
import os
import uuid
from werkzeug.utils import secure_filename
from datetime import datetime
from pathlib import Path
import json
import threading
import cv2

# ------------------------ APP CONFIG ------------------------ #
app = Flask(__name__)
app.secret_key = "supersecretkey"

CATEGORIES = ["phone", "wallet", "umbrella", "calculator", "random"]
DB_FILE = "lost_found.db"
BLYNK_TOKEN = "XzczQjXJGQgSem7wbhzu4_JYFcTpogpf"

# ------------------------ CLAIMS CONFIG ------------------------ #
UPLOAD_FOLDER = Path.cwd() / "claims"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024
DATA_FILE = Path.cwd() / "claims.json"

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# ------------------------ CLAIMS STORAGE ------------------------ #
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_claims():
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []

def save_claims():
    with open(DATA_FILE, 'w') as f:
        json.dump(claims_storage, f, indent=2)

claims_storage = load_claims()

# Prevent duplicate uploads
uploaded_hashes = set()
for claim in claims_storage:
    for img_path in claim.get('images', []):
        img_file = os.path.join(app.config['UPLOAD_FOLDER'], img_path)
        if os.path.exists(img_file):
            with open(img_file, 'rb') as f:
                uploaded_hashes.add(hashlib.md5(f.read()).hexdigest())

def file_hash(file) -> str:
    file.seek(0)
    h = hashlib.md5(file.read()).hexdigest()
    file.seek(0)
    return h

# ------------------------ DATABASE INIT ------------------------ #
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # Students
        c.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tcc_number TEXT UNIQUE,
                name TEXT
            )
        """)
        # Admin users
        c.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT
            )
        """)
        # CSU users
        c.execute("""
            CREATE TABLE IF NOT EXISTS csu_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT
            )
        """)
        # Staff users
        c.execute("""
            CREATE TABLE IF NOT EXISTS staff_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tcc_number TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            )
        """)
        # Reports
        c.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tcc_number TEXT,
                report_type TEXT,
                category TEXT,
                description TEXT,
                user_type TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

# ------------------------ HELPERS ------------------------ #
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def verify_user(table, username, password):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(f"SELECT password_hash FROM {table} WHERE username=?", (username,))
        row = c.fetchone()
        return row and row[0] == hash_password(password)

def is_registered(tcc):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM students WHERE tcc_number=?", (tcc,))
        return c.fetchone() is not None

def is_registered_staff(tcc):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM staff_users WHERE tcc_number=?", (tcc,))
        return c.fetchone() is not None

def control_servo(category, action):
    mapping = {"phone":1,"wallet":2,"umbrella":3,"calculator":4,"random":5}
    vpin = mapping.get(category)
    if not vpin:
        return False, "Invalid category"
    value = 1 if action=="on" else 0
    url = f"https://blynk.cloud/external/api/update?token={BLYNK_TOKEN}&V{vpin}={value}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return True, f"Servo {action} for {category}"
        else:
            return False, f"Blynk error: {r.text}"
    except Exception as e:
        return False, str(e)

# ------------------------ ROUTES ------------------------ #
@app.route("/")
def home():
    return redirect(url_for("submit_report"))

@app.route("/submit_report", methods=["GET","POST"])
def submit_report():
    if request.method=="POST":
        data = request.get_json()
        if not data:
            return jsonify({"status":"error","message":"No data received"}), 400

        user_type = data.get("user_type")
        tcc = data.get("tcc_number")
        rtype = data.get("report_type")
        category = data.get("category")
        desc = data.get("description","")

        if not user_type or not tcc:
            return jsonify({"status":"error","message":"Missing user type or TCC"}), 400

        if user_type == "student":
            if not is_registered(tcc):
                return jsonify({"status":"error","message":"Student TCC not registered"}), 403
        elif user_type == "staff":
            if not is_registered_staff(tcc):
                return jsonify({"status":"error","message":"Staff TCC not registered"}), 403
        else:
            return jsonify({"status":"error","message":"Invalid user type"}), 400

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO reports (tcc_number, report_type, category, description, user_type)
                VALUES (?,?,?,?,?)
            """, (tcc, rtype, category, desc, user_type))
            conn.commit()

        if rtype=="found":
            ok,msg = control_servo(category,"off")
            if not ok:
                return jsonify({"status":"error","message":msg}),500
            time.sleep(10)
            control_servo(category,"on")

        return jsonify({"status":"success","message":"Report submitted successfully."})

    return render_template("submit_report.html", categories=CATEGORIES)

# ------------------------ ADMIN ROUTES ------------------------ #
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if verify_user("admin_users", u, p):
            session["admin_user"] = u
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Invalid credentials")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_user", None)
    return redirect(url_for("admin_login"))

@app.route("/admin/dashboard")
def admin_dashboard():
    if "admin_user" not in session:
        return redirect(url_for("admin_login"))

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM students ORDER BY id DESC")
        students = c.fetchall()
        c.execute("""
            SELECT reports.id, reports.tcc_number, reports.user_type, 
                   reports.report_type, reports.category, reports.description, reports.timestamp
            FROM reports
            ORDER BY reports.timestamp DESC
        """)
        reports = c.fetchall()
        c.execute("SELECT * FROM staff_users ORDER BY id DESC")
        staff = c.fetchall()

    return render_template("admin_dashboard.html", students=students, reports=reports, staff=staff)

@app.route("/admin/register_student", methods=["POST"])
def admin_register_student():
    if "admin_user" not in session:
        return redirect(url_for("admin_login"))
    tcc = request.form.get("tcc_number")
    name = request.form.get("name")
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO students (tcc_number, name) VALUES (?,?)", (tcc, name))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete_student/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if "admin_user" not in session:
        return redirect(url_for("admin_login"))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM students WHERE id=?", (student_id,))
        conn.commit()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete_report/<int:report_id>", methods=["POST"])
def delete_report(report_id):
    if "admin_user" not in session:
        return redirect(url_for("admin_login"))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM reports WHERE id=?", (report_id,))
        conn.commit()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete_all_reports/<report_type>", methods=["POST"])
def delete_all_reports(report_type):
    if "admin_user" not in session:
        return redirect(url_for("admin_login"))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM reports WHERE report_type=?", (report_type,))
        conn.commit()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/register_staff_user", methods=["POST"])
def admin_register_staff_user():
    if "admin_user" not in session:
        return redirect(url_for("admin_login"))
    tcc_number = request.form.get("tcc_number")
    name = request.form.get("name")
    if not tcc_number or not name:
        flash("Both TCC number and name are required", "error")
        return redirect(url_for("admin_dashboard"))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO staff_users (tcc_number, name) VALUES (?,?)", (tcc_number, name))
            conn.commit()
            flash("Staff user registered successfully", "success")
        except sqlite3.IntegrityError:
            flash("TCC number already exists", "error")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete_staff_user/<int:staff_id>", methods=["POST"])
def delete_staff_user(staff_id):
    if "admin_user" not in session:
        return redirect(url_for("admin_login"))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM staff_users WHERE id=?", (staff_id,))
        conn.commit()
    flash("Staff user deleted")
    return redirect(url_for("admin_dashboard"))

# ------------------------ CSU ROUTES ------------------------ #
@app.route("/csu/login", methods=["GET","POST"])
def csu_login():
    if request.method=="POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if verify_user("csu_users", u, p):
            session["csu_user"] = u
            return redirect(url_for("csu_control"))
        return render_template("csu_login.html", error="Invalid credentials")
    return render_template("csu_login.html")

@app.route("/csu/logout")
def csu_logout():
    session.pop("csu_user", None)
    return redirect(url_for("csu_login"))

# ------------------------ DYNAMIC IP CAMERA CONFIG ------------------------ #
IP_CAMERA_URL = "http://192.168.1.7:8080/video"  # default value
IP_FILE = Path("ipcam.json")

def load_ip():
    global IP_CAMERA_URL
    if IP_FILE.exists():
        with open(IP_FILE, 'r') as f:
            data = json.load(f)
            IP_CAMERA_URL = data.get("ip", IP_CAMERA_URL)

def save_ip(new_ip):
    global IP_CAMERA_URL
    IP_CAMERA_URL = new_ip
    with open(IP_FILE, 'w') as f:
        json.dump({"ip": new_ip}, f)

load_ip()

@app.route("/csu/set_ip", methods=["POST"])
def set_ip():
    if "csu_user" not in session:
        return redirect(url_for("csu_login"))

    new_ip = request.form.get("ip_address")
    if new_ip:
        save_ip(new_ip)
        flash(f"IP Camera updated to {new_ip}", "success")
    else:
        flash("Invalid IP", "error")
    return redirect(url_for("csu_control"))

@app.route("/csu/control_led", methods=["GET", "POST"])
def csu_control():
    if "csu_user" not in session:
        return redirect(url_for("csu_login"))

    msg = ""
    if request.method == "POST":
        action = request.form.get("action")  # on/off
        category = request.form.get("category")
        if action not in ("on", "off") or not category:
            msg = "Invalid action or category"
        else:
            ok, msg = control_servo(category, action)

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT id, category, description
            FROM reports
            WHERE report_type = 'found'
        """)
        found_items = c.fetchall()
    # ------------------------------------------------------------

    return render_template(
        "csu_control.html",
        message=msg,
        categories=CATEGORIES,
        claims=claims_storage,
        ip_camera_url=IP_CAMERA_URL,
        found_items=found_items
    )

# ------------------------ CLAIMS UPLOAD ------------------------ #
@app.route("/upload", methods=["POST"])
def upload():
    tcc = request.form.get("tcc", "").strip()
    found_item_id = request.form.get("found_item_id")  # <-- get the selected found item id
    uploaded_files = request.files.getlist('images')
    if not tcc:
        flash("TCC Number is required")
        return redirect(url_for('csu_control'))

    if not (is_registered(tcc) or is_registered_staff(tcc)):
        flash("TCC not registered as student or staff")
        return redirect(url_for('csu_control'))

    # --- Get found item details from DB ---
    found_item_info = None
    if found_item_id:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT id, category, description FROM reports WHERE id=? AND report_type='found'",
                (found_item_id,)
            )
            found_item_info = c.fetchone()
            # --- Delete the found item after fetching its info ---
            c.execute(
                "DELETE FROM reports WHERE id=? AND report_type='found'",
                (found_item_id,)
            )
            conn.commit()
    # --------------------------------------

    existing_claim = next((c for c in claims_storage if c['tcc']==tcc), None)
    new_images = []
    for file in uploaded_files:
        if file and allowed_file(file.filename):
            h = file_hash(file)
            if h in uploaded_hashes:
                continue
            filename = secure_filename(file.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            dest = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
            file.save(dest)
            uploaded_hashes.add(h)
            new_images.append(unique_name)
    if not new_images and existing_claim:
        flash("No new images to add (duplicate detected).")
        return redirect(url_for('csu_control'))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if existing_claim:
        existing_claim['images'].extend(new_images)
        existing_claim['timestamp'] = timestamp
        if found_item_info:
            existing_claim['found_item'] = {
                "id": found_item_info["id"],
                "category": found_item_info["category"],
                "description": found_item_info["description"]
            }
        flash("Claim updated successfully")
    else:
        claim_data = {
            "tcc": tcc,
            "images": new_images,
            "timestamp": timestamp
        }
        if found_item_info:
            claim_data["found_item"] = {
                "id": found_item_info["id"],
                "category": found_item_info["category"],
                "description": found_item_info["description"]
            }
        claims_storage.append(claim_data)
        flash("Claim submitted successfully")
    save_claims()
    return redirect(url_for('csu_control'))

@app.route('/claims/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete', methods=['POST'])
def delete():
    tcc = request.form.get('tcc')
    claim_to_delete = next((c for c in claims_storage if c['tcc']==tcc), None)
    if claim_to_delete:
        for img in claim_to_delete.get('images', []):
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], img)
            if os.path.exists(img_path):
                with open(img_path,'rb') as f:
                    uploaded_hashes.discard(hashlib.md5(f.read()).hexdigest())
                os.remove(img_path)
        claims_storage.remove(claim_to_delete)
        flash('Claim deleted')
        save_claims()
    else:
        flash('Claim not found')
    return redirect(url_for('csu_control'))

# ------------------------ IP CAMERA ------------------------ #
latest_frame = None

def update_frames():
    global latest_frame
    while True:
        cap = cv2.VideoCapture(IP_CAMERA_URL)
        ret, frame = cap.read()
        if ret:
            _, buffer = cv2.imencode('.jpg', frame)
            latest_frame = buffer.tobytes()
        cap.release()
        time.sleep(0.05)

# Start background thread
threading.Thread(target=update_frames, daemon=True).start()

def gen_frames():
    global latest_frame
    while True:
        if latest_frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        else:
            time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/capture_image')
def capture_image():
    if latest_frame:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"capture_{now}.jpg"
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(path, 'wb') as f:
            f.write(latest_frame)
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    return "No frame captured yet", 404

# ------------------------ API FOR APP ------------------------ #
@app.route("/found-items", methods=["GET"])
def get_found_items():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, tcc_number, category, description
        FROM reports
        WHERE report_type = 'found'
    """)
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route("/lost-items", methods=["GET"])
def get_lost_items():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, tcc_number, category, description
        FROM reports
        WHERE report_type = 'lost'
    """)
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route("/claims", methods=["GET"])
def get_claims():
    return jsonify(claims_storage)
# ------------------------ INIT DB ------------------------ #
def seed_admin():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM admin_users LIMIT 1")
        if not c.fetchone():
            c.execute(
                "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
                ("admin", hash_password("admin123"))
            )
            conn.commit()
def seed_csu():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM csu_users LIMIT 1")
        if not c.fetchone():
            c.execute(
                "INSERT INTO csu_users (username, password_hash) VALUES (?, ?)",
                ("csu", hash_password("csu123"))
            )
            conn.commit()

init_db()
seed_admin()
seed_csu()
# ------------------------ MAIN ------------------------ #
if __name__=="__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
