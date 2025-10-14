from flask import Flask, render_template, jsonify, request
import psycopg2
import os

app = Flask(__name__)

# ---- Database Config ----
DB = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'dbname': os.environ.get('DB_NAME', 'theo_hour_attendance'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASS', 'Vonlucille03')
}

API_KEY = os.environ.get('TAP_API_KEY', 'super-secret-token')

def get_conn():
    return psycopg2.connect(
        host=DB["host"],
        dbname=DB["dbname"],
        user=DB["user"],
        password=DB["password"],
        options='-c client_encoding=UTF8'
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/api/latest")
def latest():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT idnumber, firstname, middlename, lastname, time
        FROM lst_student_attendance
        ORDER BY time DESC
        LIMIT 1
    """)
    latest = cur.fetchone()
    conn.close()

    if not latest:
        return jsonify({"status": "waiting", "message": "No attendance yet"}), 200

    idnumber, firstname, middlename, lastname, time = latest
    fullname = f"{firstname} {middlename or ''} {lastname or ''}".strip()
    return jsonify({
        "status": "success",
        "idnumber": idnumber,
        "firstname": firstname,
        "middlename": middlename,
        "lastname": lastname,
        "fullname": fullname,
        "time": str(time)
    })



@app.route("/api/record", methods=["POST"])
def record_attendance():
    data = request.get_json()
    carduid = data.get("carduid")

    if not carduid:
        return jsonify({"status": "error", "message": "No CardUID sent"}), 400

    # Connect to DB
    conn = get_conn()
    cur = conn.cursor()

    # Check if card exists in lst_student
    cur.execute("""
        SELECT idnumber, firstname, middlename, lastname
        FROM lst_student
        WHERE carduid = %s
    """, (carduid,))
    student = cur.fetchone()

    if not student:
        conn.close()
        print(f"⚠️ Unknown card: {carduid}")
        return jsonify({"status": "error", "message": "Unknown card"}), 404

    idnumber, firstname, middlename, lastname = student

    # Insert attendance record
    cur.execute("""
        INSERT INTO lst_student_attendance (idnumber, carduid, firstname, middlename, lastname)
        VALUES (%s, %s, %s, %s, %s)
    """, (idnumber, carduid, firstname, middlename, lastname))
    conn.commit()
    conn.close()

    fullname = f"{firstname} {middlename or ''} {lastname or ''}".strip()
    print(f"Attendance recorded for {fullname} ({idnumber})")

    return jsonify({
        "status": "success",
        "idnumber": idnumber,
        "firstname": firstname,
        "middlename": middlename,
        "lastname": lastname,
        "message": "Attendance Recorded"
    }), 201





if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
