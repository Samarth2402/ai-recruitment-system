from flask import Flask, render_template, request, redirect, session, send_from_directory,jsonify

import os, random, json

from ai_resume_analyzer import analyze_resume

from data_manager import read_json, write_json
from resume_parser import extract_text_from_pdf
from interview_engine import generate_questions, evaluate_answers
from datetime import datetime
import uuid
from skill_matcher import extract_skills_from_resume, calculate_match_score

app = Flask(__name__)
app.secret_key = "secret123"

# ================= CONFIG =================
#SMTP_EMAIL = "ss9879086402@gmail.com"
#SMTP_PASSWORD = "ojwsndwozpbrmcuk"
#SMTP_SERVER = "smtp.gmail.com"
#SMTP_PORT = 587
#SMTP_SERVER = os.environ.get("smtp.gmail.com")
#SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
#SMTP_EMAIL = os.environ.get("ss9879086402@gmail.com")
#SMTP_PASSWORD = os.environ.get("ojwsndwozpbrmcuk")

USERS_FILE = "data/users.json"
JOBS_FILE = "data/jobs.json"
APPLICATIONS_FILE = "data/applications.json"
OTP_FILE = "data/otp.json"
INTERVIEWS_FILE = "data/interviews.json"
SCHEDULE_FILE = "data/scheduled_interviews.json"
RESUME_FOLDER = "resumes"
RESUME_META_FILE = "data/resumes.json"
os.makedirs("data", exist_ok=True)
os.makedirs(RESUME_FOLDER, exist_ok=True)
APTITUDE_Q_FILE = "data/aptitude_questions.json"
APTITUDE_RESULT_FILE = "data/aptitude_results.json"

# ================= EMAIL HELPERS =================

# ================= AUTH =================

@app.route("/", methods=["GET", "POST"])
def login():
    users = read_json(USERS_FILE)

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        for u in users:
            if u["email"] == email and u["password"] == password:
                session["user"] = u
                return redirect("/dashboard")

        # ❌ If not matched
        return render_template(
            "login.html",
            error="❌ Invalid email or password. If you are new, please register first."
        )

    return render_template("login.html")
    
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    user = session["user"]

    applied_jobs = []
    aptitude_result = None
    aptitude_allowed = False
    aptitude_done = False

    if user["role"] == "candidate":
        applications = read_json(APPLICATIONS_FILE)
        applied_jobs = [a for a in applications if a["user_id"] == user["id"]]

        # 🔥 Load aptitude result
        if os.path.exists(APTITUDE_RESULT_FILE):
            with open(APTITUDE_RESULT_FILE) as f:
                results = json.load(f)

            # get latest result
            for r in reversed(results):
                if r["user_id"] == user["id"]:
                    aptitude_result = r
                    break

        # 🔥 Check aptitude permission + status
        for app in applications:
            if app["user_id"] == user["id"]:
                if app.get("aptitude_required", False):
                    aptitude_allowed = True
                if app.get("aptitude_status") == "completed":
                    aptitude_done = True

    return render_template(
        "dashboard.html",
        user=user,
        applied_jobs=applied_jobs,
        aptitude_result=aptitude_result,
        aptitude_allowed=aptitude_allowed,
        aptitude_done=aptitude_done
    )
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")




@app.route("/register", methods=["GET", "POST"])
def register():

    # 1️⃣ Page load
    if request.method == "GET":
        return render_template("register.html")

    # 2️⃣ JSON request after OTP verification
    if request.is_json:
        data = request.get_json()

        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        role = data.get("role")

        if not all([name, email, password, role]):
            return jsonify({
                "success": False,
                "message": "Missing fields"
            }), 400

        users = read_json(USERS_FILE)

        # ❌ Prevent duplicate email
        for u in users:
            if u["email"] == email:
                return jsonify({
                    "success": False,
                    "message": "Email already registered"
                }), 400

        # ✅ SAVE USER
        new_user = {
            "id": len(users) + 1,
            "name": name,
            "email": email,
            "password": password,
            "role": role
        }

        users.append(new_user)
        write_json(USERS_FILE, users)

        print("✅ USER SAVED:", new_user)  # DEBUG

        return jsonify({
            "success": True
        })

    return jsonify({
        "success": False,
        "message": "Invalid request"
    }), 400
