import os, re, uuid, sqlite3, secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "gdrfad.sqlite3"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED = {"pdf", "png", "jpg", "jpeg"}
MAX_UPLOAD = 8 * 1024 * 1024

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "CHANGE-ME-before-deployment-" + secrets.token_hex(16)),
    MAX_CONTENT_LENGTH=MAX_UPLOAD,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Set COOKIE_SECURE=1 behind HTTPS in production.
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
)

STATUSES = ["Pending", "Under Review", "Approved", "Rejected"]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'customer',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            service TEXT NOT NULL, full_name TEXT NOT NULL,
            nationality TEXT NOT NULL, passport_number TEXT NOT NULL,
            date_of_birth TEXT NOT NULL, email TEXT NOT NULL,
            phone TEXT NOT NULL, travel_date TEXT NOT NULL,
            notes TEXT, passport_file TEXT NOT NULL, photo_file TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            authority_verified INTEGER NOT NULL DEFAULT 0,
            visa_pdf TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL REFERENCES applications(id),
            amount REAL NOT NULL, currency TEXT NOT NULL,
            method TEXT NOT NULL, transaction_ref TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            receipt_file TEXT, created_at TEXT NOT NULL
        );
        """)
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@gdrfad.local").lower()
        admin_password = os.environ.get("ADMIN_PASSWORD", "ChangeThisAdmin123!")
        exists = c.execute("SELECT id FROM users WHERE email=?", (admin_email,)).fetchone()
        if not exists:
            c.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                      ("GDRFAD Administrator", admin_email, generate_password_hash(admin_password),
                       "admin", datetime.now(timezone.utc).isoformat()))

def logged_in():
    return session.get("user_id") is not None

def current_user():
    if not logged_in(): return None
    with db() as c:
        return c.execute("SELECT id,name,email,role FROM users WHERE id=?", (session["user_id"],)).fetchone()

def login_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not logged_in():
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        u = current_user()
        if not u or u["role"] != "admin":
            abort(403)
        return fn(*a, **kw)
    return wrapped

def save_upload(field, prefix):
    f = request.files.get(field)
    if not f or not f.filename:
        raise ValueError(f"{field.replace('_',' ').title()} is required.")
    original = secure_filename(f.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED:
        raise ValueError("Only PDF, JPG, JPEG and PNG files are accepted.")
    # Random stored name; never expose original filenames.
    name = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    f.save(UPLOAD_DIR / name)
    return name

@app.context_processor
def inject_globals():
    return {"user": current_user(), "year": datetime.now().year}

@app.get("/")
def home():
    return render_template("home.html")

@app.get("/services")
def services():
    return render_template("services.html")

@app.get("/services/<slug>")
def service_detail(slug):
    names = {"tourist-visa":"Tourist Visa", "transit-visa":"Transit Visa", "visit-visa":"Visit Visa"}
    if slug not in names: abort(404)
    return render_template("service_detail.html", service=names[slug])

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name=request.form.get("name","").strip()
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        if not name or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) or len(password)<10:
            flash("Enter a name, valid email and password of at least 10 characters.", "danger")
        else:
            try:
                with db() as c:
                    c.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                              (name,email,generate_password_hash(password),datetime.now(timezone.utc).isoformat()))
                flash("Account created. Please sign in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "danger")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        with db() as c:
            u=c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u and check_password_hash(u["password_hash"],password):
            session.clear()
            session["user_id"]=u["id"]
            return redirect(url_for("admin_dashboard" if u["role"]=="admin" else "dashboard"))
        flash("Email or password is incorrect.", "danger")
    return render_template("auth.html", mode="login")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/apply", methods=["GET","POST"])
@login_required
def apply():
    if request.method=="POST":
        try:
            fields = {k:request.form.get(k,"").strip() for k in
                      ["service","full_name","nationality","passport_number","date_of_birth","email","phone","travel_date","notes"]}
            required=["service","full_name","nationality","passport_number","date_of_birth","email","phone","travel_date"]
            if any(not fields[k] for k in required):
                raise ValueError("Please complete all required fields.")
            if not request.form.get("privacy_consent"):
                raise ValueError("Please confirm that you agree to the privacy notice.")
            passport=save_upload("passport_file","passport")
            try: photo=save_upload("photo_file","photo")
            except Exception:
                (UPLOAD_DIR/passport).unlink(missing_ok=True)
                raise
            ref="GF-" + datetime.now().strftime("%y%m%d") + "-" + secrets.token_hex(3).upper()
            now=datetime.now(timezone.utc).isoformat()
            with db() as c:
                c.execute("""INSERT INTO applications(reference,user_id,service,full_name,nationality,passport_number,
                date_of_birth,email,phone,travel_date,notes,passport_file,photo_file,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ref,session["user_id"],fields["service"],fields["full_name"],fields["nationality"],
                 fields["passport_number"],fields["date_of_birth"],fields["email"],fields["phone"],
                 fields["travel_date"],fields["notes"],passport,photo,"Pending",now,now))
            flash(f"Application submitted. Your reference is {ref}.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as e:
            flash(str(e),"danger")
        except Exception:
            flash("We could not submit the application. Please check your files and try again.","danger")
    return render_template("apply.html")

@app.get("/dashboard")
@login_required
def dashboard():
    with db() as c:
        apps=c.execute("SELECT * FROM applications WHERE user_id=? ORDER BY id DESC",(session["user_id"],)).fetchall()
    return render_template("dashboard.html", applications=apps)

@app.route("/track", methods=["GET","POST"])
def track():
    result=None
    if request.method=="POST":
        ref=request.form.get("reference","").strip().upper()
        with db() as c:
            result=c.execute("SELECT reference,service,status,created_at,updated_at FROM applications WHERE reference=?",(ref,)).fetchone()
        if not result: flash("No application found for that reference number.","warning")
    return render_template("track.html", result=result)

@app.get("/admin")
@login_required
@admin_required
def admin_dashboard():
    with db() as c:
        apps=c.execute("""SELECT a.*,u.name AS customer_name FROM applications a
        JOIN users u ON u.id=a.user_id ORDER BY a.id DESC""").fetchall()
        payments=c.execute("""SELECT p.*,a.reference FROM payments p JOIN applications a ON a.id=p.application_id
        ORDER BY p.id DESC""").fetchall()
    return render_template("admin.html", applications=apps, payments=payments, statuses=STATUSES)

@app.post("/admin/application/<int:app_id>/status")
@login_required
@admin_required
def update_status(app_id):
    status=request.form.get("status")
    if status not in STATUSES: abort(400)
    with db() as c:
        c.execute("UPDATE applications SET status=?,updated_at=? WHERE id=?",
                  (status,datetime.now(timezone.utc).isoformat(),app_id))
    flash("Application status updated.","success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/application/<int:app_id>/visa")
@login_required
@admin_required
def upload_visa(app_id):
    if not request.form.get("authority_verified"):
        flash("Confirm that the PDF was issued by the relevant official authority.","danger")
        return redirect(url_for("admin_dashboard"))
    f=request.files.get("visa_pdf")
    if not f or not f.filename or not f.filename.lower().endswith(".pdf"):
        flash("Upload the authority-issued PDF file.","danger")
        return redirect(url_for("admin_dashboard"))
    name=f"visa_{uuid.uuid4().hex}.pdf"
    f.save(UPLOAD_DIR/name)
    with db() as c:
        c.execute("UPDATE applications SET visa_pdf=?,authority_verified=1,updated_at=? WHERE id=?",
                  (name,datetime.now(timezone.utc).isoformat(),app_id))
    flash("Authority-issued visa PDF added to the customer's account.","success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/application/<int:app_id>/payment")
@login_required
@admin_required
def add_payment(app_id):
    try:
        amount=float(request.form.get("amount","0"))
        currency=request.form.get("currency","AED")
        method=request.form.get("method","Bank transfer")
        if amount<=0 or currency not in ("AED","PKR") or method not in ("Bank transfer","Cash","Card"):
            raise ValueError()
        with db() as c:
            c.execute("INSERT INTO payments(application_id,amount,currency,method,transaction_ref,status,created_at) VALUES(?,?,?,?,?,?,?)",
                      (app_id,amount,currency,method,request.form.get("transaction_ref","").strip(),"Pending",datetime.now(timezone.utc).isoformat()))
        flash("Payment record added.","success")
    except Exception:
        flash("Please enter a valid payment amount and method.","danger")
    return redirect(url_for("admin_dashboard"))

@app.get("/documents/<int:app_id>/<kind>")
@login_required
def customer_document(app_id,kind):
    with db() as c:
        a=c.execute("SELECT * FROM applications WHERE id=?",(app_id,)).fetchone()
    if not a: abort(404)
    u=current_user()
    if u["role"]!="admin" and a["user_id"]!=u["id"]: abort(403)
    mapping={"passport":a["passport_file"],"photo":a["photo_file"],"visa":a["visa_pdf"]}
    filename=mapping.get(kind)
    if not filename: abort(404)
    if kind=="visa" and not a["authority_verified"]: abort(403)
    return send_from_directory(UPLOAD_DIR,filename,as_attachment=True)

@app.get("/receipt/<int:payment_id>")
@login_required
def receipt(payment_id):
    with db() as c:
        p=c.execute("""SELECT p.*,a.user_id,a.reference FROM payments p JOIN applications a ON a.id=p.application_id
        WHERE p.id=?""",(payment_id,)).fetchone()
    if not p: abort(404)
    u=current_user()
    if u["role"]!="admin" and p["user_id"]!=u["id"]: abort(403)
    return render_template("receipt.html", payment=p)

@app.get("/about")
def about(): return render_template("about.html")
@app.get("/contact")
def contact(): return render_template("contact.html")

@app.errorhandler(403)
def forbidden(e): return render_template("error.html",code=403,message="You do not have permission to view this page."),403
@app.errorhandler(404)
def not_found(e): return render_template("error.html",code=404,message="The page could not be found."),404
@app.errorhandler(413)
def too_large(e): return render_template("error.html",code=413,message="Each upload must be 8 MB or smaller."),413

init_db()
if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG","0")=="1", host="0.0.0.0", port=int(os.environ.get("PORT","5000")))
