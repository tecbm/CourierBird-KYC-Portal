import os
import sqlite3
import secrets
import zipfile
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, send_file

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# --- STORAGE CONFIGURATION ---
UPLOAD_FOLDER = 'static/uploads'
DB_NAME = 'logistics_kyc.db'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS tokens 
                      (token TEXT PRIMARY KEY, expiry_time TEXT, used INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS kyc_data 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, company_name TEXT, gstin TEXT, pan TEXT, 
                       contact_person TEXT, mobile TEXT, email TEXT, bank_account TEXT, ifsc_code TEXT, 
                       submission_time TEXT)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/generate-link', methods=['GET'])
def generate_link():
    token = secrets.token_urlsafe(16)
    expiry_time = (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tokens (token, expiry_time) VALUES (?, ?)", (token, expiry_time))
    conn.commit()
    conn.close()
    
    base_url = request.host_url.rstrip('/')
    customer_link = f"{base_url}/kyc/{token}"
    
    return f'''
    <div style="font-family:sans-serif; max-width:500px; margin:50px auto; padding:20px; border:1px solid #ccc; border-radius:8px;">
        <h2>Courier Bird - KYC Link Generated</h2>
        <p>This link is valid for 48 hours:</p>
        <input type="text" value="{customer_link}" id="linkInput" style="width:100%; padding:10px; margin-bottom:10px;" readonly>
        <button onclick="navigator.clipboard.writeText(document.getElementById('linkInput').value); alert('Link copied!');" style="background:#1e3a8a; color:white; border:none; padding:10px 15px; cursor:pointer; border-radius:4px;">Copy Link</button>
    </div>
    '''

@app.route('/kyc/<token>', methods=['GET'])
def kyc_form(token):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT expiry_time, used FROM tokens WHERE token=?", (token,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return "<h3>Invalid KYC Link!</h3>", 404
        
    expiry_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
    used = result[1]
    
    if datetime.now() > expiry_time:
        return "<h3>⏳ Link Expired! This KYC link was only valid for 48 hours.</h3>", 403
    if used == 1:
        return "<h3>✅ KYC already submitted using this link.</h3>", 403
        
    return render_template('kyc_form.html', token=token)

@app.route('/submit_kyc/<token>', methods=['POST'])
def submit_kyc(token):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT used FROM tokens WHERE token=?", (token,))
    result = cursor.fetchone()
    
    if not result or result[0] == 1:
        conn.close()
        return "Link invalid or already used.", 403

    c_name = request.form.get('company_name')
    gstin = request.form.get('gstin')
    pan = request.form.get('pan')
    p_name = request.form.get('contact_person')
    mobile = request.form.get('mobile')
    email = request.form.get('email')
    bank = request.form.get('bank_account')
    ifsc = request.form.get('ifsc_code')
    sub_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''INSERT INTO kyc_data (company_name, gstin, pan, contact_person, mobile, email, bank_account, ifsc_code, submission_time)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (c_name, gstin, pan, p_name, mobile, email, bank, ifsc, sub_time))
    
    cursor.execute("UPDATE tokens SET used=1 WHERE token=?", (token,))
    conn.commit()
    conn.close()

    doc_fields = ['gst_doc', 'pan_doc', 'aadhaar_doc', 'address_doc', 'cheque_doc']
    for field in doc_fields:
        file = request.files.get(field)
        if file and file.filename != '':
            filename = f"{c_name}_{field}_{file.filename}".replace(" ", "_")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    return f"<h2 style='text-align:center;font-family:sans-serif;color:green;margin-top:50px;'>✅ KYC Submitted Successfully for {c_name}!</h2>"

# --- ROUTE TO DOWNLOAD ALL FILES OF A CUSTOMER IN A ZIP ---
@app.route('/download-zip/<company_name>', methods=['GET'])
def download_zip(company_name):
    c_name_clean = company_name.replace(" ", "_")
    zip_buffer = io.BytesIO()
    
    if os.path.exists(UPLOAD_FOLDER):
        all_files = os.listdir(UPLOAD_FOLDER)
        # Us company ke saare documents filter karna
        customer_files = [f for f in all_files if f.startswith(f"{c_name_clean}_")]
        
        if not customer_files:
            return "No documents found for this company.", 404
            
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file in customer_files:
                file_path = os.path.join(UPLOAD_FOLDER, file)
                zip_file.write(file_path, arcname=file)
                
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name=f"{c_name_clean}_KYC_Documents.zip")
    
    return "Storage folder not found.", 404

# --- ROUTE TO DOWNLOAD ALL DATA IN EXCEL/CSV SHEET ---
@app.route('/download-excel', methods=['GET'])
def download_excel():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kyc_data")
    rows = cursor.fetchall()
    conn.close()
    
    # Simple CSV formatting
    csv_data = "ID,Company Name,GSTIN,PAN,Contact Person,Mobile,Email,Bank Account,IFSC Code,Submission Time\n"
    for row in rows:
        cleaned_row = [str(item).replace(",", " ") for item in row] # Commas ko text me se hatana takki CSV kharab na ho
        csv_data += ",".join(cleaned_row) + "\n"
        
    output = io.BytesIO()
    output.write(csv_data.encode('utf-8'))
    output.seek(0)
    
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name="CourierBird_KYC_Data.csv")

# --- SECRET DASHBOARD ---
@app.route('/view-secret-data', methods=['GET'])
def view_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kyc_data")
    rows = cursor.fetchall()
    conn.close()
    
    html = '''
    <style>
        table { width: 100%; border-collapse: collapse; font-family: sans-serif; margin-top: 20px;}
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; font-size: 14px; }
        th { background-color: #1e3a8a; color: white; }
        tr:nth-child(even){background-color: #f9f9f9;}
        .btn { display: inline-block; padding: 6px 12px; background: #10b981; color: white; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 12px; }
        .btn-zip { background: #f59e0b; margin-left: 5px; }
        .btn-excel { background: #1e3a8a; padding: 10px 20px; font-size: 14px; margin-bottom: 20px; }
    </style>
    <div style="padding: 20px;">
        <h2>🦅 Courier Bird - Received KYC Applications</h2>
        
        <a href="/download-excel" class="btn btn-excel">📥 Download Full Data (Excel/CSV)</a>
        
        <table>
            <tr>
                <th>ID</th><th>Company Name</th><th>GSTIN</th><th>PAN</th><th>Contact Person</th>
                <th>Mobile</th><th>Email</th><th>Bank & IFSC</th><th>Submission Time</th><th>Actions</th>
            </tr>
    '''
    
    for row in rows:
        html += f'''
            <tr>
                <td>{row[0]}</td>
                <td><b>{row[1]}</b></td>
                <td>{row[2]}</td>
                <td>{row[3]}</td>
                <td>{row[4]}</td>
                <td>{row[5]}</td>
                <td>{row[6]}</td>
                <td>{row[7]}<br><small style="color:#666;">IFSC: {row[8]}</small></td>
                <td>{row[9]}</td>
                <td>
                    <a href="/download-zip/{row[1]}" class="btn btn-zip">📦 Download ZIP</a>
                </td>
            </tr>
        '''
    html += '</table></div>'
    return html

if __name__ == '__main__':
    app.run(port=8000, debug=True)