# ================= CANDIDATE =================

@app.route("/my_interviews")
def my_interviews():
    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied"

    interviews = read_json(INTERVIEWS_FILE)
    schedules = read_json(SCHEDULE_FILE)

    user_id = session["user"]["id"]

    user_interviews = [i for i in interviews if i["user_id"] == user_id]
    schedule = next((s for s in schedules if s["user_id"] == user_id), None)

    return render_template(
        "my_interviews.html",
        interviews=user_interviews,
        schedule=schedule
    )

@app.route("/upload_resume", methods=["GET", "POST"])
def upload_resume():
    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied"

    resumes = read_json(RESUME_META_FILE)
    user_id = session["user"]["id"]

    if request.method == "POST":
        file = request.files.get("resume")

        if file and file.filename.endswith(".pdf"):
            resume_id = str(uuid.uuid4())[:8]   # ✅ UNIQUE ID
            filename = f"{user_id}_{int(datetime.now().timestamp())}.pdf"
            file_path = os.path.join(RESUME_FOLDER, filename)
            file.save(file_path)

            # deactivate old resumes
            for r in resumes:
                if r["user_id"] == user_id:
                    r["is_active"] = False

            resumes.append({
    "resume_id": resume_id,
    "user_id": user_id,
    "filename": filename,
    "uploaded_on": datetime.now().strftime("%d %b %Y %H:%M"),
    "uploaded_ts": datetime.now().timestamp(),   # ✅ ADD THIS
    "is_active": True
})

            write_json(RESUME_META_FILE, resumes)
            return redirect("/dashboard")

    return render_template("upload_resume.html")
    

@app.route("/jobs")
def jobs():
    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied", 403

    jobs_data = read_json(JOBS_FILE)
    clean_jobs = []

    for job in jobs_data:
        skills = job.get("skills", [])

        # 🔥 SAFETY FIX
        if isinstance(skills, list):
            skills_str = ", ".join(skills)
        else:
            skills_str = str(skills)

        clean_jobs.append({
            "job_id": job.get("job_id"),
            "title": job.get("title", "Untitled Job"),
            "skills": skills_str
        })

    return render_template("jobs.html", jobs=clean_jobs)
    
@app.route("/set_active_resume/<resume_id>")
def set_active_resume(resume_id):
    resumes = read_json(RESUME_META_FILE)
    user_id = session["user"]["id"]

    for r in resumes:
        if r["user_id"] == user_id:
            r["is_active"] = (r["resume_id"] == resume_id)

    write_json(RESUME_META_FILE, resumes)
    return redirect("/resume_history")
    
@app.route("/delete_resume/<resume_id>")
def delete_resume(resume_id):
    resumes = read_json(RESUME_META_FILE)
    user_id = session["user"]["id"]

    for r in resumes:
        if r["resume_id"] == resume_id and r["user_id"] == user_id:
            if r["is_active"]:
                return "Cannot delete active resume"
            os.remove(os.path.join(RESUME_FOLDER, r["filename"]))
            resumes.remove(r)
            break

    write_json(RESUME_META_FILE, resumes)
    return redirect("/resume_history")

# ================= APPLY JOB =================

