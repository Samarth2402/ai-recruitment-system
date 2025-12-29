from flask import Flask, render_template, request, redirect, session, send_from_directory
import os, random, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
SMTP_EMAIL = "ss9879086402@gmail.com"
SMTP_PASSWORD = "ojwsndwozpbrmcuk"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

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

# ================= EMAIL HELPERS =================
def generate_otp():
    return str(random.randint(100000, 999999))
    
def send_email(subject, body, to_email):
    try:
        msg = MIMEMultipart()
        msg["From"] = f"AI Recruitment System <{SMTP_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()

        print("✅ EMAIL SENT SUCCESSFULLY TO:", to_email)

    except Exception as e:
        print("❌ EMAIL FAILED:", e)

def send_hr_decision_email(email, name, decision):
    if decision == "shortlisted":
        subject = "Shortlisted | AI Recruitment System"
        body = f"""
Hello {name},

Congratulations 🎉
You have been SHORTLISTED after the mock interview.

HR will contact you soon.

Regards,
AI Recruitment System
"""
    else:
        subject = "Interview Result | AI Recruitment System"
        body = f"""
Hello {name},

Thank you for attending the interview.
Currently, you are not shortlisted.

You may try again.

Regards,
AI Recruitment System
"""
    send_email(subject, body, email)

def send_interview_schedule_email(email, name, date, time, mode):
    subject = "Interview Scheduled | AI Recruitment System"
    body = f"""
Hello {name},

Your interview is scheduled.

📅 Date: {date}
⏰ Time: {time}
📍 Mode: {mode}

Best of luck!

Regards,
AI Recruitment System
"""
    send_email(subject, body, email)

def send_email_otp(to_email, otp):
    subject = "OTP Verification | AI Recruitment System"
    body = f"""
Hello,

Your OTP for registration is:

🔐 OTP: {otp}

Please do not share this OTP with anyone.

Regards,
AI Recruitment System
"""
    send_email(subject, body, to_email)
# ================= AUTH =================

@app.route("/", methods=["GET", "POST"])
def login():
    users = read_json(USERS_FILE)
    if request.method == "POST":
        for u in users:
            if u["email"] == request.form["email"] and u["password"] == request.form["password"]:
                session["user"] = u
                return redirect("/dashboard")
        return render_template("login.html", message="Invalid credentials")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    user = session["user"]

    applied_jobs = []

    if user["role"] == "candidate":
        applications = read_json(APPLICATIONS_FILE)

        applied_jobs = [
            app for app in applications
            if app["user_id"] == user["id"]
        ]

    return render_template(
        "dashboard.html",
        user=user,
        applied_jobs=applied_jobs
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    users = read_json(USERS_FILE)
    otp_data = read_json(OTP_FILE)

    if not isinstance(otp_data, list):
        otp_data = []

    if request.method == "POST":
        action = request.form.get("action")

        if action == "send":
            email = request.form["email"]

            for u in users:
                if u["email"] == email:
                    return render_template("register.html", error="Email already registered")

            otp = generate_otp()

            otp_data.append({
                "name": request.form["name"],
                "email": email,
                "password": request.form["password"],
                "role": request.form["role"],
                "otp": otp
            })
            write_json(OTP_FILE, otp_data)
            send_email_otp(email, otp)

            return render_template("register.html", otp_sent=True)

        if action == "verify":
            entered_otp = request.form["otp"]

            for record in otp_data:
                if record["otp"] == entered_otp:
                    users.append({
                        "id": len(users) + 1,
                        "name": record["name"],
                        "email": record["email"],
                        "password": record["password"],
                        "role": record["role"]
                    })
                    write_json(USERS_FILE, users)
                    write_json(OTP_FILE, [])
                    return render_template("register.html", success=True)

            return render_template("register.html", otp_sent=True, error="Invalid OTP")

    return render_template("register.html")

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
def view_jobs():
    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied"
    return render_template("jobs.html", jobs=read_json(JOBS_FILE))
    
    
@app.route("/resume_history")
def resume_history():
    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied"

    resumes = read_json(RESUME_META_FILE)
    user_id = session["user"]["id"]
    

    user_resumes = sorted(
    [r for r in resumes if r["user_id"] == user_id],
    key=lambda x: x.get("uploaded_ts", 0),
    reverse=True
)

    return render_template(
        "resume_history.html",
        resumes=user_resumes
    )
    
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
        return redirect("/")

    user = session["user"]

    # ✅ Get active resume
    resumes = read_json(RESUME_META_FILE)
    active_resume = next(
        (r for r in resumes if r["user_id"] == user["id"] and r["is_active"]),
        None
    )

    if not active_resume:
        return redirect("/upload_resume")

    resume_path = os.path.join(RESUME_FOLDER, active_resume["filename"])
    resume_text = extract_text_from_pdf(resume_path)

    jobs = read_json(JOBS_FILE)
    job = next((j for j in jobs if j["job_id"] == job_id), None)

    if not job:
        return redirect("/jobs")

    score, _ = calculate_match_score(resume_text, job["skills"])

    applications = read_json(APPLICATIONS_FILE)

    for app in applications:
        if app["user_id"] == user["id"] and app["job_id"] == job_id:
            return redirect("/dashboard")

    applications.append({
        "user_id": user["id"],
        "job_id": job_id,
        "job_title": job["title"],
        "score": score,
        "status": "Applied"
    })

    write_json(APPLICATIONS_FILE, applications)

    send_email(
        "Job Application Submitted | AI Recruitment System",
        f"""
Hello {user['name']},

Your application for "{job['title']}" has been submitted successfully.

Regards,
AI Recruitment System
""",
        user["email"]
    )

    return redirect("/dashboard")
    
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

@app.route("/start_interview")
def start_interview():

    if session.get("user", {}).get("role") != "candidate":
        return "Access Denied"

    resumes = read_json(RESUME_META_FILE)
    active_resume = next(
        (r for r in resumes if r["user_id"] == session["user"]["id"] and r["is_active"]),
        None
    )

    if not active_resume:
        return redirect("/upload_resume")

    resume_path = os.path.join(RESUME_FOLDER, active_resume["filename"])
    resume_text = extract_text_from_pdf(resume_path)

    skills = extract_skills_from_resume(resume_text)
    if not skills:
        skills = ["python"]

    questions = generate_questions(skills)
    session["questions"] = questions

    return render_template("interview.html", questions=questions)
    
@app.route("/submit_interview", methods=["POST"])
def submit_interview():
    questions = session.get("questions", [])
    answers = [request.form.get(f"answer_{i}", "") for i in range(len(questions))]

    score, weak_areas, readiness = evaluate_answers(questions, answers)

    interviews = read_json(INTERVIEWS_FILE)
    interviews = [i for i in interviews if i["user_id"] != session["user"]["id"]]

    interviews.append({
        "user_id": session["user"]["id"],
        "score": score,
        "weak_areas": weak_areas,
        "readiness": readiness,
        "hr_decision": "pending"
    })

    write_json(INTERVIEWS_FILE, interviews)

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
            "readiness": i["readiness"],
            "hr_decision": i.get("hr_decision", "pending"),
            "schedule": schedule
        })

    return render_template("hr_interviews.html", interviews=reports)

