from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
    send_file,
    send_from_directory
)

import sqlite3
import os
import math
from functools import wraps
from datetime import datetime
from werkzeug.utils import secure_filename


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

app.secret_key = "emergency_assistance_secret_key"


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EMERGENCY_DB = os.path.join(
    BASE_DIR,
    "emergency.db"
)

LEGACY_DB = os.path.join(
    BASE_DIR,
    "database.db"
)

if os.path.exists(EMERGENCY_DB):
    DATABASE = EMERGENCY_DB
else:
    DATABASE = LEGACY_DB


UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "static",
    "uploads"
)

REPORT_FOLDER = os.path.join(
    BASE_DIR,
    "static",
    "reports"
)


os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

os.makedirs(
    REPORT_FOLDER,
    exist_ok=True
)


app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["MAX_CONTENT_LENGTH"] = (
    10 * 1024 * 1024
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_db():

    conn = sqlite3.connect(
        DATABASE
    )

    conn.row_factory = sqlite3.Row

    return conn


def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def has_column(
    conn,
    table,
    column
):

    rows = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(
        row["name"] == column
        for row in rows
    )


def add_column(
    conn,
    table,
    column,
    definition
):

    if not has_column(
        conn,
        table,
        column
    ):

        conn.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_database():

    conn = get_db()

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
        """
    )

    add_column(
        conn,
        "users",
        "role",
        "TEXT DEFAULT 'user'"
    )


    # --------------------------------------------------------
    # RESPONDERS
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS responders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            phone TEXT NOT NULL,
            status TEXT DEFAULT 'Available',
            created_at TEXT,
            latitude REAL,
            longitude REAL,
            login_username TEXT,
            login_password TEXT
        )
        """
    )

    add_column(
        conn,
        "responders",
        "latitude",
        "REAL"
    )

    add_column(
        conn,
        "responders",
        "longitude",
        "REAL"
    )

    add_column(
        conn,
        "responders",
        "login_username",
        "TEXT"
    )

    add_column(
        conn,
        "responders",
        "login_password",
        "TEXT"
    )


    # --------------------------------------------------------
    # STATIONS
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            latitude REAL,
            longitude REAL,
            status TEXT DEFAULT 'Active',
            created_at TEXT
        )
        """
    )


    # --------------------------------------------------------
    # EMERGENCIES
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS emergencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            emergency_type TEXT,
            location TEXT,
            severity TEXT,
            description TEXT,
            status TEXT DEFAULT 'Reported',
            responder TEXT,
            responder_id INTEGER,
            created_at TEXT,
            user_id INTEGER,
            rating INTEGER,
            photo TEXT,
            resolution_notes TEXT,
            completed_at TEXT,
            reporter_name TEXT,
            address TEXT,
            latitude REAL,
            longitude REAL
        )
        """
    )

    emergency_columns = [

        ("latitude", "REAL"),

        ("longitude", "REAL"),

        ("reporter_name", "TEXT"),

        ("address", "TEXT"),

        ("rating", "INTEGER"),

        ("photo", "TEXT"),

        ("resolution_notes", "TEXT"),

        ("completed_at", "TEXT"),

        ("responder_id", "INTEGER"),

        ("user_id", "INTEGER")
    ]

    for column, definition in emergency_columns:

        add_column(
            conn,
            "emergencies",
            column,
            definition
        )


    # --------------------------------------------------------
    # EMERGENCY HISTORY
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS emergency_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emergency_id INTEGER,
            old_status TEXT,
            new_status TEXT,
            note TEXT,
            changed_at TEXT
        )
        """
    )

    add_column(
        conn,
        "emergency_history",
        "changed_at",
        "TEXT"
    )


    # --------------------------------------------------------
    # MULTIPLE RESPONDERS
    # --------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS emergency_responders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emergency_id INTEGER NOT NULL,
            responder_id INTEGER NOT NULL,
            department TEXT,
            status TEXT DEFAULT 'Dispatched',
            assigned_at TEXT,
            accepted_at TEXT,
            completed_at TEXT,
            distance_km REAL,
            UNIQUE(emergency_id, responder_id)
        )
        """
    )


    # --------------------------------------------------------
    # REPAIR ADMIN
    # --------------------------------------------------------

    admin = conn.execute(
        """
        SELECT *
        FROM users
        WHERE
            email = ?
            OR name = ?
            OR role = 'admin'
        ORDER BY
            CASE
                WHEN role = 'admin' THEN 0
                ELSE 1
            END,
            id ASC
        LIMIT 1
        """,
        (
            "admin@emergency.com",
            "Nikky"
        )
    ).fetchone()


    if admin is None:

        conn.execute(
            """
            INSERT INTO users
            (
                name,
                email,
                password,
                role
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "Nikky",
                "admin@emergency.com",
                "Kaila2808",
                "admin"
            )
        )

    else:

        conn.execute(
            """
            UPDATE users
            SET
                name = ?,
                email = ?,
                password = ?,
                role = 'admin'
            WHERE id = ?
            """,
            (
                "Nikky",
                "admin@emergency.com",
                "Kaila2808",
                admin["id"]
            )
        )


    conn.commit()

    conn.close()


# ============================================================
# LOGIN DECORATORS
# ============================================================

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if session.get("role") != "admin":

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


def responder_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if session.get("role") != "responder":

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# HOME
# ============================================================

@app.route("/")
@app.route("/home")
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "GET":

        # Inline registration page.
        # This avoids another template error if register.html
        # is missing.

        return """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Create Account | Emergency Assistance</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f4f6fa;
    font-family: Arial, sans-serif;
    padding: 20px;
}

.card {
    width: 100%;
    max-width: 460px;
    background: white;
    padding: 35px;
    border-radius: 22px;
    box-shadow: 0 20px 60px rgba(0,0,0,.12);
}

.logo {
    text-align: center;
    font-size: 48px;
}

h1 {
    text-align: center;
    color: #111827;
    margin-bottom: 8px;
}

.subtitle {
    text-align: center;
    color: #667085;
    margin-bottom: 28px;
}

label {
    display: block;
    font-weight: bold;
    margin-bottom: 7px;
    color: #344054;
}

input {
    width: 100%;
    padding: 14px;
    border: 1px solid #d0d5dd;
    border-radius: 12px;
    margin-bottom: 18px;
    font-size: 15px;
}

button {
    width: 100%;
    border: none;
    background: #dc2626;
    color: white;
    padding: 15px;
    border-radius: 12px;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
}

button:hover {
    background: #b91c1c;
}

.login {
    display: block;
    text-align: center;
    margin-top: 20px;
    color: #344054;
    text-decoration: none;
}

</style>

</head>

<body>

<div class="card">

<div class="logo">
🚨
</div>

<h1>
Create Account
</h1>

<div class="subtitle">
Emergency Assistance
</div>

<form method="POST">

<label>
Name
</label>

<input
    type="text"
    name="name"
    placeholder="Enter your name"
    required
>

<label>
Email
</label>

<input
    type="email"
    name="email"
    placeholder="Enter your email"
    required
>

<label>
Password
</label>

<input
    type="password"
    name="password"
    placeholder="Create a password"
    required
>

<button type="submit">
CREATE ACCOUNT
</button>

</form>

<a
    class="login"
    href="/login"
>
Already have an account? Login
</a>

</div>