@app.route("/apply_job/<int:job_id>", methods=["POST"])
def apply_job(job_id):

    if "user" not in session or session["user"]["role"] != "candidate":
        return "Access Denied", 403

    user_id = session["user"]["id"]

    # ---------- READ FORM DATA ----------
    try:
        experience = int(request.form["experience"])
        tenth = int(request.form["tenth"])
        twelfth = int(request.form["twelfth"])
        graduation = int(request.form["graduation"])
    except (KeyError, ValueError):
        return render_template(
            "message.html",
            message="❌ Please enter valid numeric values."
        )

    # ---------- VALIDATION ----------
    if experience < 0:
        return render_template("message.html", message="❌ Experience cannot be negative")

    if not (0 <= tenth <= 100):
        return render_template("message.html", message="❌ 10th % must be 0–100")

    if not (0 <= twelfth <= 100):
        return render_template("message.html", message="❌ 12th % must be 0–100")

    if not (0 <= graduation <= 100):
        return render_template("message.html", message="❌ Graduation % must be 0–100")

    # ---------- LOAD DATA ----------
    jobs = read_json(JOBS_FILE)
    applications = read_json(APPLICATIONS_FILE)

    job = next((j for j in jobs if j["job_id"] == job_id), None)
    if not job:
        return "Job not found", 404

    # ---------- DUPLICATE CHECK ----------
    for app in applications:
        if app["user_id"] == user_id and app["job_id"] == job_id:
            return render_template(
                "message.html",
                message="⚠️ You have already applied for this job."
            )

    # ---------- SAVE APPLICATION ----------
    new_application = {
    "user_id": user_id,
    "job_id": job_id,
    "job_title": job["title"],
    "experience": experience,
    "tenth": tenth,
    "twelfth": twelfth,
    "graduation": graduation,
    "status": "Applied",

    # 🔥 NEW FIELDS
    "aptitude_required": False,
    "aptitude_status": "not_assigned"
    }

    applications.append(new_application)
    write_json(APPLICATIONS_FILE, applications)

    print("✅ Application Saved:", new_application)

    return redirect("/dashboard")
    
@app.route("/applied_jobs")
def applied_jobs():

    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied", 403

    user_id = session["user"]["id"]
    applications = read_json(APPLICATIONS_FILE)

    # ✅ FILTER CORRECTLY
    user_jobs = [
        app for app in applications
        if app["user_id"] == user_id
    ]

    return render_template(
        "applied_jobs.html",
        jobs=user_jobs
    )
    
@app.route("/download_resume/<filename>")
def download_resume(filename):
    if "user" not in session:
        return "Unauthorized"

    user = session["user"]
    resumes = read_json(RESUME_META_FILE)

    # Candidate: can download only own resume
    if user["role"] == "candidate":
        allowed = any(
            r for r in resumes
            if r["filename"] == filename and r["user_id"] == user["id"]
        )
        if not allowed:
            return "Unauthorized"

    # HR: can download any resume
    elif user["role"] == "hr":
        allowed = any(r for r in resumes if r["filename"] == filename)
        if not allowed:
            return "Resume not found"

    else:
        return "Unauthorized"

    return send_from_directory(RESUME_FOLDER, filename, as_attachment=True)
    
# ================= MOCK INTERVIEW =================

@app.route("/start_interview", methods=["GET"])
def start_interview():

    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied"

    resumes = read_json(RESUME_META_FILE)
    active_resume = next(
        (r for r in resumes
         if r["user_id"] == session["user"]["id"] and r["is_active"]),
        None
    )

    if not active_resume:
        return redirect("/upload_resume")

    resume_path = os.path.join(RESUME_FOLDER, active_resume["filename"])
    resume_text = extract_text_from_pdf(resume_path)

    # 🔥 AI-based skill extraction
    skills = extract_skills_from_resume(resume_text)
    if not skills:
        skills = ["python"]

    # 🔥 AI-generated questions (NO static questions)
    questions = generate_questions(skills)

    # store for submission
    session["questions"] = questions

    return render_template("interview.html", questions=questions)
    
@app.route("/submit_interview", methods=["POST"])
def submit_interview():

    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied"

    questions = session.get("questions", [])

    if not questions:
        return redirect("/start_interview")

    answers = [
        request.form.get(f"answer_{i}", "").strip()
        for i in range(len(questions))
    ]

    # 🔥 AI evaluation
    score, weak_areas, readiness = evaluate_answers(questions, answers)

    interviews = read_json(INTERVIEWS_FILE)

    # remove old record for same user
    interviews = [
        i for i in interviews
        if i["user_id"] != session["user"]["id"]
    ]

    interviews.append({
        "user_id": session["user"]["id"],
        "name": session["user"]["name"],
        "email": session["user"]["email"],
        "score": score,
        "weak_areas": weak_areas,
        "readiness": readiness,
        "hr_decision": "pending"
    })

    write_json(INTERVIEWS_FILE, interviews)

    # cleanup
    session.pop("questions", None)

    return render_template(
        "interview_result.html",
        score=score,
        weak_areas=weak_areas,
        readiness=readiness
    )

