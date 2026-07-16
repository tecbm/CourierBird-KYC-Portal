import os
import re
import sqlite3
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configurations
UPLOAD_FOLDER = 'customer_documents'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15MB limit
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database Initialize
def init_db():
    conn = sqlite3.connect('logistics_kyc.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer_kyc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT, gstin TEXT, pan_number TEXT,
            contact_person TEXT, mobile TEXT, email TEXT,
            bank_account TEXT, ifsc_code TEXT,
            gst_file TEXT, pan_file TEXT, aadhaar_file TEXT, address_file TEXT, cheque_file TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kyc_links (
            token TEXT PRIMARY KEY,
            created_at TEXT,
            expires_at TEXT,
            status TEXT DEFAULT 'ACTIVE'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/generate-link', methods=['GET'])
def generate_new_link():
    token = secrets.token_urlsafe(16)
    now = datetime.now()
    expiry = now + timedelta(hours=48)
    
    conn = sqlite3.connect('logistics_kyc.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO kyc_links (token, created_at, expires_at) VALUES (?, ?, ?)',
                   (token, now.strftime('%Y-%m-%d %H:%M:%S'), expiry.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    
    domain = request.host_url
    customer_link = f"{domain}kyc/{token}"
    
    return f"""
    <div style="font-family: Arial; margin: 50px; text-align: center;">
        <h2>🔗 New KYC Link Generated</h2>
        <p>Yeh link agle 48 hours tak active rahegi:</p>
        <input type="text" value="{customer_link}" style="width: 500px; padding: 10px; text-align: center;" readonly><br><br>
        <small style="color: red;">Expires on: {expiry.strftime('%d-%b-%Y %I:%M %p')}</small>
    </div>
    """

@app.route('/kyc/<token>', methods=['GET'])
def open_kyc_form(token):
    conn = sqlite3.connect('logistics_kyc.db')
    cursor = conn.cursor()
    cursor.execute('SELECT expires_at, status FROM kyc_links WHERE token = ?', (token,))
    link_info = cursor.fetchone()
    conn.close()
    
    if not link_info:
        return "<h2 style='color:red; text-align:center; margin-top:50px;'>❌ Invalid Link!</h2>", 404
        
    expires_at_str, status = link_info
    expiry_time = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S')
    
    if datetime.now() > expiry_time or status == 'EXPIRED':
        return "<div style='text-align:center; margin-top:100px; font-family:Arial;'><h2 style='color:red;'>⏳ Link Expired!</h2><p>Yeh KYC link 48 hours se purani hai.</p></div>", 403

    return render_template('kyc_form.html', token=token)

@app.route('/submit_kyc/<token>', methods=['POST'])
def submit_kyc(token):
    conn = sqlite3.connect('logistics_kyc.db')
    cursor = conn.cursor()
    cursor.execute('SELECT expires_at, status FROM kyc_links WHERE token = ?', (token,))
    link_info = cursor.fetchone()
    
    if not link_info or datetime.now() > datetime.strptime(link_info[0], '%Y-%m-%d %H:%M:%S') or link_info[1] == 'EXPIRED':
        conn.close()
        return "<h3>❌ Session Expired!</h3>"

    comp_name = request.form.get('company_name')
    gstin = request.form.get('gstin')
    pan = request.form.get('pan').upper()
    person = request.form.get('contact_person')
    mobile = request.form.get('mobile')
    email = request.form.get('email')
    bank_acc = request.form.get('bank_account')
    ifsc = request.form.get('ifsc_code').upper()

    uploaded_paths = {}
    docs = ['gst_doc', 'pan_doc', 'aadhaar_doc', 'address_doc', 'cheque_doc']
    for d in docs:
        file = request.files.get(d)
        if file and file.filename != '':
            filename = f"{secure_filename(comp_name)}_{d}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            uploaded_paths[d] = filename
        else:
            conn.close()
            return f"<h3>❌ File missing for {d}</h3>"

    cursor.execute('''
        INSERT INTO customer_kyc (
            company_name, gstin, pan_number, contact_person, mobile, email, bank_account, ifsc_code,
            gst_file, pan_file, aadhaar_file, address_file, cheque_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        comp_name, gstin, pan, person, mobile, email, bank_acc, ifsc,
        uploaded_paths['gst_doc'], uploaded_paths['pan_doc'], uploaded_paths['aadhaar_doc'], 
        uploaded_paths['address_doc'], uploaded_paths['cheque_doc']
    ))
    
    cursor.execute('UPDATE kyc_links SET status = "EXPIRED" WHERE token = ?', (token,))
    conn.commit()
    conn.close()

    return f"<div style='text-align:center;margin-top:50px;'><h2>✅ KYC Submitted Successfully for {comp_name}!</h2></div>"

if __name__ == '__main__':
    app.run(debug=True, port=8000)