</body>
</html>
"""


    name = request.form.get(
        "name",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    ).strip()


    if not name:

        flash(
            "Please enter your name.",
            "error"
        )

        return redirect(
            url_for("register")
        )


    if not email:

        flash(
            "Please enter your email.",
            "error"
        )

        return redirect(
            url_for("register")
        )


    if not password:

        flash(
            "Please enter a password.",
            "error"
        )

        return redirect(
            url_for("register")
        )


    conn = get_db()


    existing = conn.execute(
        """
        SELECT id
        FROM users
        WHERE LOWER(email) = ?
        LIMIT 1
        """,
        (email,)
    ).fetchone()


    if existing:

        conn.close()

        flash(
            "This email is already registered.",
            "error"
        )

        return redirect(
            url_for("register")
        )


    conn.execute(
        """
        INSERT INTO users
        (
            name,
            email,
            password,
            role
        )
        VALUES (?, ?, ?, 'user')
        """,
        (
            name,
            email,
            password
        )
    )

    conn.commit()

    conn.close()


    flash(
        "Account created successfully. Please login.",
        "success"
    )


    return redirect(
        url_for("login")
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "GET":

        return render_template(
            "login.html"
        )


    username = request.form.get(
        "username",
        ""
    ).strip()


    if not username:

        username = request.form.get(
            "email",
            ""
        ).strip()


    password = request.form.get(
        "password",
        ""
    ).strip()


    if not username or not password:

        flash(
            "Please enter username/email and password.",
            "error"
        )

        return redirect(
            url_for("login")
        )


    conn = get_db()


    # --------------------------------------------------------
    # ADMIN / USER LOGIN
    # --------------------------------------------------------

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE
            (
                name = ?
                OR email = ?
            )
            AND password = ?
        LIMIT 1
        """,
        (
            username,
            username,
            password
        )
    ).fetchone()


    if user:

        conn.close()

        session.clear()

        session["user_id"] = user["id"]

        session["user_name"] = user["name"]

        session["role"] = user["role"]


        if user["role"] == "admin":

            return redirect(
                url_for("admin")
            )


        return redirect(
            url_for("user_dashboard")
        )


    # --------------------------------------------------------
    # RESPONDER LOGIN
    # --------------------------------------------------------

    responder = conn.execute(
        """
        SELECT *
        FROM responders
        WHERE
            login_username = ?
            AND login_password = ?
        LIMIT 1
        """,
        (
            username,
            password
        )
    ).fetchone()


    conn.close()


    if responder:

        session.clear()

        session["user_id"] = responder["id"]

        session["user_name"] = responder["name"]

        session["responder_id"] = responder["id"]

        session["role"] = "responder"

        session["department"] = responder["department"]


        return redirect(
            url_for("responder_dashboard")
        )


    flash(
        "Invalid username or password.",
        "error"
    )


    return redirect(
        url_for("login")
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# ============================================================
# DISTANCE CALCULATION
# ============================================================

def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    if (
        lat1 is None
        or lon1 is None
        or lat2 is None
        or lon2 is None
    ):

        return None


    try:

        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)

    except (
        TypeError,
        ValueError
    ):

        return None


    radius = 6371.0


    dlat = math.radians(
        lat2 - lat1
    )

    dlon = math.radians(
        lon2 - lon1
    )


    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )


    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


    return radius * c


# ============================================================
# DEPARTMENT MATCHING
# ============================================================

def department_matches(
    emergency_type,
    department
):

    emergency_type = (
        emergency_type or ""
    ).strip().lower()

    department = (
        department or ""
    ).strip().lower()


    # --------------------------------------------------------
    # WOMEN SAFETY
    # POLICE ONLY
    # --------------------------------------------------------

    if emergency_type == "women safety":

        return "police" in department


    # --------------------------------------------------------
    # ACCIDENT
    # --------------------------------------------------------

    if emergency_type == "accident":

        return any(
            word in department
            for word in (
                "police",
                "ambulance",
                "medical",
                "fire",
                "rescue"
            )
        )


    # --------------------------------------------------------
    # FIRE
    # --------------------------------------------------------

    if emergency_type == "fire":

        return (
            "fire" in department
            or "rescue" in department
        )


    # --------------------------------------------------------
    # MEDICAL
    # --------------------------------------------------------

    if emergency_type == "medical":

        return any(
            word in department
            for word in (
                "ambulance",
                "medical",
                "hospital"
            )
        )


    # --------------------------------------------------------
    # POLICE
    # --------------------------------------------------------

    if emergency_type == "police":

        return "police" in department


    # --------------------------------------------------------
    # OTHER
    # --------------------------------------------------------

    return True


# ============================================================
# ADD HISTORY
# ============================================================

def add_history(
    emergency_id,
    old_status,
    new_status,
    note=""
):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO emergency_history
        (
            emergency_id,
            old_status,
            new_status,
            note,
            changed_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            emergency_id,
            old_status,
            new_status,
            note,
            now()
        )
    )

    conn.commit()

    conn.close()


# ============================================================
# MULTIPLE RESPONDER DISPATCH
# ============================================================

def dispatch_multiple_responders(
    emergency_id,
    emergency_type,
    latitude=None,
    longitude=None
):

    conn = get_db()


    responders = conn.execute(
        """
        SELECT *
        FROM responders
        WHERE LOWER(
            COALESCE(status, 'Available')
        ) = 'available'
        ORDER BY id
        """
    ).fetchall()


    selected = []


    for responder in responders:

        if not department_matches(
            emergency_type,
            responder["department"]
        ):

            continue


        distance = distance_km(
            latitude,
            longitude,
            responder["latitude"],
            responder["longitude"]
        )


        if distance is None:

            distance = 10**9


        selected.append(
            (
                distance,
                responder
            )
        )


    selected.sort(
        key=lambda item: item[0]
    )


    # ========================================================
    # WOMEN SAFETY
    # POLICE ONLY
    # MULTIPLE POLICE ARE ALLOWED
    # ========================================================

    if (
        emergency_type or ""
    ).strip().lower() == "women safety":

        chosen = [

            item

            for item in selected

            if "police"
            in (
                item[1]["department"]
                or ""
            ).lower()
        ]


    else:

        # ====================================================
        # NORMAL EMERGENCIES
        # ONE FROM EACH SERVICE FAMILY
        # ====================================================

        families = set()

        chosen = []


        for distance, responder in selected:

            department = (
                responder["department"]
                or ""
            ).lower()


            if "police" in department:

                family = "police"

            elif any(
                word in department
                for word in (
                    "ambulance",
                    "medical",
                    "hospital"
                )
            ):

                family = "medical"

            elif any(
                word in department
                for word in (
                    "fire",
                    "rescue"
                )
            ):

                family = "fire"

            else:

                family = (
                    department
                    or "other"
                )


            if family in families:

                continue


            families.add(
                family
            )

            chosen.append(
                (
                    distance,
                    responder
                )
            )


    if not chosen:

        conn.close()

        return []


    # ========================================================
    # PRIMARY RESPONDER
    # ========================================================

    primary = chosen[0][1]


    conn.execute(
        """
        UPDATE emergencies
        SET
            responder = ?,
            responder_id = ?,
            status = 'Assigned'
        WHERE id = ?
        """,
        (
            primary["name"],
            primary["id"],
            emergency_id
        )
    )


    # ========================================================
    # ADD ALL RESPONDERS
    # ========================================================

    for distance, responder in chosen:

        conn.execute(
            """
            INSERT OR IGNORE INTO emergency_responders
            (
                emergency_id,
                responder_id,
                department,
                status,
                assigned_at,
                distance_km
            )
            VALUES
            (
                ?,
                ?,
                ?,
                'Dispatched',
                ?,
                ?
            )
            """,
            (
                emergency_id,
                responder["id"],
                responder["department"],
                now(),
                None
                if distance >= 10**9
                else distance
            )
        )


        conn.execute(
            """
            UPDATE responders
            SET status = 'Busy'
            WHERE id = ?
            """,
            (
                responder["id"],
            )
        )


    conn.commit()

    conn.close()


    if (
        emergency_type or ""
    ).strip().lower() == "women safety":

        history_text = (
            "Police responders dispatched: "
        )

    else:

        history_text = (
            "Multiple responders dispatched: "
        )


    history_text += ", ".join(
        responder["name"]
        for _, responder in chosen
    )


    add_history(
        emergency_id,
        "Reported",
        "Assigned",
        history_text
    )


    return chosen


# ============================================================
# REPORT EMERGENCY
# ============================================================