@app.route("/hr_decision/<int:user_id>/<decision>")
def hr_decision(user_id, decision):
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    interviews = read_json(INTERVIEWS_FILE)
    users = read_json(USERS_FILE)
    applications = read_json(APPLICATIONS_FILE)

    user = next(u for u in users if u["id"] == user_id)

    # ✅ Update interview decision
    for i in interviews:
        if i["user_id"] == user_id:
            i["hr_decision"] = decision
            i["readiness"] = "Ready" if decision == "shortlisted" else "Not Ready"
            send_hr_decision_email(user["email"], user["name"], decision)
            break

    # ✅ ALSO update application status
    for appn in applications:
        if appn["user_id"] == user_id:
            appn["status"] = decision.capitalize()   # Shortlisted / Rejected

    write_json(INTERVIEWS_FILE, interviews)
    write_json(APPLICATIONS_FILE, applications)

    return redirect("/hr_interviews")
@app.route("/hr_applications")
def hr_applications():
    if session.get("user", {}).get("role") != "hr":
        return "Access Denied"

    applications = read_json(APPLICATIONS_FILE)
    users = read_json(USERS_FILE)
    jobs = read_json(JOBS_FILE)
    resumes = read_json(RESUME_META_FILE)

    data = []

    for appn in applications:
        user = next((u for u in users if u["id"] == appn["user_id"]), None)
        job = next((j for j in jobs if j["job_id"] == appn["job_id"]), None)

        if not user or not job:
            continue

        active_resume = next(
            (r for r in resumes if r["user_id"] == user["id"] and r["is_active"]),
            None
        )

        data.append({
            "candidate": user["name"],
            "email": user["email"],
            "job_title": job["title"],
            "score": appn["score"],
            "status": appn["status"],
            "resume_filename": active_resume["filename"] if active_resume else None
        })

    return render_template("hr_applications.html", applications=data)
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

# ================= RUN =================

if __name__ == "__main__":
    app.run(hosts="0.0.0.0",port=10000)