from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import psycopg2
import os
import sys
from flask import Response
import csv
from io import StringIO
from datetime import datetime


sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # allow browser connections

# ---- Database Config ----
DB = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'dbname': os.environ.get('DB_NAME', 'ralph_b_gehring_library_entry'),
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
        # No attendance yet → show waiting screen
        return render_template('index.html', status='waiting')

    idnumber, firstname, middlename, lastname, time = latest
    fullname = f"{firstname} {middlename or ''} {lastname or ''}".strip()

    # Show latest student on the page
    return render_template('index.html', status='success', fullname=fullname, idnumber=idnumber)


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

@app.route("/api/status")
def api_status():
    if os.path.exists("last_status.txt"):
        with open("last_status.txt", "r", encoding="utf-8") as f:
            status = f.read().strip()
        if status == "error":
            os.remove("last_status.txt")
            return jsonify({"status": "error"})
    return jsonify({"status": "ok"})


@app.route("/api/record", methods=["POST"])
def record_attendance():
    data = request.get_json()
    carduid = data.get("carduid")

    if not carduid:
        return jsonify({"status": "error", "message": "No CardUID sent"}), 400

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT idnumber, firstname, middlename, lastname
        FROM lst_student
        WHERE carduid = %s
    """, (carduid,))
    student = cur.fetchone()

    if not student:
        conn.close()
        print(f"⚠️ Unknown card: {carduid}")

        # 🔥 Send instant "unknown" update to browser
        socketio.emit('new_attendance', {
            'status': 'error',
            'message': 'Card Not Registered'
        })

        return jsonify({"status": "error", "message": "Unknown card"}), 404

    idnumber, firstname, middlename, lastname = student

    cur.execute("""
        INSERT INTO lst_student_attendance (idnumber, carduid, firstname, middlename, lastname)
        VALUES (%s, %s, %s, %s, %s)
    """, (idnumber, carduid, firstname, middlename, lastname))
    conn.commit()
    conn.close()

    fullname = f"{firstname} {middlename or ''} {lastname or ''}".strip()
    print(f"✅ Attendance recorded for {fullname} ({idnumber})")

    socketio.emit('new_attendance', {
        'status': 'success',
        'idnumber': idnumber,
        'fullname': fullname
    })

    return jsonify({
        "status": "success",
        "idnumber": idnumber,
        "firstname": firstname,
        "middlename": middlename,
        "lastname": lastname,
        "message": "Attendance Recorded"
    }), 201


@app.route("/download_attendance")
def download_attendance():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT idnumber, firstname, middlename, lastname, time
        FROM lst_student_attendance
        ORDER BY time DESC
    """)
    rows = cur.fetchall()
    conn.close()

    from io import StringIO
    import csv
    from datetime import datetime
    from flask import Response

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID Number', 'First Name', 'Middle Name', 'Last Name', 'Time In'])
    writer.writerows(rows)
    output.seek(0)

    filename = f"attendance_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=9000, debug=True)