@app.route(
    "/report",
    methods=["GET", "POST"]
)
def report():

    if request.method == "GET":

        return render_template(
            "report.html"
        )


    name = request.form.get(
        "name",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    emergency_type = request.form.get(
        "emergency_type",
        ""
    ).strip()

    location = request.form.get(
        "location",
        ""
    ).strip()

    address = request.form.get(
        "address",
        ""
    ).strip()

    severity = request.form.get(
        "severity",
        "Medium"
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()


    latitude = request.form.get(
        "latitude"
    )

    longitude = request.form.get(
        "longitude"
    )


    photo_name = None

    photo = request.files.get(
        "photo"
    )


    if photo and photo.filename:

        filename = secure_filename(
            photo.filename
        )


        photo_name = (
            datetime.now().strftime(
                "%Y%m%d%H%M%S"
            )
            + "_"
            + filename
        )


        photo.save(
            os.path.join(
                UPLOAD_FOLDER,
                photo_name
            )
        )


    reason = request.form.get(
        "reason",
        ""
    ).strip()


    if emergency_type == "Women Safety":

        description = (
            "Women Safety SOS"
            + (
                f": {reason}"
                if reason
                else ""
            )
            + ". Police responders only."
        )

    elif not description:

        description = (
            "Emergency reported."
        )


    conn = get_db()


    cursor = conn.execute(
        """
        INSERT INTO emergencies
        (
            name,
            phone,
            emergency_type,
            location,
            severity,
            description,
            status,
            created_at,
            photo,
            reporter_name,
            address,
            latitude,
            longitude,
            user_id
        )
        VALUES
        (
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            'Reported',
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            name,
            phone,
            emergency_type,
            location,
            severity,
            description,
            now(),
            photo_name,
            name,
            address,
            latitude,
            longitude,
            session.get("user_id")
        )
    )


    emergency_id = cursor.lastrowid


    conn.commit()

    conn.close()


    add_history(
        emergency_id,
        "",
        "Reported",
        "Emergency reported"
    )


    dispatch_multiple_responders(
        emergency_id,
        emergency_type,
        latitude,
        longitude
    )


    return redirect(
        url_for(
            "emergency_details",
            emergency_id=emergency_id
        )
    )


# ============================================================
# QUICK SOS
# ============================================================

@app.route(
    "/sos",
    methods=["POST"]
)
def sos():

    emergency_type = request.form.get(
        "emergency_type",
        "Other"
    ).strip()


    allowed_types = [

        "Accident",

        "Fire",

        "Medical",

        "Police",

        "Women Safety",

        "Other"
    ]


    if emergency_type not in allowed_types:

        emergency_type = "Other"


    latitude = request.form.get(
        "latitude",
        ""
    ).strip()


    longitude = request.form.get(
        "longitude",
        ""
    ).strip()


    if latitude and longitude:

        location = (
            f"{latitude}, {longitude}"
        )

    else:

        location = (
            "Location unavailable"
        )


    if emergency_type in (
        "Accident",
        "Fire",
        "Medical",
        "Women Safety"
    ):

        severity = "Critical"

    else:

        severity = "High"


    # IMPORTANT:
    # This fixes the old undefined `description` error.

    if emergency_type == "Women Safety":

        description = (
            "Women Safety SOS. "
            "Police responders only."
        )

    else:

        description = (
            f"{emergency_type} "
            "emergency reported using SOS button."
        )


    conn = get_db()


    cursor = conn.execute(
        """
        INSERT INTO emergencies
        (
            name,
            phone,
            emergency_type,
            location,
            severity,
            description,
            status,
            created_at,
            reporter_name,
            address,
            latitude,
            longitude,
            user_id
        )
        VALUES
        (
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            'Reported',
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            "SOS User",
            "",
            emergency_type,
            location,
            severity,
            description,
            now(),
            "SOS User",
            location,
            latitude or None,
            longitude or None,
            session.get("user_id")
        )
    )


    emergency_id = cursor.lastrowid


    conn.commit()

    conn.close()


    add_history(
        emergency_id,
        "",
        "Reported",
        "Emergency reported using SOS"
    )


    chosen = dispatch_multiple_responders(
        emergency_id,
        emergency_type,
        latitude,
        longitude
    )


    responder_list = []


    for distance, responder in chosen:

        responder_list.append(
            {
                "id": responder["id"],
                "name": responder["name"],
                "department": responder["department"],
                "phone": responder["phone"],
                "distance_km":
                    None
                    if distance >= 10**9
                    else round(
                        distance,
                        2
                    )
            }
        )


    return jsonify(
        {
            "success": True,

            "emergency_id":
                emergency_id,

            "emergency_type":
                emergency_type,

            "responders":
                responder_list,

            "responder":
                (
                    responder_list[0]["name"]
                    if responder_list
                    else None
                ),

            "message":
                (
                    "Women Safety alert sent "
                    "to police responders."
                    if emergency_type
                    == "Women Safety"
                    else
                    "Emergency alert sent successfully."
                )
        }
    )


# ============================================================
# WOMEN SAFETY
# ============================================================

@app.route(
    "/women-safety",
    methods=["POST"]
)
def women_safety():

    latitude = request.form.get(
        "latitude",
        ""
    ).strip()

    longitude = request.form.get(
        "longitude",
        ""
    ).strip()

    reason = request.form.get(
        "reason",
        "Feeling Unsafe"
    ).strip()


    if latitude and longitude:

        location = (
            f"{latitude}, {longitude}"
        )

    else:

        location = (
            "Location unavailable"
        )


    description = (
        "Women Safety SOS"
        + (
            f": {reason}"
            if reason
            else ""
        )
        + ". Police responders only."
    )


    conn = get_db()


    cursor = conn.execute(
        """
        INSERT INTO emergencies
        (
            name,
            phone,
            emergency_type,
            location,
            severity,
            description,
            status,
            created_at,
            reporter_name,
            address,
            latitude,
            longitude,
            user_id
        )
        VALUES
        (
            ?,
            ?,
            'Women Safety',
            ?,
            'Critical',
            ?,
            'Reported',
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            "Women Safety User",
            "",
            location,
            description,
            now(),
            "Women Safety User",
            location,
            latitude or None,
            longitude or None,
            session.get("user_id")
        )
    )


    emergency_id = cursor.lastrowid


    conn.commit()

    conn.close()


    add_history(
        emergency_id,
        "",
        "Reported",
        description
    )


    chosen = dispatch_multiple_responders(
        emergency_id,
        "Women Safety",
        latitude,
        longitude
    )


    responders = []


    for distance, responder in chosen:

        responders.append(
            {
                "id": responder["id"],
                "name": responder["name"],
                "department":
                    responder["department"],
                "phone":
                    responder["phone"],
                "distance_km":
                    None
                    if distance >= 10**9
                    else round(
                        distance,
                        2
                    )
            }
        )


    return jsonify(
        {
            "success": True,

            "emergency_id":
                emergency_id,

            "emergency_type":
                "Women Safety",

            "status":
                (
                    "Assigned"
                    if chosen
                    else "Reported"
                ),

            "responders":
                responders,

            "responder_name":
                (
                    responders[0]["name"]
                    if responders
                    else None
                ),

            "responder_department":
                (
                    responders[0]["department"]
                    if responders
                    else "Police"
                ),

            "responder_phone":
                (
                    responders[0]["phone"]
                    if responders
                    else None
                ),

            "message":
                (
                    "Women Safety alert sent "
                    "to police responders."
                    if chosen
                    else
                    "No police responder is "
                    "currently available."
                )
        }
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    conn = get_db()


    emergencies = conn.execute(
        """
        SELECT
            e.*,
            r.name AS responder_name
        FROM emergencies e
        LEFT JOIN responders r
            ON e.responder_id = r.id
        ORDER BY e.id DESC
        """
    ).fetchall()


    responders = conn.execute(
        """
        SELECT *
        FROM responders
        ORDER BY name
        """
    ).fetchall()


    stations = conn.execute(
        """
        SELECT *
        FROM stations
        ORDER BY name
        """
    ).fetchall()


    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        """
    ).fetchone()[0]


    reported = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        WHERE status = 'Reported'
        """
    ).fetchone()[0]


    assigned = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        WHERE status IN
        (
            'Assigned',
            'Accepted',
            'On the Way',
            'Reached'
        )
        """
    ).fetchone()[0]


    critical = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        WHERE severity = 'Critical'
        """
    ).fetchone()[0]


    resolved = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        WHERE status IN
        (
            'Completed',
            'Resolved'
        )
        """
    ).fetchone()[0]


    conn.close()


    return render_template(
        "admin.html",
        emergencies=emergencies,
        responders=responders,
        stations=stations,
        total=total,
        reported=reported,
        assigned=assigned,
        critical=critical,
        resolved=resolved
    )


# ============================================================
# CLEAR EMERGENCIES
# ============================================================

