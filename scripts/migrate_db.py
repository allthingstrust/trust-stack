import sqlite3
import os

DB_PATH = "truststack.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found. Nothing to migrate.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add screenshot_path
    try:
        cursor.execute("ALTER TABLE content_assets ADD COLUMN screenshot_path TEXT")
        print("Added screenshot_path column.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("screenshot_path column already exists.")
        else:
            print(f"Error adding screenshot_path: {e}")

    # Add visual_analysis
    try:
        cursor.execute("ALTER TABLE content_assets ADD COLUMN visual_analysis TEXT")
        print("Added visual_analysis column.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("visual_analysis column already exists.")
        else:
            print(f"Error adding visual_analysis: {e}")

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