# ================= HR =================
@app.route("/hr_dashboard")
def hr_dashboard():
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"
    return render_template("hr_dashboard.html", jobs=read_json(JOBS_FILE))


@app.route("/hr_interviews")
def hr_interviews():
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    interviews = read_json(INTERVIEWS_FILE)
    users = read_json(USERS_FILE)
    schedules = read_json(SCHEDULE_FILE)

    reports = []

    for i in interviews:
        user = next((u for u in users if u["id"] == i["user_id"]), None)
        if not user:
            continue

        schedule = next((s for s in schedules if s["user_id"] == user["id"]), None)

        reports.append({
            "user_id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "score": i["score"],
            "weak_areas": i["weak_areas"],
            "readiness": i.get("readiness", "Not Ready"),
            "hr_decision": i.get("hr_decision", "pending"),
            "schedule": schedule
        })

    return render_template("hr_interviews.html", interviews=reports)
    
@app.route("/hr_decision/<int:user_id>/<decision>")
def hr_decision(user_id, decision):

    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    interviews = read_json(INTERVIEWS_FILE)
    applications = read_json(APPLICATIONS_FILE)
    users = read_json(USERS_FILE)

    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        return "User not found", 404

    # ✅ Update interviews.json
    for i in interviews:
        if i["user_id"] == user_id:
            i["hr_decision"] = decision
            i["readiness"] = "Ready" if decision == "shortlisted" else "Not Ready"
            break

    # ✅ Update applications.json
    for appn in applications:
        if appn["user_id"] == user_id:
            appn["status"] = "Shortlisted" if decision == "shortlisted" else "Rejected"

    write_json(INTERVIEWS_FILE, interviews)
    write_json(APPLICATIONS_FILE, applications)

    return "OK", 200
    

@app.route("/hr_applications/<int:job_id>")
def hr_applications(job_id=None):
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    applications = read_json(APPLICATIONS_FILE)
    users = read_json(USERS_FILE)
    jobs = read_json(JOBS_FILE)
    resumes = read_json(RESUME_META_FILE)

    data = []

    for idx, appn in enumerate(applications):

        # ✅ FILTER BY JOB ID (THIS WAS THE BUG)
        if job_id is not None and str(appn["job_id"]) != str(job_id):
            continue

        user = next((u for u in users if u["id"] == appn["user_id"]), None)
        job = next((j for j in jobs if str(j["job_id"]) == str(appn["job_id"])), None)

        if not user or not job:
            continue

        active_resume = next(
            (r for r in resumes if r["user_id"] == user["id"] and r["is_active"]),
            None
        )

        data.append({
            "app_id": idx,
            "candidate": user["name"],
            "email": user["email"],
            "job_title": job["title"],
            "experience": appn["experience"],
            "tenth": appn["tenth"],
            "twelfth": appn["twelfth"],
            "graduation": appn["graduation"],
            "status": appn["status"].lower(),
            "resume_filename": active_resume["filename"] if active_resume else None
        })

    return render_template("hr_applications.html", applications=data)

@app.route("/hr_direct_decision/<int:app_id>/<decision>")
def hr_direct_decision(app_id, decision):

    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    applications = read_json(APPLICATIONS_FILE)
    users = read_json(USERS_FILE)

    if app_id >= len(applications):
        return "Invalid application", 404

    appn = applications[app_id]

    # ✅ Update status
    appn["status"] = decision.capitalize()

    # ✅ Get candidate
    user = next(u for u in users if u["id"] == appn["user_id"])

    # ✅ Send email
    send_hr_decision_email(
        user["email"],
        user["name"],
        decision,
        appn["job_title"]
    )

    write_json(APPLICATIONS_FILE, applications)

    return redirect("/hr_applications")
    
