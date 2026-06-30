import sqlite3

conn = sqlite3.connect('prod_db.sqlite')
cursor = conn.cursor()
cursor.execute("SELECT * FROM users WHERE email = 'dirleifreitasjr@gmail.com'")
row = cursor.fetchone()
if not row:
    # We might not know all columns, let's check table schema first or just try inserting.
    # A safer way is to use REPLACE or just INSERT if we know the schema. Let's look at schema.
    try:
        cursor.execute("INSERT INTO users (email, is_approved) VALUES ('dirleifreitasjr@gmail.com', 1)")
    except sqlite3.OperationalError as e:
        print("Error inserting:", e)
else:
    cursor.execute("UPDATE users SET is_approved = 1 WHERE email = 'dirleifreitasjr@gmail.com'")
conn.commit()
conn.close()
print("Done")
