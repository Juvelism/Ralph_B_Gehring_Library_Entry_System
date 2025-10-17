from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import psycopg2
import os
import sys
from flask import Response
import csv
from io import StringIO
from datetime import datetime


from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_session import Session


sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # allow browser connections
app.secret_key = "super-secret-key"
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)


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
    writer.writerow(['ID Number', 'First Name',
                    'Middle Name', 'Last Name', 'Time In'])
    writer.writerows(rows)
    output.seek(0)

    filename = f"attendance_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# --- ADMIN LOGIN PAGE ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT password FROM lst_admin WHERE admin_name = %s", (username,))
        admin = cur.fetchone()
        conn.close()

        if admin and password == admin[0]:
            session['admin'] = username
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
            return redirect(url_for('admin_login'))

    return render_template('login.html')


# --- DASHBOARD PAGE ---
@app.route('/dashboard')
def dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    limit = 15
    offset = (page - 1) * limit

    conn = get_conn()
    cur = conn.cursor()

    # --- If search query is active ---
    if search_query:
        cur.execute("""
            SELECT idnumber, carduid, firstname, middlename, lastname
            FROM lst_student
            WHERE idnumber ILIKE %s
               OR firstname ILIKE %s
               OR middlename ILIKE %s
               OR lastname ILIKE %s
            ORDER BY idnumber ASC
            LIMIT %s OFFSET %s
        """, (
            f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", limit, offset
        ))
        students = cur.fetchall()

        # 🔹 new cursor for count query
        cur2 = conn.cursor()
        cur2.execute("""
            SELECT COUNT(*) FROM lst_student
            WHERE idnumber ILIKE %s
               OR firstname ILIKE %s
               OR middlename ILIKE %s
               OR lastname ILIKE %s
        """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
        total_students = cur2.fetchone()[0]
        cur2.close()
    else:
        cur.execute("""
            SELECT idnumber, carduid, firstname, middlename, lastname
            FROM lst_student
            ORDER BY idnumber ASC
            LIMIT %s OFFSET %s
        """, (limit, offset))
        students = cur.fetchall()

        cur2 = conn.cursor()
        cur2.execute("SELECT COUNT(*) FROM lst_student")
        total_students = cur2.fetchone()[0]
        cur2.close()

    conn.close()

    total_pages = (total_students + limit - 1) // limit

    return render_template(
        'dashboard.html',
        students=students,
        page=page,
        total_pages=total_pages,
        search_query=search_query
    )


# --- ADD STUDENT ---
@app.route('/add_student', methods=['POST'])
def add_student():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    idnumber = request.form['idnumber']
    carduid = request.form['carduid']
    firstname = request.form['firstname']
    middlename = request.form['middlename']
    lastname = request.form['lastname']

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lst_student (idnumber, carduid, firstname, middlename, lastname)
        VALUES (%s, %s, %s, %s, %s)
    """, (idnumber, carduid, firstname, middlename, lastname))
    conn.commit()
    conn.close()

    flash('Student added successfully!', 'success')
    return redirect(url_for('dashboard'))

# --- EDIT STUDENT ---


@app.route('/edit_student/<idnumber>', methods=['GET', 'POST'])
def edit_student(idnumber):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = get_conn()
    cur = conn.cursor()

    if request.method == 'POST':
        carduid = request.form['carduid']
        firstname = request.form['firstname']
        middlename = request.form['middlename']
        lastname = request.form['lastname']

        cur.execute("""
            UPDATE lst_student
            SET carduid = %s, firstname = %s, middlename = %s, lastname = %s
            WHERE idnumber = %s
        """, (carduid, firstname, middlename, lastname, idnumber))
        conn.commit()
        conn.close()

        flash('Student record updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    # GET request: show the edit form
    cur.execute("""
        SELECT idnumber, carduid, firstname, middlename, lastname
        FROM lst_student
        WHERE idnumber = %s
    """, (idnumber,))
    student = cur.fetchone()
    conn.close()

    return render_template('edit_student.html', student=student)


# --- LOGOUT ---
@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=9000, debug=True)
