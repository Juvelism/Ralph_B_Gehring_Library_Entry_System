from flask import Flask, render_template, jsonify, request
import psycopg2
import os

app = Flask(__name__)

# ---- Database Config ----
DB = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'dbname': os.environ.get('DB_NAME', 'rfid_db'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASS', '')
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
    return jsonify({
        "status": "success",
        "idnumber": idnumber,
        "firstname": firstname,
        "middlename": middlename,
        "lastname": lastname,
        "time": str(time)
    })



@app.route('/api/record', methods=['POST'])
def record():
    key = request.headers.get('X-API-KEY')
    if key != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(force=True)
    carduid = data.get('carduid')
    if not carduid:
        return jsonify({'error': 'Missing carduid'}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT idnumber, firstname, middlename, lastname FROM lst_student WHERE carduid=%s", (carduid,))
    row = cur.fetchone()

    if row:
        idnumber, firstname, middlename, lastname = row
        fullname = f"{firstname} {middlename or ''} {lastname}".strip()
    else:
        idnumber, firstname, middlename, lastname, fullname = None, None, None, None, None

    cur.execute("""
        INSERT INTO lst_student_attendance (idnumber, carduid, firstname, middlename, lastname)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING time
    """, (idnumber, carduid, firstname, middlename, lastname))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        'ok': True,
        'student_idnumber': idnumber,
        'student_name': firstname,
        'carduid': carduid
    }), 201

@app.route("/api/record", methods=["POST"])
def record_attendance():
    data = request.get_json()
    carduid = data.get("carduid")

    if not carduid:
        return jsonify({"status": "error", "message": "No CardUID sent"}), 400

    conn = psycopg2.connect(
        host=DB["host"],
        dbname=DB["dbname"],
        user=DB["user"],
        password=DB["password"],
        options='-c client_encoding=UTF8'
    )
    cur = conn.cursor()

    cur.execute("SELECT idnumber, firstname, middlename, lastname FROM lst_student WHERE carduid = %s", (carduid,))
    student = cur.fetchone()

    if not student:
        conn.close()
        return jsonify({"status": "error", "message": "Unknown card"}), 404

    idnumber, firstname, middlename, lastname = student
    fullname = f"{firstname} {middlename or ''} {lastname or ''}".strip()

    cur.execute("""
        INSERT INTO lst_student_attendance (idnumber, carduid, fullname, time)
        VALUES (%s, %s, %s, NOW())
    """, (idnumber, carduid, fullname))
    conn.commit()
    conn.close()

    print(f"✅ Attendance recorded for {fullname} ({idnumber})")
    return jsonify({
        "status": "success",
        "idnumber": idnumber,
        "firstname": firstname,
        "middlename": middlename,
        "lastname": lastname,
        "fullname": fullname,
        "message": "Attendance Recorded"
    }), 201




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
