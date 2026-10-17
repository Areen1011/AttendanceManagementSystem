import csv
import io
import os
import secrets
from contextlib import contextmanager
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db_connection

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
CSRFProtect(app)


@contextmanager
def database_cursor(dictionary=True):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=dictionary)
    try:
        yield connection, cursor
    finally:
        cursor.close()
        connection.close()


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if f"{role}_id" not in session:
                flash("Please sign in to continue.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def password_matches(stored_password, submitted_password):
    if not stored_password:
        return False, False

    try:
        if check_password_hash(stored_password, submitted_password):
            return True, False
    except (ValueError, TypeError):
        pass

    # Upgrade legacy plain-text passwords after the first successful login.
    if secrets.compare_digest(
        str(stored_password).encode("utf-8"), submitted_password.encode("utf-8")
    ):
        return True, True
    return False, False


def parse_report_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        flash("Choose a valid report date.", "error")
        return None


def teacher_for_session(cursor):
    cursor.execute(
        "SELECT id, name, class FROM teachers WHERE id=%s",
        (session["teacher_id"],),
    )
    return cursor.fetchone()


def attendance_report(cursor, selected_date, class_name=None):
    query = """
        SELECT s.roll_no, s.name, s.class,
               COALESCE(a.status, 'Not marked') AS status
        FROM students s
        LEFT JOIN attendance a
          ON a.student_id = s.id AND a.date = %s
    """
    params = [selected_date]
    if class_name:
        query += " WHERE s.class = %s"
        params.append(class_name)
    query += " ORDER BY s.class, s.roll_no"
    cursor.execute(query, tuple(params))
    return cursor.fetchall()


def safe_spreadsheet_value(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Enter your email and password.", "error")
            return render_template("login.html")

        with database_cursor() as (connection, cursor):
            cursor.execute(
                "SELECT id, email, password FROM admins WHERE email=%s",
                (email,),
            )
            admin = cursor.fetchone()

            if admin:
                matched, upgrade = password_matches(admin["password"], password)
                if matched:
                    if upgrade:
                        cursor.execute(
                            "UPDATE admins SET password=%s WHERE id=%s",
                            (generate_password_hash(password), admin["id"]),
                        )
                        connection.commit()
                    session.clear()
                    session["admin_id"] = admin["id"]
                    return redirect(url_for("admin_dashboard"))

            cursor.execute(
                "SELECT id, name, class, email, password FROM teachers WHERE email=%s",
                (email,),
            )
            teacher = cursor.fetchone()

            if teacher:
                matched, upgrade = password_matches(teacher["password"], password)
                if matched:
                    if upgrade:
                        cursor.execute(
                            "UPDATE teachers SET password=%s WHERE id=%s",
                            (generate_password_hash(password), teacher["id"]),
                        )
                        connection.commit()
                    session.clear()
                    session["teacher_id"] = teacher["id"]
                    return redirect(url_for("teacher_dashboard"))

        flash("The email or password is incorrect.", "error")

    return render_template("login.html")


@app.route("/admin-dashboard")
@role_required("admin")
def admin_dashboard():
    with database_cursor() as (_, cursor):
        cursor.execute("SELECT COUNT(*) AS total FROM teachers")
        total_teachers = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT COUNT(*) AS total FROM attendance WHERE date=%s",
            (date.today(),),
        )
        attendance_today = cursor.fetchone()["total"]

    return render_template(
        "admin_dashboard.html",
        total_teachers=total_teachers,
        total_students=total_students,
        attendance_today=attendance_today,
        current_date=date.today(),
    )


@app.route("/manage-teachers", methods=["GET", "POST"])
@role_required("admin")
def manage_teachers():
    with database_cursor() as (connection, cursor):
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            class_name = request.form.get("class", "").strip()
            if not all((name, email, password, class_name)) or len(password) < 8:
                flash("Complete all fields and use a password of at least 8 characters.", "error")
            else:
                cursor.execute("SELECT id FROM teachers WHERE email=%s", (email,))
                if cursor.fetchone():
                    flash("A teacher account already uses that email address.", "error")
                else:
                    cursor.execute(
                        "INSERT INTO teachers (name,email,password,class) VALUES (%s,%s,%s,%s)",
                        (name, email, generate_password_hash(password), class_name),
                    )
                    connection.commit()
                    flash(f"{name} was added as a teacher.", "success")
                    return redirect(url_for("manage_teachers"))

        cursor.execute("SELECT id, name, email, class FROM teachers ORDER BY name")
        teachers = cursor.fetchall()
    return render_template("manage_teachers.html", teachers=teachers)


@app.route("/delete-teacher/<int:id>", methods=["POST"])
@role_required("admin")
def delete_teacher(id):
    with database_cursor() as (connection, cursor):
        cursor.execute("DELETE FROM teachers WHERE id=%s", (id,))
        if cursor.rowcount == 0:
            abort(404)
        connection.commit()
    flash("Teacher account deleted.", "success")
    return redirect(url_for("manage_teachers"))


@app.route("/edit-teacher/<int:id>", methods=["GET", "POST"])
@role_required("admin")
def edit_teacher(id):
    with database_cursor() as (connection, cursor):
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            class_name = request.form.get("class", "").strip()
            if not all((name, email, class_name)):
                flash("Complete all fields before saving.", "error")
            else:
                cursor.execute(
                    "SELECT id FROM teachers WHERE id=%s",
                    (id,),
                )
                if cursor.fetchone() is None:
                    abort(404)
                cursor.execute(
                    "SELECT id FROM teachers WHERE email=%s AND id<>%s",
                    (email, id),
                )
                if cursor.fetchone():
                    flash("Another teacher account already uses that email address.", "error")
                else:
                    cursor.execute(
                        "UPDATE teachers SET name=%s, email=%s, class=%s WHERE id=%s",
                        (name, email, class_name, id),
                    )
                    connection.commit()
                    flash("Teacher details updated.", "success")
                    return redirect(url_for("manage_teachers"))

        cursor.execute(
            "SELECT id, name, email, class FROM teachers WHERE id=%s",
            (id,),
        )
        teacher = cursor.fetchone()
    if teacher is None:
        abort(404)
    return render_template("edit_teacher.html", teacher=teacher)


@app.route("/teacher-dashboard")
@role_required("teacher")
def teacher_dashboard():
    with database_cursor() as (_, cursor):
        teacher = teacher_for_session(cursor)
        if teacher is None:
            session.clear()
            flash("Your teacher account is no longer available.", "error")
            return redirect(url_for("login"))

        cursor.execute(
            "SELECT COUNT(*) AS total FROM students WHERE class=%s",
            (teacher["class"],),
        )
        total_students = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) AS present,
                SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) AS absent
            FROM attendance a
            JOIN students s ON s.id=a.student_id
            WHERE a.date=%s AND s.class=%s
            """,
            (date.today(), teacher["class"]),
        )
        totals = cursor.fetchone()
        present_today = totals["present"] or 0
        absent_today = totals["absent"] or 0

    return render_template(
        "teacher_dashboard.html",
        teacher_name=teacher["name"],
        class_name=teacher["class"],
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today,
        current_date=date.today(),
    )


@app.route("/students")
@role_required("teacher")
def students():
    with database_cursor() as (_, cursor):
        teacher = teacher_for_session(cursor)
        if teacher is None:
            abort(404)
        cursor.execute(
            "SELECT id, roll_no, name, class FROM students WHERE class=%s ORDER BY roll_no",
            (teacher["class"],),
        )
        student_rows = cursor.fetchall()
    return render_template(
        "students.html", students=student_rows, class_name=teacher["class"]
    )


@app.route("/add-student", methods=["GET", "POST"])
@role_required("teacher")
def add_student():
    with database_cursor() as (connection, cursor):
        teacher = teacher_for_session(cursor)
        if teacher is None:
            abort(404)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Enter a student name.", "error")
            else:
                cursor.execute(
                    "SELECT COALESCE(MAX(roll_no), 0) + 1 AS next_roll "
                    "FROM students WHERE class=%s",
                    (teacher["class"],),
                )
                roll_no = cursor.fetchone()["next_roll"]
                cursor.execute(
                    "INSERT INTO students (roll_no,name,class) VALUES (%s,%s,%s)",
                    (roll_no, name, teacher["class"]),
                )
                connection.commit()
                flash(f"{name} was added to {teacher['class']}.", "success")
                return redirect(url_for("students"))

    return render_template("add_student.html", class_name=teacher["class"])


@app.route("/edit-student/<int:id>", methods=["GET", "POST"])
@role_required("teacher")
def edit_student(id):
    with database_cursor() as (connection, cursor):
        teacher = teacher_for_session(cursor)
        if teacher is None:
            abort(404)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Enter a student name.", "error")
            else:
                cursor.execute(
                    "SELECT id FROM students WHERE id=%s AND class=%s",
                    (id, teacher["class"]),
                )
                if cursor.fetchone() is None:
                    abort(404)
                cursor.execute(
                    "UPDATE students SET name=%s WHERE id=%s AND class=%s",
                    (name, id, teacher["class"]),
                )
                connection.commit()
                flash("Student details updated.", "success")
                return redirect(url_for("students"))

        cursor.execute(
            "SELECT id, roll_no, name, class FROM students WHERE id=%s AND class=%s",
            (id, teacher["class"]),
        )
        student = cursor.fetchone()
    if student is None:
        abort(404)
    return render_template("edit_student.html", student=student)


@app.route("/delete-student/<int:id>", methods=["POST"])
@role_required("teacher")
def delete_student(id):
    with database_cursor() as (connection, cursor):
        teacher = teacher_for_session(cursor)
        if teacher is None:
            abort(404)
        cursor.execute(
            "SELECT id FROM students WHERE id=%s AND class=%s",
            (id, teacher["class"]),
        )
        if cursor.fetchone() is None:
            abort(404)
        cursor.execute("DELETE FROM attendance WHERE student_id=%s", (id,))
        cursor.execute("DELETE FROM students WHERE id=%s", (id,))
        connection.commit()
    flash("Student and their attendance history were deleted.", "success")
    return redirect(url_for("students"))


@app.route("/mark-attendance", methods=["GET", "POST"])
@role_required("teacher")
def mark_attendance():
    selected_date = request.form.get("date") if request.method == "POST" else request.args.get(
        "date", date.today().isoformat()
    )
    parsed_date = parse_report_date(selected_date)
    if parsed_date is None:
        return redirect(url_for("mark_attendance"))

    with database_cursor() as (connection, cursor):
        teacher = teacher_for_session(cursor)
        if teacher is None:
            abort(404)
        cursor.execute(
            "SELECT id, roll_no, name FROM students WHERE class=%s ORDER BY roll_no",
            (teacher["class"],),
        )
        student_rows = cursor.fetchall()

        if request.method == "POST":
            statuses = []
            for student in student_rows:
                status = request.form.get(f"student_{student['id']}")
                if status not in {"Present", "Absent"}:
                    flash("Choose Present or Absent for every student.", "error")
                    return render_template(
                        "mark_attendance.html",
                        students=student_rows,
                        selected_date=parsed_date.isoformat(),
                        class_name=teacher["class"],
                        saved_statuses={},
                    )
                statuses.append((student["id"], parsed_date, status, status))

            if statuses:
                cursor.executemany(
                    """
                    INSERT INTO attendance (student_id,date,status)
                    VALUES (%s,%s,%s)
                    ON DUPLICATE KEY UPDATE status=%s
                    """,
                    statuses,
                )
                connection.commit()
            flash(f"Attendance saved for {parsed_date.isoformat()}.", "success")
            return redirect(
                url_for("attendance_report_page", date=parsed_date.isoformat())
            )

        cursor.execute(
            """
            SELECT a.student_id, a.status
            FROM attendance a
            JOIN students s ON s.id=a.student_id
            WHERE s.class=%s AND a.date=%s
            """,
            (teacher["class"], parsed_date),
        )
        saved_statuses = {
            row["student_id"]: row["status"] for row in cursor.fetchall()
        }

    return render_template(
        "mark_attendance.html",
        students=student_rows,
        selected_date=parsed_date.isoformat(),
        class_name=teacher["class"],
        saved_statuses=saved_statuses,
    )


@app.route("/view-student/<int:id>")
@role_required("teacher")
def view_student(id):
    with database_cursor() as (_, cursor):
        teacher = teacher_for_session(cursor)
        if teacher is None:
            abort(404)
        cursor.execute(
            "SELECT id, roll_no, name, class FROM students WHERE id=%s AND class=%s",
            (id, teacher["class"]),
        )
        student = cursor.fetchone()
        if student is None:
            abort(404)
        cursor.execute(
            "SELECT date, status FROM attendance WHERE student_id=%s ORDER BY date DESC",
            (id,),
        )
        records = cursor.fetchall()

    total_classes = len(records)
    present_count = sum(record["status"] == "Present" for record in records)
    percentage = round(present_count / total_classes * 100, 1) if total_classes else 0
    return render_template(
        "view_student.html",
        student=student,
        records=records,
        present_count=present_count,
        total_classes=total_classes,
        percentage=percentage,
    )


@app.route("/admin-students")
@role_required("admin")
def admin_students():
    with database_cursor() as (_, cursor):
        cursor.execute(
            "SELECT id, roll_no, name, class FROM students ORDER BY class, roll_no"
        )
        student_rows = cursor.fetchall()
    return render_template(
        "admin_students.html",
        students=student_rows,
        total_students=len(student_rows),
    )


@app.route("/attendance-report")
def attendance_report_page():
    is_admin = "admin_id" in session
    is_teacher = "teacher_id" in session
    if not is_admin and not is_teacher:
        flash("Please sign in to view attendance reports.", "error")
        return redirect(url_for("login"))

    selected_date = request.args.get("date", date.today().isoformat())
    parsed_date = parse_report_date(selected_date)
    if parsed_date is None:
        return redirect(url_for("attendance_report_page"))

    with database_cursor() as (_, cursor):
        class_name = None
        classes = []
        if is_teacher:
            teacher = teacher_for_session(cursor)
            if teacher is None:
                abort(404)
            class_name = teacher["class"]
        else:
            cursor.execute("SELECT DISTINCT class FROM students ORDER BY class")
            classes = [row["class"] for row in cursor.fetchall()]
            class_name = request.args.get("class_name", "").strip() or None
            if class_name and class_name not in classes:
                flash("Choose a class from the list.", "error")
                return redirect(url_for("attendance_report_page"))

        rows = attendance_report(cursor, parsed_date, class_name)

    return render_template(
        "attendance_report.html",
        records=rows,
        selected_date=parsed_date.isoformat(),
        class_name=class_name,
        classes=classes,
        is_admin=is_admin,
        present_count=sum(row["status"] == "Present" for row in rows),
        absent_count=sum(row["status"] == "Absent" for row in rows),
        unmarked_count=sum(row["status"] == "Not marked" for row in rows),
    )


@app.route("/attendance-report.csv")
def export_attendance_report():
    is_admin = "admin_id" in session
    is_teacher = "teacher_id" in session
    if not is_admin and not is_teacher:
        flash("Please sign in to export attendance reports.", "error")
        return redirect(url_for("login"))

    parsed_date = parse_report_date(request.args.get("date", date.today().isoformat()))
    if parsed_date is None:
        return redirect(url_for("attendance_report_page"))

    with database_cursor() as (_, cursor):
        class_name = None
        if is_teacher:
            teacher = teacher_for_session(cursor)
            if teacher is None:
                abort(404)
            class_name = teacher["class"]
        else:
            class_name = request.args.get("class_name", "").strip() or None
            if class_name:
                cursor.execute("SELECT 1 FROM students WHERE class=%s LIMIT 1", (class_name,))
                if cursor.fetchone() is None:
                    abort(404)
        rows = attendance_report(cursor, parsed_date, class_name)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Roll number", "Student", "Class", "Status"])
    for row in rows:
        writer.writerow(
            [
                parsed_date.isoformat(),
                row["roll_no"],
                safe_spreadsheet_value(row["name"]),
                safe_spreadsheet_value(row["class"]),
                row["status"],
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=attendance-{parsed_date.isoformat()}.csv"
            )
        },
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() == "true")