def send_hr_decision_email(email, name, decision, job_title):
    subject = f"Application Update – {job_title}"

    message = f"""
Hi {name},

We have reviewed your application for the position of {job_title}.

Status: {decision.capitalize()}

Thank you for applying.
Best wishes,
HR Team
    """

    print("EMAIL SENT TO:", email)
    print(subject)
    print(message)
    

@app.route("/hr_applications")
def hr_applications_all():
    return render_hr_applications()
    
@app.route("/hr_applications/<int:job_id>")
def hr_applications_by_job(job_id):
    return render_hr_applications(job_id)

def render_hr_applications(job_id=None):
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    applications = read_json(APPLICATIONS_FILE)
    users = read_json(USERS_FILE)
    resumes = read_json(RESUME_META_FILE)
    jobs = read_json(JOBS_FILE)

    data = []

    for idx, appn in enumerate(applications):

        # 🔎 Filter by job if needed
        if job_id and appn["job_id"] != job_id:
            continue

        user = next((u for u in users if u["id"] == appn["user_id"]), None)
        job = next((j for j in jobs if j["job_id"] == appn["job_id"]), None)
        resume = next(
            (r for r in resumes if r["user_id"] == user["id"] and r["is_active"]),
            None
        )

        if not user or not job:
            continue

        data.append({
            # 🔥 IMPORTANT: index used as app_id
            "app_id": idx,

            "candidate": user["name"],
            "email": user["email"],
            "job_title": job["title"],
            "experience": appn["experience"],
            "tenth": appn["tenth"],
            "twelfth": appn["twelfth"],
            "graduation": appn["graduation"],
            "status": appn["status"].lower(),

            # 📄 Resume
            "resume_filename": resume["filename"] if resume else None,

            # 🧠 Aptitude flow
            "aptitude_required": appn.get("aptitude_required", False),
            "aptitude_status": appn.get("aptitude_status", "not_assigned")
        })

    return render_template("hr_applications.html", applications=data)

def send_tech_round_email(email, name):
    subject = "🎉 You are selected for Technical Round"

    message = f"""
Hi {name},

Congratulations! 🎊

Based on your aptitude test performance, you have been shortlisted for the
Technical Interview Round.

Our HR team will contact you shortly with further details.

Best of luck! 🚀  
AI Recruitment Team
"""

    # For now just print (safe)
    print("📧 TECH ROUND EMAIL")
    print("TO:", email)
    print("SUBJECT:", subject)
    print(message)

@app.route("/schedule_interview/<int:user_id>", methods=["GET", "POST"])
def schedule_interview(user_id):
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    schedules = read_json(SCHEDULE_FILE)
    users = read_json(USERS_FILE)

    user = next(u for u in users if u["id"] == user_id)

    if request.method == "POST":
        schedules = [s for s in schedules if s["user_id"] != user_id]

        new_schedule = {
            "user_id": user_id,
            "date": request.form["date"],
            "time": request.form["time"],
            "mode": request.form["mode"]
        }

        schedules.append(new_schedule)
        write_json(SCHEDULE_FILE, schedules)

        send_interview_schedule_email(
            user["email"],
            user["name"],
            new_schedule["date"],
            new_schedule["time"],
            new_schedule["mode"]
        )

        return redirect("/hr_interviews")

    return render_template("schedule_interview.html", candidate=user)


@app.route("/post_job", methods=["GET", "POST"])
def post_job():
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    if request.method == "POST":
        jobs = read_json(JOBS_FILE)
        jobs.append({
            "job_id": len(jobs) + 1,
            "title": request.form["title"],
            "skills": request.form["skills"].lower().split(","),
            "min_exp": int(request.form["min_exp"]),
            "max_exp": int(request.form["max_exp"]),
            "min_10": int(request.form["min_10"]),
            "min_12": int(request.form["min_12"]),
            "min_grad": int(request.form["min_grad"]),
            "hr_id": session["user"]["id"]
        })
        write_json(JOBS_FILE, jobs)
        return redirect("/hr_dashboard")

    return render_template("post_job.html")

