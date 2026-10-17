import re
import unittest
from datetime import date

from flask import render_template
from werkzeug.security import generate_password_hash

from app import app, password_matches, safe_spreadsheet_value


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()

    def test_login_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sign in to ClassPulse", response.data)
        self.assertNotIn(b'<header class="topbar">', response.data)

    def test_teacher_dashboard_requires_sign_in(self):
        response = self.client.get("/teacher-dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_admin_dashboard_requires_sign_in(self):
        response = self.client.get("/admin-dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_report_requires_sign_in(self):
        response = self.client.get("/attendance-report")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_login_form_has_csrf_token(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="csrf_token"', response.data)

    def test_login_rejects_a_post_without_a_csrf_token(self):
        response = self.client.post("/", data={"email": "", "password": ""})
        self.assertEqual(response.status_code, 400)

    def test_empty_login_shows_feedback_in_the_login_card(self):
        page = self.client.get("/")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1)
        response = self.client.post(
            "/",
            data={"csrf_token": token, "email": "", "password": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enter your email and password.", response.data)

    def test_all_pages_render_with_their_expected_context(self):
        contexts = {
            "login.html": {},
            "admin_dashboard.html": {
                "total_teachers": 1,
                "total_students": 2,
                "attendance_today": 1,
                "current_date": date.today(),
            },
            "teacher_dashboard.html": {
                "teacher_name": "Teacher",
                "class_name": "Grade 8A",
                "total_students": 2,
                "present_today": 1,
                "absent_today": 1,
                "current_date": date.today(),
            },
            "students.html": {"students": [], "class_name": "Grade 8A"},
            "add_student.html": {"class_name": "Grade 8A"},
            "edit_student.html": {
                "student": {"roll_no": 1, "name": "Student", "class": "Grade 8A"}
            },
            "manage_teachers.html": {"teachers": []},
            "edit_teacher.html": {
                "teacher": {
                    "id": 1,
                    "name": "Teacher",
                    "email": "teacher@example.com",
                    "class": "Grade 8A",
                }
            },
            "admin_students.html": {"students": [], "total_students": 0},
            "mark_attendance.html": {
                "students": [],
                "selected_date": date.today().isoformat(),
                "class_name": "Grade 8A",
                "saved_statuses": {},
            },
            "view_student.html": {
                "student": {
                    "name": "Student",
                    "roll_no": 1,
                    "class": "Grade 8A",
                },
                "records": [],
                "present_count": 0,
                "total_classes": 0,
                "percentage": 0,
            },
            "attendance_report.html": {
                "records": [],
                "selected_date": date.today().isoformat(),
                "class_name": None,
                "classes": [],
                "is_admin": True,
                "present_count": 0,
                "absent_count": 0,
                "unmarked_count": 0,
            },
        }

        with app.test_request_context("/"):
            for template_name, context in contexts.items():
                with self.subTest(template=template_name):
                    self.assertTrue(render_template(template_name, **context))

    def test_password_verification_supports_hashes_and_legacy_values(self):
        password = "correct horse battery staple"
        self.assertEqual(password_matches(generate_password_hash(password), password), (True, False))
        self.assertEqual(password_matches(password, password), (True, True))
        self.assertEqual(password_matches("different-password", password), (False, False))

    def test_csv_cells_cannot_start_spreadsheet_formulas(self):
        self.assertEqual(safe_spreadsheet_value("=1+1"), "'=1+1")
        self.assertEqual(safe_spreadsheet_value("  @SUM(A1:A2)"), "'  @SUM(A1:A2)")
        self.assertEqual(safe_spreadsheet_value("Grade 8A"), "Grade 8A")


if __name__ == "__main__":
    unittest.main()
