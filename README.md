# ClassPulse Attendance System

A Flask and MySQL attendance application for school administrators and teachers. Administrators manage teacher accounts and browse the school-wide student directory. Teachers maintain their class roster, record daily attendance, view student histories, and export attendance reports.

## Features

- Separate administrator and teacher workspaces.
- Class-scoped student management and daily attendance.
- Existing attendance can be loaded and corrected by date.
- Attendance summaries, searchable rosters, and CSV reports.
- Responsive pages designed for desktop, tablet, and mobile.
- CSRF protection on sign-in and data-changing forms.
- Password hashing for newly created teacher accounts, with automatic upgrade of legacy plain-text passwords at successful sign-in.
- Environment-based database and session configuration.

## Requirements

- Python 3.10 or newer
- MySQL 8.0 or compatible

## Run locally (Windows PowerShell)

1. Clone this repository and open its folder in PowerShell.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Create a local environment file and update the values for your MySQL server:

   ```powershell
   Copy-Item .env.example .env
   ```

   Use a unique, random `SECRET_KEY` value. The `.env` file is ignored by Git and should never be committed.

5. Create the database and tables by running `schema.sql` in MySQL Workbench or your MySQL client. The script creates the `attendance_system` database and ensures password columns can store secure hashes; back up existing data before running it against an existing installation.
6. Create the first administrator. Generate a password hash:

   ```powershell
   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('replace-this-password'))"
   ```

   Insert the generated hash (not the original password) into MySQL:

   ```sql
   INSERT INTO admins (email, password)
   VALUES ('admin@school.example', 'paste-the-generated-hash-here');
   ```

7. Start the app:

   ```powershell
   python app.py
   ```

   Open <http://127.0.0.1:5000>.

## Configuration

The application reads these values from environment variables (a local `.env` file is loaded automatically):

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | Random for each process | Protects Flask sessions; set a persistent random value for local use and a secret value in deployment. |
| `DB_HOST` | `localhost` | MySQL server host |
| `DB_PORT` | `3306` | MySQL server port |
| `DB_USER` | `root` | MySQL account |
| `DB_PASSWORD` | Empty | MySQL password |
| `DB_NAME` | `attendance_system` | Database name |
| `FLASK_DEBUG` | `false` | Set to `true` only for local development. |

For deployment, configure these values in your hosting provider's secret/environment settings. Do not commit `.env`, production credentials, or database dumps.

## Tests

Run the lightweight application and route tests:

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions runs these tests and a Python syntax compilation check on pushes and pull requests.

## GitHub publishing checklist

- Keep `.env` and all real credentials out of commits.
- Set a persistent `SECRET_KEY` and `FLASK_DEBUG=false` in deployment.
- Use a dedicated MySQL account with only the permissions the app needs.
- Back up the database before applying schema changes.
- Serve the app through a production WSGI server and HTTPS; Flask's built-in development server is for local use only.
