import sqlite3
import os

DATABASE = "emergency.db"


print("=" * 60)
print("EMERGENCY DATABASE FIX")
print("=" * 60)


if not os.path.exists(DATABASE):
    print("ERROR: emergency.db was not found.")
    print("Make sure this file is inside your emergency_system folder.")
    input("\nPress Enter to exit...")
    raise SystemExit


conn = sqlite3.connect(DATABASE)

conn.row_factory = sqlite3.Row


# ============================================================
# CHECK CURRENT TABLE
# ============================================================

print("\nChecking emergencies table...")

columns = conn.execute(
    "PRAGMA table_info(emergencies)"
).fetchall()


if not columns:
    print("ERROR: emergencies table was not found.")
    conn.close()
    input("\nPress Enter to exit...")
    raise SystemExit


print("\nCurrent columns:")

for column in columns:
    print(
        f"  {column['name']} | "
        f"type={column['type']} | "
        f"NOT NULL={column['notnull']}"
    )


# ============================================================
# BACKUP EXISTING EMERGENCIES
# ============================================================

print("\nCreating backup table...")

conn.execute("""
    DROP TABLE IF EXISTS emergencies_backup
""")


conn.execute("""
    CREATE TABLE emergencies_backup AS
    SELECT *
    FROM emergencies
""")


# ============================================================
# RENAME OLD TABLE
# ============================================================

print("Preparing new emergencies table...")

conn.execute("""
    ALTER TABLE emergencies
    RENAME TO emergencies_old
""")


# ============================================================
# CREATE NEW TABLE
#
# IMPORTANT:
# responder is now allowed to be NULL.
# ============================================================

conn.execute("""
    CREATE TABLE emergencies (
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

        rating INTEGER
    )
""")


# ============================================================
# COPY OLD DATA
# ============================================================

old_columns = [
    column["name"]
    for column in columns
]


new_columns = [
    "id",
    "name",
    "phone",
    "emergency_type",
    "location",
    "severity",
    "description",
    "status",
    "responder",
    "responder_id",
    "created_at",
    "user_id",
    "rating"
]


# Only copy columns that actually existed
available_columns = [
    column
    for column in new_columns
    if column in old_columns
]


print("\nCopying existing emergency records...")


if available_columns:

    column_list = ", ".join(
        available_columns
    )

    conn.execute(
        f"""
        INSERT INTO emergencies
        ({column_list})
        SELECT
            {column_list}
        FROM emergencies_old
        """
    )


# ============================================================
# REMOVE OLD TABLE
# ============================================================

conn.execute("""
    DROP TABLE emergencies_old
""")


# ============================================================
# COMMIT
# ============================================================

conn.commit()


# ============================================================
# VERIFY NEW STRUCTURE
# ============================================================

print("\nNew emergencies table:")

new_info = conn.execute(
    "PRAGMA table_info(emergencies)"
).fetchall()


for column in new_info:

    if column["name"] == "responder":

        print(
            f"  responder | "
            f"type={column['type']} | "
            f"NOT NULL={column['notnull']}"
        )


# ============================================================
# COUNT RECORDS
# ============================================================

count = conn.execute("""
    SELECT COUNT(*)
    FROM emergencies
""").fetchone()[0]


print("\nEmergency records preserved:", count)


# ============================================================
# TEST NULL RESPONDER
# ============================================================

print("\nTesting responder field...")

try:

    cursor = conn.execute("""
        INSERT INTO emergencies
        (
            name,
            phone,
            emergency_type,
            location,
            severity,
            description,
            status,
            responder,
            responder_id,
            created_at,
            user_id,
            rating
        )
        VALUES
        (
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
    """, (
        "DATABASE TEST",
        "0000000000",
        "Other",
        "Database Test",
        "Low",
        "",
        "Reported",
        None,
        None,
        "DATABASE TEST",
        None,
        None
    ))

    test_id = cursor.lastrowid

    conn.execute("""
        DELETE FROM emergencies
        WHERE id = ?
    """, (
        test_id,
    ))

    conn.commit()

    print("SUCCESS: responder can now be NULL.")


except Exception as error:

    conn.rollback()

    print("ERROR:", error)

    conn.close()

    input("\nPress Enter to exit...")
    raise SystemExit


# ============================================================
# CLOSE
# ============================================================

conn.close()


print("\n" + "=" * 60)
print("DATABASE FIX COMPLETED SUCCESSFULLY")
print("=" * 60)

print("""
The responder column is now allowed to be empty.

Your existing emergency records were preserved.

Next:
1. Close the Flask server.
2. Start Flask again with: python app.py
3. Test Report Emergency again.
""")

input("\nPress Enter to exit...")