@app.route("/test_email")
def test_email():
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_EMAIL
        msg["To"] = SMTP_EMAIL
        msg["Subject"] = "SMTP Test Success"
        msg.attach(MIMEText("If you got this email, SMTP works!", "plain"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, SMTP_EMAIL, msg.as_string())
        server.quit()

        return "✅ SMTP WORKING – Email sent successfully"

    except Exception as e:
        return f"❌ SMTP FAILED: {e}"
        
@app.route("/save_schedule", methods=["POST"])
def save_schedule():
    if session.get("user", {}).get("role") != "hr":
        return {"success": False}, 403

    data = request.json
    schedules = read_json(SCHEDULE_FILE)

    # Remove old schedule (if any)
    schedules = [s for s in schedules if s["user_id"] != data["user_id"]]

    schedules.append({
        "user_id": data["user_id"],
        "date": data["date"],
        "time": data["time"],
        "mode": data["mode"]
    })

    write_json(SCHEDULE_FILE, schedules)
    return {"success": True}

@app.route("/resume_history")
def resume_history():
    if "user" not in session or session["user"]["role"] != "candidate":
        return "Access Denied", 403

    resumes = read_json(RESUME_META_FILE)
    user_id = session["user"]["id"]

    user_resumes = [r for r in resumes if r["user_id"] == user_id]

    return render_template(
        "resume_history.html",
        resumes=user_resumes
    )

@app.route("/hr_schedule_direct/<int:app_id>", methods=["POST"])
def hr_schedule_direct(app_id):
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    date = request.form.get("date")
    time = request.form.get("time")
    mode = request.form.get("mode")

    if not date or not time or not mode:
        return "Missing interview details", 400

    applications = read_json(APPLICATIONS_FILE)
    users = read_json(USERS_FILE)
    schedules = read_json(SCHEDULE_FILE)

    appn = applications[app_id]
    user = next(u for u in users if u["id"] == appn["user_id"])

    # Remove old schedule if exists
    schedules = [s for s in schedules if s["user_id"] != user["id"]]

    new_schedule = {
        "user_id": user["id"],
        "job_title": appn["job_title"],
        "date": date,
        "time": time,
        "mode": mode
    }

    schedules.append(new_schedule)
    write_json(SCHEDULE_FILE, schedules)

    # Update application status
    appn["status"] = "Scheduled"
    write_json(APPLICATIONS_FILE, applications)

    # 📧 Send Email (EmailJS handled on frontend earlier OR skip if already done)
    # If you want backend email later, we’ll add it cleanly

    return redirect("/hr_applications")

    
@app.route("/send_otp", methods=["POST"])
def send_otp():
    otp = random.randint(100000, 999999)
    session["otp"] = str(otp)
    return jsonify({"success": True, "otp": otp})

@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    if data["otp"] != session.get("otp"):
        return jsonify({"success": False})
    return jsonify({"success": True})
    
@app.route("/hr_history")
def hr_history():

    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    interviews = read_json(INTERVIEWS_FILE)
    applications = read_json(APPLICATIONS_FILE)
    schedules = read_json(SCHEDULE_FILE)

    history = []

    for i in interviews:
        # only show where HR has taken decision
        if i.get("hr_decision") not in ["shortlisted", "rejected"]:
            continue

        # find application
        appn = next((a for a in applications if a["user_id"] == i["user_id"]), None)

        # find schedule
        sched = next((s for s in schedules if s["user_id"] == i["user_id"]), None)

        history.append({
            "name": i["name"],
            "email": i["email"],
            "job_title": appn["job_title"] if appn else "N/A",
            "status": i["hr_decision"].capitalize(),
            "schedule": sched
        })

    return render_template("hr_history.html", history=history)

@app.route("/aptitude_test")
def aptitude_test():

    if "user" not in session:
        return redirect("/")

    level = session.get("aptitude_level", "easy")

    with open("data/aptitude_questions.json") as f:
        all_questions = json.load(f)

    questions = all_questions.get(level, [])[:10]

    return render_template(
        "aptitude_test.html",
        questions=questions,
        level=level
    )
    
@app.route("/submit_aptitude", methods=["POST"])
def submit_aptitude():

    user = session.get("user")
    if not user:
        return redirect("/")

    level = session.get("aptitude_level", "easy")

    with open(APTITUDE_Q_FILE) as f:
        all_questions = json.load(f)

    questions = all_questions[level][:10]

    score = 0
    for q in questions:
        qid = str(q["id"])
        if request.form.get(qid) == q["answer"]:
            score += 1

    total = len(questions)
    percentage = (score / total) * 100

    # 🔥 AUTO DECISION
    # 🔥 AUTO DECISION
    if percentage >= 70:
        decision = "tech"

    # 📧 SEND TECH ROUND EMAIL
        send_tech_round_email(user["email"], user["name"])
    else:
        decision = "pending"    # HR will decide

    result = {
        "user_id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "level": level,
        "score": score,
        "total": total,
        "percentage": round(percentage, 2),
        "decision": decision
    }

    # save result
    with open(APTITUDE_RESULT_FILE) as f:
        results = json.load(f)

    results.append(result)

    with open(APTITUDE_RESULT_FILE, "w") as f:
        json.dump(results, f, indent=4)
    
    applications = read_json(APPLICATIONS_FILE)

    for app in applications:
        if app["user_id"] == user["id"] and app.get("aptitude_required"):
            app["aptitude_status"] = "completed"
            break

    write_json(APPLICATIONS_FILE, applications)

    return render_template("aptitude_result.html", result=result)
@app.route("/hr_aptitude_decision/<int:user_id>/<decision>")
def hr_aptitude_decision(user_id, decision):

    if "user" not in session or session["user"]["role"] != "hr":
        return "Access Denied"

    with open(APTITUDE_RESULT_FILE) as f:
        results = json.load(f)

    # update latest result
    for r in reversed(results):
        if r["user_id"] == user_id:
            r["decision"] = decision

        # 📧 If HR selects for tech round
            if decision == "tech":
                send_tech_round_email(r["email"], r["name"])

            break

    with open(APTITUDE_RESULT_FILE, "w") as f:
        json.dump(results, f, indent=4)

    return redirect(f"/hr_aptitude/{user_id}")

@app.route("/aptitude")
def aptitude_start():

    user = session.get("user")
    if not user:
        return redirect("/")

    exp = int(request.args.get("exp", 0))

    if exp == 0:
        level = "easy"
    elif exp == 1:
        level = "medium"
    else:
        level = "hard"

    with open(APTITUDE_Q_FILE, "r") as f:
        data = json.load(f)

    # 🔥 DEBUG PRINT (important)
    print("LEVEL:", level)
    print("AVAILABLE KEYS:", data.keys())

    questions = data.get(level, [])

    print("QUESTIONS COUNT:", len(questions))

    session["aptitude_level"] = level

    return render_template(
        "aptitude_test.html",
        questions=questions[:10],
        level=level
    )
    
@app.route("/aptitude_start")
def aptitude_start_page():
    if "user" not in session:
        return redirect("/")
    return render_template("aptitude_start.html")

@app.route("/start_aptitude", methods=["POST"])
def start_aptitude():

    if "user" not in session:
        return redirect("/")

    exp = int(request.form.get("experience", 0))

    if exp == 0:
        level = "easy"
    elif exp == 1:
        level = "medium"
    else:
        level = "hard"

    session["aptitude_level"] = level

    return redirect("/aptitude_test")
    
@app.route("/aptitude_history")
def aptitude_history():

    if "user" not in session:
        return redirect("/")

    user = session["user"]

    if user["role"] != "candidate":
        return "Access Denied"

    history = []

    if os.path.exists(APTITUDE_RESULT_FILE):
        with open(APTITUDE_RESULT_FILE) as f:
            results = json.load(f)

        # only this user's results
        history = [r for r in results if r["user_id"] == user["id"]]

    return render_template("aptitude_history.html", history=history)

@app.route("/hr_aptitude_results")
def hr_aptitude_results():

    if "user" not in session or session["user"]["role"] != "hr":
        return "Access Denied"

    history = []

    if os.path.exists(APTITUDE_RESULT_FILE):
        with open(APTITUDE_RESULT_FILE) as f:
            results = json.load(f)

    else:
        results = []

    users = read_json(USERS_FILE)

    for r in results:
        user = next((u for u in users if u["id"] == r["user_id"]), None)
        if not user:
            continue

        history.append({
            "name": user["name"],
            "email": user["email"],
            "level": r["level"],
            "score": r["score"],
            "total": r["total"]
        })

    return render_template("hr_aptitude_results.html", history=history)

@app.route("/hr_aptitude")
def hr_aptitude():

    if "user" not in session or session["user"]["role"] != "hr":
        return "Access Denied"

    if os.path.exists(APTITUDE_RESULT_FILE):
        with open(APTITUDE_RESULT_FILE) as f:
            results = json.load(f)
    else:
        results = []

    users = read_json(USERS_FILE)

    candidates = []
    seen = set()

    for r in results:
        uid = r["user_id"]
        if uid in seen:
            continue

        user = next((u for u in users if u["id"] == uid), None)
        if not user:
            continue

        candidates.append({
            "id": uid,
            "name": user["name"],
            "email": user["email"]
        })
        seen.add(uid)

    return render_template("hr_aptitude_list.html", candidates=candidates)

@app.route("/hr_aptitude/<int:user_id>")
def hr_view_aptitude(user_id):

    if "user" not in session or session["user"]["role"] != "hr":
        return "Access Denied"

    if os.path.exists(APTITUDE_RESULT_FILE):
        with open(APTITUDE_RESULT_FILE) as f:
            results = json.load(f)
    else:
        results = []

    users = read_json(USERS_FILE)
    user = next((u for u in users if u["id"] == user_id), None)

    if not user:
        return "Candidate not found"

    # get latest result
    user_results = [r for r in results if r["user_id"] == user_id]

    if not user_results:
        return "No aptitude result for this candidate"

    latest = user_results[-1]

    return render_template(
        "hr_aptitude_view.html",
        user=user,
        result=latest
    )

@app.route("/hr_aptitude_history")
def hr_aptitude_history():

    if "user" not in session or session["user"]["role"] != "hr":
        return redirect("/dashboard")

    with open(APTITUDE_RESULT_FILE) as f:
        results = json.load(f)

    return render_template("hr_aptitude_history.html", results=results)
    
@app.route("/hr_aptitude_view/<int:user_id>")
def hr_aptitude_view(user_id):

    with open(APTITUDE_RESULT_FILE) as f:
        results = json.load(f)

    result = None
    for r in results:
        if r["user_id"] == user_id:
            result = r
            break

    if not result:
        return "Result not found"

    return render_template("hr_aptitude_result.html", result=result, user=result)
    
@app.route("/assign_aptitude/<int:app_id>")
def assign_aptitude(app_id):

    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    applications = read_json(APPLICATIONS_FILE)
    users = read_json(USERS_FILE)

    # app_id is index of application
    if app_id >= len(applications):
        return "Invalid application", 404

    appn = applications[app_id]

    # ✅ Mark aptitude assigned
    appn["aptitude_required"] = True
    appn["aptitude_status"] = "pending"

    # ✅ Get candidate info
    user = next(u for u in users if u["id"] == appn["user_id"])

    # 📧 SEND EMAIL
    send_aptitude_invite_email(
        user["email"],
        user["name"],
        appn["job_title"]
    )

    write_json(APPLICATIONS_FILE, applications)

    return redirect("/hr_applications")
    
def send_aptitude_invite_email(email, name, job_title):
    subject = "📝 Aptitude Test Invitation"

    message = f"""
Hi {name},

You have been shortlisted for the next step in the hiring process for:

Position: {job_title}

Please log in to your dashboard and complete the Aptitude Test assigned to you.

This test will help us evaluate you for the next round.

Best of luck! 🚀  
AI Recruitment Team
"""

    # For now, just print (safe testing)
    print("📧 APTITUDE INVITE EMAIL")
    print("TO:", email)
    print("SUBJECT:", subject)
    print(message)
# ================= RUN =================

if __name__ == "__main__":
    app.run()