@app.route(
    "/admin/clear-emergencies",
    methods=["POST"],
    endpoint="clear_all_emergencies"
)
@app.route(
    "/admin/clear_emergencies",
    methods=["POST"],
    endpoint="clear_emergencies"
)
@admin_required
def clear_all_emergencies():

    conn = get_db()


    try:

        assigned_ids = conn.execute(
            """
            SELECT DISTINCT responder_id
            FROM emergency_responders
            """
        ).fetchall()


        legacy_ids = conn.execute(
            """
            SELECT DISTINCT responder_id
            FROM emergencies
            WHERE responder_id IS NOT NULL
            """
        ).fetchall()


        conn.execute(
            "DELETE FROM emergency_responders"
        )

        conn.execute(
            "DELETE FROM emergency_history"
        )

        conn.execute(
            "DELETE FROM emergencies"
        )


        all_ids = set()


        for row in assigned_ids:

            if row["responder_id"]:

                all_ids.add(
                    row["responder_id"]
                )


        for row in legacy_ids:

            if row["responder_id"]:

                all_ids.add(
                    row["responder_id"]
                )


        for responder_id in all_ids:

            conn.execute(
                """
                UPDATE responders
                SET status = 'Available'
                WHERE id = ?
                """,
                (
                    responder_id,
                )
            )


        conn.commit()


    except Exception:

        conn.rollback()

        conn.close()

        flash(
            "Could not clear emergency reports.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    conn.close()


    flash(
        "All emergency reports were cleared.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


# ============================================================
# STATIONS
# ============================================================

@app.route("/stations")
@admin_required
def stations():

    conn = get_db()


    station_list = conn.execute(
        """
        SELECT *
        FROM stations
        ORDER BY id DESC
        """
    ).fetchall()


    conn.close()


    return render_template(
        "stations.html",
        stations=station_list
    )


@app.route(
    "/stations/add",
    methods=["GET", "POST"]
)
@admin_required
def add_station():

    if request.method == "GET":

        return render_template(
            "add_station.html"
        )


    name = request.form.get(
        "name",
        ""
    ).strip()

    station_type = request.form.get(
        "type",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    address = request.form.get(
        "address",
        ""
    ).strip()

    latitude = request.form.get(
        "latitude"
    )

    longitude = request.form.get(
        "longitude"
    )

    status = request.form.get(
        "status",
        "Active"
    ).strip()


    if not name or not station_type:

        flash(
            "Station name and type are required.",
            "error"
        )

        return redirect(
            url_for("add_station")
        )


    conn = get_db()


    conn.execute(
        """
        INSERT INTO stations
        (
            name,
            type,
            phone,
            address,
            latitude,
            longitude,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            station_type,
            phone,
            address,
            latitude,
            longitude,
            status,
            now()
        )
    )


    conn.commit()

    conn.close()


    flash(
        "Station added successfully.",
        "success"
    )


    return redirect(
        url_for("stations")
    )


@app.route(
    "/stations/delete/<int:station_id>",
    methods=["POST", "GET"]
)
@admin_required
def delete_station(station_id):

    conn = get_db()


    conn.execute(
        """
        DELETE FROM stations
        WHERE id = ?
        """,
        (
            station_id,
        )
    )


    conn.commit()

    conn.close()


    return redirect(
        url_for("stations")
    )


# ============================================================
# RESPONDERS
# ============================================================

@app.route("/responders")
@admin_required
def responders():

    conn = get_db()


    responder_list = conn.execute(
        """
        SELECT *
        FROM responders
        ORDER BY id DESC
        """
    ).fetchall()


    conn.close()


    return render_template(
        "responders.html",
        responders=responder_list
    )


# ============================================================
# ADD RESPONDER
# ============================================================

@app.route(
    "/responders/add",
    methods=["GET", "POST"]
)
@admin_required
def add_responder():

    if request.method == "GET":

        return render_template(
            "add_responder.html"
        )


    responder_id = request.form.get(
        "responder_id",
        ""
    ).strip()


    if responder_id:

        try:

            return edit_responder(
                int(responder_id)
            )

        except ValueError:

            flash(
                "Invalid responder ID.",
                "error"
            )

            return redirect(
                url_for("responders")
            )


    name = request.form.get(
        "name",
        ""
    ).strip()

    department = request.form.get(
        "department",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    latitude = request.form.get(
        "latitude"
    )

    longitude = request.form.get(
        "longitude"
    )

    status = request.form.get(
        "status",
        "Available"
    ).strip()

    login_username = request.form.get(
        "login_username",
        ""
    ).strip()

    login_password = request.form.get(
        "login_password",
        ""
    ).strip()


    if (
        not name
        or not department
        or not phone
    ):

        flash(
            "Name, department and phone are required.",
            "error"
        )

        return redirect(
            url_for("add_responder")
        )


    if (
        not login_username
        or not login_password
    ):

        flash(
            "Responder username and password are required.",
            "error"
        )

        return redirect(
            url_for("add_responder")
        )


    conn = get_db()


    existing = conn.execute(
        """
        SELECT id
        FROM responders
        WHERE login_username = ?
        """,
        (
            login_username,
        )
    ).fetchone()


    if existing:

        conn.close()

        flash(
            "That responder username already exists.",
            "error"
        )

        return redirect(
            url_for("add_responder")
        )


    conn.execute(
        """
        INSERT INTO responders
        (
            name,
            department,
            phone,
            status,
            latitude,
            longitude,
            created_at,
            login_username,
            login_password
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            department,
            phone,
            status,
            latitude,
            longitude,
            now(),
            login_username,
            login_password
        )
    )


    conn.commit()

    conn.close()


    flash(
        "Responder created successfully.",
        "success"
    )


    return redirect(
        url_for("responders")
    )


# ============================================================
# EDIT RESPONDER
# ============================================================

@app.route(
    "/responders/edit/<int:responder_id>",
    methods=["GET", "POST"],
    endpoint="edit_responder"
)
@admin_required
def edit_responder(
    responder_id
):

    conn = get_db()


    responder = conn.execute(
        """
        SELECT *
        FROM responders
        WHERE id = ?
        """,
        (
            responder_id,
        )
    ).fetchone()


    if responder is None:

        conn.close()

        flash(
            "Responder not found.",
            "error"
        )

        return redirect(
            url_for("responders")
        )


    if request.method == "GET":

        conn.close()

        return render_template(
            "add_responder.html",
            responder=responder,
            edit_mode=True
        )


    name = request.form.get(
        "name",
        responder["name"] or ""
    ).strip()

    department = request.form.get(
        "department",
        responder["department"] or ""
    ).strip()

    phone = request.form.get(
        "phone",
        responder["phone"] or ""
    ).strip()

    status = request.form.get(
        "status",
        responder["status"] or "Available"
    ).strip()

    username = request.form.get(
        "login_username",
        responder["login_username"] or ""
    ).strip()

    password = request.form.get(
        "login_password",
        ""
    ).strip()


    latitude_raw = request.form.get(
        "latitude",
        ""
    ).strip()

    longitude_raw = request.form.get(
        "longitude",
        ""
    ).strip()


    try:

        latitude = (
            float(latitude_raw)
            if latitude_raw
            else responder["latitude"]
        )

    except (
        TypeError,
        ValueError
    ):

        latitude = responder["latitude"]


    try:

        longitude = (
            float(longitude_raw)
            if longitude_raw
            else responder["longitude"]
        )

    except (
        TypeError,
        ValueError
    ):

        longitude = responder["longitude"]


    if (
        not name
        or not department
        or not phone
    ):

        conn.close()

        flash(
            "Name, department and phone are required.",
            "error"
        )

        return redirect(
            url_for(
                "edit_responder",
                responder_id=responder_id
            )
        )


    if username:

        duplicate = conn.execute(
            """
            SELECT id
            FROM responders
            WHERE
                login_username = ?
                AND id != ?
            """,
            (
                username,
                responder_id
            )
        ).fetchone()


        if duplicate:

            conn.close()

            flash(
                "That responder username already exists.",
                "error"
            )

            return redirect(
                url_for(
                    "edit_responder",
                    responder_id=responder_id
                )
            )


    new_password = (
        password
        or responder["login_password"]
    )


    conn.execute(
        """
        UPDATE responders
        SET
            name = ?,
            department = ?,
            phone = ?,
            status = ?,
            latitude = ?,
            longitude = ?,
            login_username = ?,
            login_password = ?
        WHERE id = ?
        """,
        (
            name,
            department,
            phone,
            status or "Available",
            latitude,
            longitude,
            username or None,
            new_password,
            responder_id
        )
    )


    conn.commit()

    conn.close()


    flash(
        "Responder updated successfully.",
        "success"
    )


    return redirect(
        url_for("responders")
    )


# ============================================================
# DELETE RESPONDER
# ============================================================

@app.route(
    "/responders/delete/<int:responder_id>",
    methods=["POST", "GET"]
)
@admin_required
def delete_responder(
    responder_id
):

    conn = get_db()


    conn.execute(
        """
        DELETE FROM responders
        WHERE id = ?
        """,
        (
            responder_id,
        )
    )


    conn.commit()

    conn.close()


    return redirect(
        url_for("responders")
    )


# ============================================================
# RESPONDER DASHBOARD
# ============================================================

@app.route(
    "/responder/dashboard"
)
@responder_required
def responder_dashboard():

    responder_id = session.get(
        "responder_id"
    )


    conn = get_db()


    responder = conn.execute(
        """
        SELECT *
        FROM responders
        WHERE id = ?
        """,
        (
            responder_id,
        )
    ).fetchone()


    emergencies = conn.execute(
        """
        SELECT DISTINCT e.*
        FROM emergencies e
        LEFT JOIN emergency_responders er
            ON er.emergency_id = e.id
        WHERE
            e.responder_id = ?
            OR er.responder_id = ?
        ORDER BY e.id DESC
        """,
        (
            responder_id,
            responder_id
        )
    ).fetchall()


    conn.close()


    return render_template(
        "responder_dashboard.html",
        responder=responder,
        emergencies=emergencies
    )


# ============================================================
# RESPONDER STATUS
# ============================================================

@app.route(
    "/responder/emergency/<int:emergency_id>/status",
    methods=["POST"]
)
@responder_required
def responder_status(
    emergency_id
):

    responder_id = session.get(
        "responder_id"
    )


    new_status = request.form.get(
        "status",
        ""
    ).strip()

    note = request.form.get(
        "note",
        ""
    ).strip()


    allowed = [

        "Accepted",

        "On the Way",

        "Reached",

        "Completed"
    ]


    if new_status not in allowed:

        flash(
            "Invalid status.",
            "error"
        )

        return redirect(
            url_for(
                "responder_dashboard"
            )
        )


    conn = get_db()


    # --------------------------------------------------------
    # FIRST CHECK MULTI-RESPONDER ASSIGNMENT
    # --------------------------------------------------------

    multi = conn.execute(
        """
        SELECT *
        FROM emergency_responders
        WHERE
            emergency_id = ?
            AND responder_id = ?
        """,
        (
            emergency_id,
            responder_id
        )
    ).fetchone()


    if multi:

        old_status = multi["status"]


        completed_at = (
            now()
            if new_status == "Completed"
            else None
        )


        conn.execute(
            """
            UPDATE emergency_responders
            SET
                status = ?,
                accepted_at =
                    CASE
                        WHEN ?
                        = 'Accepted'
                        AND accepted_at IS NULL
                        THEN ?
                        ELSE accepted_at
                    END,
                completed_at = ?
            WHERE
                emergency_id = ?
                AND responder_id = ?
            """,
            (
                new_status,
                new_status,
                now(),
                completed_at,
                emergency_id,
                responder_id
            )
        )


        if new_status == "Completed":

            conn.execute(
                """
                UPDATE responders
                SET status = 'Available'
                WHERE id = ?
                """,
                (
                    responder_id,
                )
            )

        else:

            conn.execute(
                """
                UPDATE responders
                SET status = 'Busy'
                WHERE id = ?
                """,
                (
                    responder_id,
                )
            )


        remaining = conn.execute(
            """
            SELECT COUNT(*)
            FROM emergency_responders
            WHERE
                emergency_id = ?
                AND status NOT IN
                (
                    'Completed',
                    'Declined'
                )
            """,
            (
                emergency_id,
            )
        ).fetchone()[0]


        if remaining == 0:

            conn.execute(
                """
                UPDATE emergencies
                SET
                    status = 'Completed',
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    now(),
                    emergency_id
                )
            )


        conn.commit()

        conn.close()


        add_history(
            emergency_id,
            old_status,
            new_status,
            note
            or "Updated by responder"
        )


        flash(
            "Emergency status updated.",
            "success"
        )


        return redirect(
            url_for(
                "responder_dashboard"
            )
        )


    # --------------------------------------------------------
    # LEGACY PRIMARY RESPONDER ASSIGNMENT
    # --------------------------------------------------------

    emergency = conn.execute(
        """
        SELECT *
        FROM emergencies
        WHERE
            id = ?
            AND responder_id = ?
        """,
        (
            emergency_id,
            responder_id
        )
    ).fetchone()


    if emergency is None:

        conn.close()

        flash(
            "This emergency is not assigned to you.",
            "error"
        )

        return redirect(
            url_for(
                "responder_dashboard"
            )
        )


    old_status = emergency["status"]


    completed_at = emergency["completed_at"]


    if new_status == "Completed":

        completed_at = now()


    conn.execute(
        """
        UPDATE emergencies
        SET
            status = ?,
            resolution_notes = ?,
            completed_at = ?
        WHERE
            id = ?
            AND responder_id = ?
        """,
        (
            new_status,
            note,
            completed_at,
            emergency_id,
            responder_id
        )
    )


    if new_status == "Completed":

        conn.execute(
            """
            UPDATE responders
            SET status = 'Available'
            WHERE id = ?
            """,
            (
                responder_id,
            )
        )

    else:

        conn.execute(
            """
            UPDATE responders
            SET status = 'Busy'
            WHERE id = ?
            """,
            (
                responder_id,
            )
        )


    conn.commit()

    conn.close()


    add_history(
        emergency_id,
        old_status,
        new_status,
        note
        or "Updated by responder"
    )


    flash(
        "Emergency status updated.",
        "success"
    )


    return redirect(
        url_for(
            "responder_dashboard"
        )
    )


# ============================================================
# EMERGENCY DETAILS
# ============================================================

@app.route(
    "/emergency/<int:emergency_id>"
)
def emergency_details(
    emergency_id
):

    conn = get_db()


    emergency = conn.execute(
        """
        SELECT
            e.*,
            r.name AS responder_name,
            r.phone AS responder_phone,
            r.department AS responder_department
        FROM emergencies e
        LEFT JOIN responders r
            ON e.responder_id = r.id
        WHERE e.id = ?
        """,
        (
            emergency_id,
        )
    ).fetchone()


    history = conn.execute(
        """
        SELECT *
        FROM emergency_history
        WHERE emergency_id = ?
        ORDER BY id DESC
        """,
        (
            emergency_id,
        )
    ).fetchall()


    assigned_responders = conn.execute(
        """
        SELECT
            er.*,
            r.name,
            r.phone,
            r.department,
            r.status AS responder_current_status
        FROM emergency_responders er
        JOIN responders r
            ON r.id = er.responder_id
        WHERE er.emergency_id = ?
        ORDER BY er.id
        """,
        (
            emergency_id,
        )
    ).fetchall()


    conn.close()


    if emergency is None:

        return render_template(
            "error.html",
            message="Emergency not found."
        ), 404


    return render_template(
        "emergency_details.html",
        emergency=emergency,
        history=history,
        assigned_responders=assigned_responders
    )


# ============================================================
# MULTI RESPONDER API
# ============================================================

@app.route(
    "/api/emergency/<int:emergency_id>/responders"
)
def api_emergency_responders(
    emergency_id
):

    conn = get_db()


    rows = conn.execute(
        """
        SELECT
            er.*,
            r.name,
            r.phone,
            r.department,
            r.status AS responder_current_status
        FROM emergency_responders er
        JOIN responders r
            ON r.id = er.responder_id
        WHERE er.emergency_id = ?
        ORDER BY er.id
        """,
        (
            emergency_id,
        )
    ).fetchall()


    conn.close()


    return jsonify(
        [
            dict(row)
            for row in rows
        ]
    )


# ============================================================
# ACCEPT MULTI RESPONDER
# ============================================================

@app.route(
    "/api/responder/emergency/<int:emergency_id>/accept",
    methods=["POST"]
)
@responder_required
def accept_multi_responder(
    emergency_id
):

    responder_id = session.get(
        "responder_id"
    )


    conn = get_db()


    row = conn.execute(
        """
        SELECT *
        FROM emergency_responders
        WHERE
            emergency_id = ?
            AND responder_id = ?
        """,
        (
            emergency_id,
            responder_id
        )
    ).fetchone()


    if row is None:

        conn.close()

        return jsonify(
            {
                "success": False,
                "error":
                    "You are not dispatched "
                    "to this emergency."
            }
        ), 403


    conn.execute(
        """
        UPDATE emergency_responders
        SET
            status = 'Accepted',
            accepted_at = ?
        WHERE
            emergency_id = ?
            AND responder_id = ?
        """,
        (
            now(),
            emergency_id,
            responder_id
        )
    )


    conn.execute(
        """
        UPDATE responders
        SET status = 'Busy'
        WHERE id = ?
        """,
        (
            responder_id,
        )
    )


    conn.commit()

    conn.close()


    return jsonify(
        {
            "success": True,
            "status": "Accepted"
        }
    )


# ============================================================
# MULTI RESPONDER STATUS
# ============================================================

@app.route(
    "/api/responder/emergency/<int:emergency_id>/multi-status",
    methods=["POST"]
)
@responder_required
def multi_responder_status(
    emergency_id
):

    responder_id = session.get(
        "responder_id"
    )


    data = request.get_json(
        silent=True
    ) or request.form


    status = (
        data.get("status")
        or ""
    ).strip()


    allowed = [

        "Dispatched",

        "Accepted",

        "On the Way",

        "Reached",

        "Completed",

        "Declined"
    ]


    if status not in allowed:

        return jsonify(
            {
                "success": False,
                "error":
                    "Invalid status."
            }
        ), 400


    conn = get_db()


    row = conn.execute(
        """
        SELECT *
        FROM emergency_responders
        WHERE
            emergency_id = ?
            AND responder_id = ?
        """,
        (
            emergency_id,
            responder_id
        )
    ).fetchone()


    if row is None:

        conn.close()

        return jsonify(
            {
                "success": False,
                "error":
                    "You are not dispatched "
                    "to this emergency."
            }
        ), 403


    completed_at = (
        now()
        if status == "Completed"
        else None
    )


    conn.execute(
        """
        UPDATE emergency_responders
        SET
            status = ?,
            accepted_at =
                CASE
                    WHEN ?
                    = 'Accepted'
                    AND accepted_at IS NULL
                    THEN ?
                    ELSE accepted_at
                END,
            completed_at = ?
        WHERE
            emergency_id = ?
            AND responder_id = ?
        """,
        (
            status,
            status,
            now(),
            completed_at,
            emergency_id,
            responder_id
        )
    )


    if status in (
        "Completed",
        "Declined"
    ):

        conn.execute(
            """
            UPDATE responders
            SET status = 'Available'
            WHERE id = ?
            """,
            (
                responder_id,
            )
        )

    else:

        conn.execute(
            """
            UPDATE responders
            SET status = 'Busy'
            WHERE id = ?
            """,
            (
                responder_id,
            )
        )


    remaining = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergency_responders
        WHERE
            emergency_id = ?
            AND status NOT IN
            (
                'Completed',
                'Declined'
            )
        """,
        (
            emergency_id,
        )
    ).fetchone()[0]


    if remaining == 0:

        conn.execute(
            """
            UPDATE emergencies
            SET
                status = 'Completed',
                completed_at = ?
            WHERE id = ?
            """,
            (
                now(),
                emergency_id
            )
        )


    conn.commit()

    conn.close()


    return jsonify(
        {
            "success": True,
            "status": status
        }
    )


# ============================================================
# EMERGENCY PHOTO
# ============================================================

@app.route(
    "/emergency/photo/<path:filename>",
    endpoint="emergency_photo"
)
def emergency_photo(
    filename
):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# ============================================================
# ADMIN STATUS UPDATE
# ============================================================

@app.route(
    "/status/<int:emergency_id>",
    methods=["POST"],
    endpoint="status"
)
@app.route(
    "/status/<int:emergency_id>",
    methods=["POST"],
    endpoint="update_status"
)
@admin_required
def status_update(
    emergency_id
):

    new_status = request.form.get(
        "status",
        ""
    ).strip()

    note = request.form.get(
        "note",
        ""
    ).strip()


    allowed = [

        "Reported",

        "Assigned",

        "Accepted",

        "On the Way",

        "Reached",

        "Completed",

        "Resolved",

        "Cancelled"
    ]


    if new_status not in allowed:

        return redirect(
            url_for(
                "emergency_details",
                emergency_id=emergency_id
            )
        )


    conn = get_db()


    emergency = conn.execute(
        """
        SELECT *
        FROM emergencies
        WHERE id = ?
        """,
        (
            emergency_id,
        )
    ).fetchone()


    if emergency is None:

        conn.close()

        return "Emergency not found", 404


    old_status = emergency["status"]


    completed_at = (
        emergency["completed_at"]
    )


    if new_status in (
        "Completed",
        "Resolved"
    ):

        completed_at = now()


    conn.execute(
        """
        UPDATE emergencies
        SET
            status = ?,
            resolution_notes = ?,
            completed_at = ?
        WHERE id = ?
        """,
        (
            new_status,
            note,
            completed_at,
            emergency_id
        )
    )


    if new_status in (
        "Completed",
        "Resolved",
        "Cancelled"
    ):

        conn.execute(
            """
            UPDATE responders
            SET status = 'Available'
            WHERE id IN
            (
                SELECT responder_id
                FROM emergency_responders
                WHERE emergency_id = ?
            )
            """,
            (
                emergency_id,
            )
        )


        if emergency["responder_id"]:

            conn.execute(
                """
                UPDATE responders
                SET status = 'Available'
                WHERE id = ?
                """,
                (
                    emergency["responder_id"],
                )
            )


        conn.execute(
            """
            UPDATE emergency_responders
            SET status = ?
            WHERE emergency_id = ?
            """,
            (
                (
                    "Completed"
                    if new_status
                    in (
                        "Completed",
                        "Resolved"
                    )
                    else "Declined"
                ),
                emergency_id
            )
        )


    conn.commit()

    conn.close()


    add_history(
        emergency_id,
        old_status,
        new_status,
        note
    )


    return redirect(
        url_for(
            "emergency_details",
            emergency_id=emergency_id
        )
    )


# ============================================================
# COMPATIBILITY STATUS ROUTE
# ============================================================

@app.route(
    "/status-update/<int:emergency_id>",
    methods=["POST"],
    endpoint="status_update_alias"
)
@admin_required
def update_status_alias(
    emergency_id
):

    return status_update(
        emergency_id
    )


# ============================================================
# SAVE RESOLUTION
# ============================================================

@app.route(
    "/emergency/<int:emergency_id>/resolution",
    methods=["POST"],
    endpoint="save_resolution"
)
@admin_required
def save_resolution(
    emergency_id
):

    resolution_notes = request.form.get(
        "resolution_notes",
        request.form.get(
            "note",
            ""
        )
    ).strip()


    conn = get_db()


    emergency = conn.execute(
        """
        SELECT *
        FROM emergencies
        WHERE id = ?
        """,
        (
            emergency_id,
        )
    ).fetchone()


    if emergency is None:

        conn.close()

        return "Emergency not found", 404


    conn.execute(
        """
        UPDATE emergencies
        SET resolution_notes = ?
        WHERE id = ?
        """,
        (
            resolution_notes,
            emergency_id
        )
    )


    conn.commit()

    conn.close()


    flash(
        "Resolution details saved successfully.",
        "success"
    )


    return redirect(
        url_for(
            "emergency_details",
            emergency_id=emergency_id
        )
    )


# ============================================================
# ADMIN MANUAL ASSIGNMENT
# ============================================================

@app.route(
    "/assign/<int:emergency_id>",
    methods=["POST"],
    endpoint="assign"
)
@app.route(
    "/emergency/<int:emergency_id>/assign",
    methods=["POST"],
    endpoint="assign_responder"
)
@admin_required
def assign(
    emergency_id
):

    responder_id = request.form.get(
        "responder_id"
    )


    conn = get_db()


    responder = conn.execute(
        """
        SELECT *
        FROM responders
        WHERE id = ?
        """,
        (
            responder_id,
        )
    ).fetchone()


    emergency = conn.execute(
        """
        SELECT *
        FROM emergencies
        WHERE id = ?
        """,
        (
            emergency_id,
        )
    ).fetchone()


    if (
        responder is None
        or emergency is None
    ):

        conn.close()

        return redirect(
            url_for("admin")
        )


    # ========================================================
    # WOMEN SAFETY = POLICE ONLY
    # ========================================================

    if (
        emergency["emergency_type"]
        or ""
    ).strip().lower() == "women safety":

        department = (
            responder["department"]
            or ""
        ).lower()


        if "police" not in department:

            conn.close()

            flash(
                "Women Safety emergencies can only be assigned to Police responders.",
                "error"
            )

            return redirect(
                url_for(
                    "emergency_details",
                    emergency_id=emergency_id
                )
            )


    # --------------------------------------------------------
    # Release old primary responder if different
    # --------------------------------------------------------

    old_responder_id = (
        emergency["responder_id"]
    )


    if (
        old_responder_id
        and old_responder_id
        != responder["id"]
    ):

        conn.execute(
            """
            UPDATE responders
            SET status = 'Available'
            WHERE id = ?
            """,
            (
                old_responder_id,
            )
        )


    # --------------------------------------------------------
    # Primary assignment
    # --------------------------------------------------------

    conn.execute(
        """
        UPDATE emergencies
        SET
            responder = ?,
            responder_id = ?,
            status = 'Assigned'
        WHERE id = ?
        """,
        (
            responder["name"],
            responder["id"],
            emergency_id
        )
    )


    conn.execute(
        """
        UPDATE responders
        SET status = 'Busy'
        WHERE id = ?
        """,
        (
            responder["id"],
        )
    )


    # --------------------------------------------------------
    # Add to multiple responder table
    # --------------------------------------------------------

    conn.execute(
        """
        INSERT OR IGNORE INTO emergency_responders
        (
            emergency_id,
            responder_id,
            department,
            status,
            assigned_at,
            distance_km
        )
        VALUES
        (
            ?,
            ?,
            ?,
            'Dispatched',
            ?,
            NULL
        )
        """,
        (
            emergency_id,
            responder["id"],
            responder["department"],
            now()
        )
    )


    conn.commit()

    conn.close()


    add_history(
        emergency_id,
        emergency["status"],
        "Assigned",
        "Assigned by admin to "
        + responder["name"]
    )


    return redirect(
        url_for(
            "emergency_details",
            emergency_id=emergency_id
        )
    )


# ============================================================
# DELETE EMERGENCY
# ============================================================

@app.route(
    "/delete/<int:emergency_id>",
    methods=["POST"],
    endpoint="delete"
)
@admin_required
def delete(
    emergency_id
):

    conn = get_db()


    responder_rows = conn.execute(
        """
        SELECT responder_id
        FROM emergency_responders
        WHERE emergency_id = ?
        """,
        (
            emergency_id,
        )
    ).fetchall()


    for row in responder_rows:

        if row["responder_id"]:

            conn.execute(
                """
                UPDATE responders
                SET status = 'Available'
                WHERE id = ?
                """,
                (
                    row["responder_id"],
                )
            )


    conn.execute(
        """
        DELETE FROM emergency_responders
        WHERE emergency_id = ?
        """,
        (
            emergency_id,
        )
    )


    conn.execute(
        """
        DELETE FROM emergency_history
        WHERE emergency_id = ?
        """,
        (
            emergency_id,
        )
    )


    conn.execute(
        """
        DELETE FROM emergencies
        WHERE id = ?
        """,
        (
            emergency_id,
        )
    )


    conn.commit()

    conn.close()


    return redirect(
        url_for("admin")
    )


# ============================================================
# USER DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    return user_dashboard()


@app.route("/user-dashboard")
def user_dashboard():

    conn = get_db()


    if session.get("role") == "user":

        user_id = session.get(
            "user_id"
        )


        emergencies = conn.execute(
            """
            SELECT *
            FROM emergencies
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (
                user_id,
            )
        ).fetchall()

    else:

        emergencies = conn.execute(
            """
            SELECT *
            FROM emergencies
            ORDER BY id DESC
            """
        ).fetchall()


    conn.close()


    return render_template(
        "user_dashboard.html",
        emergencies=emergencies
    )


# ============================================================
# ANALYTICS
# ============================================================

@app.route("/analytics")
@admin_required
def analytics():

    conn = get_db()


    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        """
    ).fetchone()[0]


    completed = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        WHERE status IN
        (
            'Completed',
            'Resolved'
        )
        """
    ).fetchone()[0]


    pending = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        WHERE status NOT IN
        (
            'Completed',
            'Resolved',
            'Cancelled'
        )
        """
    ).fetchone()[0]


    critical = conn.execute(
        """
        SELECT COUNT(*)
        FROM emergencies
        WHERE severity = 'Critical'
        """
    ).fetchone()[0]


    type_rows = conn.execute(
        """
        SELECT
            emergency_type,
            COUNT(*) AS count
        FROM emergencies
        GROUP BY emergency_type
        ORDER BY count DESC
        """
    ).fetchall()


    status_rows = conn.execute(
        """
        SELECT
            status,
            COUNT(*) AS count
        FROM emergencies
        GROUP BY status
        ORDER BY count DESC
        """
    ).fetchall()


    conn.close()


    return render_template(
        "analytics.html",
        total=total,
        completed=completed,
        pending=pending,
        critical=critical,
        type_rows=type_rows,
        status_rows=status_rows
    )


# ============================================================
# FIND NEAREST RESPONDER
# ============================================================

def find_nearest_responder(
    emergency_type,
    latitude,
    longitude
):

    conn = get_db()


    responders = conn.execute(
        """
        SELECT *
        FROM responders
        WHERE LOWER(
            COALESCE(status, 'Available')
        ) = 'available'
        """
    ).fetchall()


    conn.close()


    if not responders:

        return None


    emergency_type = (
        emergency_type or ""
    ).strip().lower()


    if emergency_type == "women safety":

        required = [
            "police"
        ]

    elif emergency_type == "accident":

        required = [
            "police",
            "ambulance"
        ]

    elif emergency_type == "fire":

        required = [
            "fire"
        ]

    elif emergency_type == "medical":

        required = [
            "ambulance",
            "medical"
        ]

    elif emergency_type == "police":

        required = [
            "police"
        ]

    else:

        required = []


    candidates = []


    for responder in responders:

        department = (
            responder["department"]
            or ""
        ).lower()


        if required:

            if not any(
                word in department
                for word in required
            ):

                continue


        distance = distance_km(
            latitude,
            longitude,
            responder["latitude"],
            responder["longitude"]
        )


        if distance is not None:

            candidates.append(
                (
                    distance,
                    responder
                )
            )


    if candidates:

        candidates.sort(
            key=lambda item: item[0]
        )

        return candidates[0][1]


    # GPS unavailable:
    # choose any correct department.

    for responder in responders:

        department = (
            responder["department"]
            or ""
        ).lower()


        if required:

            if not any(
                word in department
                for word in required
            ):

                continue


        return responder


    return None


# ============================================================
# API - ALL EMERGENCIES
# ============================================================

@app.route(
    "/api/emergencies"
)
def api_emergencies():

    conn = get_db()


    rows = conn.execute(
        """
        SELECT *
        FROM emergencies
        ORDER BY id DESC
        """
    ).fetchall()


    conn.close()


    return jsonify(
        [
            dict(row)
            for row in rows
        ]
    )


# ============================================================
# API - SINGLE EMERGENCY
# ============================================================

@app.route(
    "/api/emergency/<int:emergency_id>"
)
def api_emergency(
    emergency_id
):

    conn = get_db()


    row = conn.execute(
        """
        SELECT *
        FROM emergencies
        WHERE id = ?
        """,
        (
            emergency_id,
        )
    ).fetchone()


    conn.close()


    if row is None:

        return jsonify(
            {
                "error":
                    "Emergency not found"
            }
        ), 404


    return jsonify(
        dict(row)
    )


# ============================================================
# RESPONDER LOCATION
# ============================================================

@app.route(
    "/api/responder/location",
    methods=["POST"]
)
def responder_location():

    data = request.get_json(
        silent=True
    ) or {}


    responder_id = (
        session.get("responder_id")
        or data.get("responder_id")
        or request.form.get(
            "responder_id"
        )
    )


    latitude = data.get(
        "latitude"
    )

    longitude = data.get(
        "longitude"
    )

    status = (
        data.get("status")
        or request.form.get(
            "status"
        )
    )


    if latitude is None:

        latitude = request.form.get(
            "latitude"
        )


    if longitude is None:

        longitude = request.form.get(
            "longitude"
        )


    if (
        not responder_id
        or latitude is None
        or longitude is None
    ):

        return jsonify(
            {
                "success": False,
                "error":
                    "responder_id, latitude and longitude are required"
            }
        ), 400


    try:

        responder_id = int(
            responder_id
        )

        latitude = float(
            latitude
        )

        longitude = float(
            longitude
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify(
            {
                "success": False,
                "error":
                    "Invalid responder ID or location"
            }
        ), 400


    if not (
        -90 <= latitude <= 90
        and
        -180 <= longitude <= 180
    ):

        return jsonify(
            {
                "success": False,
                "error":
                    "Invalid latitude or longitude"
            }
        ), 400


    conn = get_db()


    responder = conn.execute(
        """
        SELECT
            id,
            name,
            department,
            status
        FROM responders
        WHERE id = ?
        """,
        (
            responder_id,
        )
    ).fetchone()


    if responder is None:

        conn.close()

        return jsonify(
            {
                "success": False,
                "error":
                    "Responder not found"
            }
        ), 404


    if status:

        conn.execute(
            """
            UPDATE responders
            SET
                latitude = ?,
                longitude = ?,
                status = ?
            WHERE id = ?
            """,
            (
                latitude,
                longitude,
                status,
                responder_id
            )
        )

    else:

        conn.execute(
            """
            UPDATE responders
            SET
                latitude = ?,
                longitude = ?
            WHERE id = ?
            """,
            (
                latitude,
                longitude,
                responder_id
            )
        )


    conn.commit()

    conn.close()


    return jsonify(
        {
            "success": True,

            "responder_id":
                responder_id,

            "latitude":
                latitude,

            "longitude":
                longitude,

            "status":
                status
                or responder["status"]
        }
    )


# ============================================================
# API - RESPONDERS
# ============================================================

@app.route(
    "/api/responders"
)
def api_responders():

    conn = get_db()


    rows = conn.execute(
        """
        SELECT *
        FROM responders
        ORDER BY name
        """
    ).fetchall()


    conn.close()


    return jsonify(
        [
            dict(row)
            for row in rows
        ]
    )


# ============================================================
# PDF REPORT
# ============================================================

@app.route(
    "/emergency/<int:emergency_id>/pdf",
    endpoint="final_report"
)
@admin_required
def final_report(
    emergency_id
):

    try:

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm

    except ImportError:

        return (
            "ReportLab is not installed. "
            "Run: pip install reportlab"
        ), 500


    conn = get_db()


    emergency = conn.execute(
        """
        SELECT
            e.*,
            r.name AS responder_name,
            r.phone AS responder_phone,
            r.department AS responder_department
        FROM emergencies e
        LEFT JOIN responders r
            ON e.responder_id = r.id
        WHERE e.id = ?
        """,
        (
            emergency_id,
        )
    ).fetchone()


    assigned_responders = conn.execute(
        """
        SELECT
            er.*,
            r.name,
            r.phone,
            r.department
        FROM emergency_responders er
        JOIN responders r
            ON r.id = er.responder_id
        WHERE er.emergency_id = ?
        ORDER BY er.id
        """,
        (
            emergency_id,
        )
    ).fetchall()


    conn.close()


    if emergency is None:

        return (
            "Emergency not found",
            404
        )


    pdf_path = os.path.join(
        REPORT_FOLDER,
        f"emergency_{emergency_id}.pdf"
    )


    pdf = canvas.Canvas(
        pdf_path,
        pagesize=A4
    )


    width, height = A4


    y = height - 25 * mm


    pdf.setFont(
        "Helvetica-Bold",
        18
    )


    pdf.drawString(
        20 * mm,
        y,
        "Emergency Assistance Report"
    )


    y -= 15 * mm


    fields = [

        (
            "Emergency ID",
            emergency["id"]
        ),

        (
            "Reporter",
            emergency["name"]
        ),

        (
            "Phone",
            emergency["phone"]
        ),

        (
            "Emergency Type",
            emergency["emergency_type"]
        ),

        (
            "Severity",
            emergency["severity"]
        ),

        (
            "Location",
            emergency["location"]
        ),

        (
            "Address",
            emergency["address"]
        ),

        (
            "Latitude",
            emergency["latitude"]
        ),

        (
            "Longitude",
            emergency["longitude"]
        ),

        (
            "Status",
            emergency["status"]
        ),

        (
            "Primary Responder",
            emergency["responder_name"]
        ),

        (
            "Responder Phone",
            emergency["responder_phone"]
        ),

        (
            "Department",
            emergency["responder_department"]
        ),

        (
            "Created At",
            emergency["created_at"]
        ),

        (
            "Completed At",
            emergency["completed_at"]
        )
    ]


    for label, value in fields:

        value = (
            ""
            if value is None
            else str(value)
        )


        pdf.setFont(
            "Helvetica-Bold",
            10
        )


        pdf.drawString(
            20 * mm,
            y,
            str(label) + ":"
        )


        pdf.setFont(
            "Helvetica",
            10
        )


        pdf.drawString(
            65 * mm,
            y,
            value[:100]
        )


        y -= 7 * mm


    # --------------------------------------------------------
    # MULTIPLE RESPONDERS
    # --------------------------------------------------------

    if assigned_responders:

        pdf.setFont(
            "Helvetica-Bold",
            11
        )

        pdf.drawString(
            20 * mm,
            y,
            "Assigned Responders:"
        )

        y -= 7 * mm


        pdf.setFont(
            "Helvetica",
            10
        )


        for responder in assigned_responders:

            text = (
                f'{responder["name"]} - '
                f'{responder["department"]} - '
                f'{responder["status"]}'
            )


            pdf.drawString(
                25 * mm,
                y,
                text[:100]
            )


            y -= 6 * mm


    y -= 5 * mm


    pdf.setFont(
        "Helvetica-Bold",
        11
    )


    pdf.drawString(
        20 * mm,
        y,
        "Description:"
    )


    y -= 7 * mm


    pdf.setFont(
        "Helvetica",
        10
    )


    pdf.drawString(
        20 * mm,
        y,
        (
            emergency["description"]
            or "No description."
        )[:120]
    )


    y -= 12 * mm


    pdf.setFont(
        "Helvetica-Bold",
        11
    )


    pdf.drawString(
        20 * mm,
        y,
        "Resolution Notes:"
    )


    y -= 7 * mm


    pdf.setFont(
        "Helvetica",
        10
    )


    pdf.drawString(
        20 * mm,
        y,
        (
            emergency["resolution_notes"]
            or "No resolution notes."
        )[:120]
    )


    pdf.save()


    return send_file(
        pdf_path,
        as_attachment=True
    )


# ============================================================
# COMPATIBILITY ROUTES
# ============================================================

app.add_url_rule(
    "/admin/dashboard",
    endpoint="admin_dashboard",
    view_func=admin
)

app.add_url_rule(
    "/admin/home",
    endpoint="admin_home",
    view_func=admin
)


app.add_url_rule(
    "/admin/stations",
    endpoint="station_management",
    view_func=stations
)

app.add_url_rule(
    "/admin/stations/list",
    endpoint="station_list",
    view_func=stations
)

app.add_url_rule(
    "/manage-stations",
    endpoint="manage_stations",
    view_func=stations
)


app.add_url_rule(
    "/admin/stations/add",
    endpoint="station_add",
    view_func=add_station,
    methods=["GET", "POST"]
)

app.add_url_rule(
    "/admin/stations/create",
    endpoint="create_station",
    view_func=add_station,
    methods=["GET", "POST"]
)


app.add_url_rule(
    "/admin/stations/delete/<int:station_id>",
    endpoint="station_delete",
    view_func=delete_station,
    methods=["POST", "GET"]
)


app.add_url_rule(
    "/admin/responders",
    endpoint="responder_management",
    view_func=responders
)

app.add_url_rule(
    "/admin/responders/list",
    endpoint="responder_list",
    view_func=responders
)

app.add_url_rule(
    "/manage-responders",
    endpoint="manage_responders",
    view_func=responders
)


app.add_url_rule(
    "/admin/responders/add",
    endpoint="responder_add",
    view_func=add_responder,
    methods=["GET", "POST"]
)

app.add_url_rule(
    "/admin/responders/create",
    endpoint="create_responder",
    view_func=add_responder,
    methods=["GET", "POST"]
)


app.add_url_rule(
    "/admin/responders/edit/<int:responder_id>",
    endpoint="responder_edit",
    view_func=edit_responder,
    methods=["GET", "POST"]
)

app.add_url_rule(
    "/manage-responders/edit/<int:responder_id>",
    endpoint="manage_responder_edit",
    view_func=edit_responder,
    methods=["GET", "POST"]
)


app.add_url_rule(
    "/admin/responders/delete/<int:responder_id>",
    endpoint="responder_delete",
    view_func=delete_responder,
    methods=["POST", "GET"]
)


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return render_template(
        "error.html",
        message="Page not found."
    ), 404


@app.errorhandler(500)
def server_error(error):

    return render_template(
        "error.html",
        message="Internal server error."
    ), 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    # IMPORTANT:
    # Database initialization happens only when the application
    # starts, NOT while importing the Flask application.
    # This prevents the old "Working outside of request context"
    # problem.

    init_database()


    print("")
    print("=" * 60)
    print(
        " EMERGENCY ASSISTANCE MANAGEMENT SYSTEM"
    )
    print(
        f" Database: {DATABASE}"
    )
    print("=" * 60)
    print("")

    print("ADMIN LOGIN")
    print(
        "Username : Nikky"
    )
    print(
        "Password : Kaila2808"
    )

    print("")

    print(
        "Responder login is created from "
        "Admin > Responders"
    )

    print("")

    print(
        "Local URL:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print("")

    print("=" * 60)


    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )