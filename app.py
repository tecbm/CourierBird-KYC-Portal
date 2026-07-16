import os
import sqlite3
import secrets
import zipfile
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file

app = Flask(__name__)

# --- SECURE CONFIGURATION FROM ENVIRONMENT VARIABLES ---
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(16))
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@CourierBird') 

DB_PATH = os.environ.get('DATABASE_URL', 'logistics_kyc.db')
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'static/uploads')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Yahan ab hamesha ke liye link active rahegi, tokens table ki zaroorat nahi hai
    cursor.execute('''CREATE TABLE IF NOT EXISTS kyc_data 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, company_name TEXT, gstin TEXT, pan TEXT, 
                       contact_person TEXT, mobile TEXT, email TEXT, bank_account TEXT, ifsc_code TEXT, 
                       submission_time TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 1. SINGLE PERMANENT KYC LINK ROUTE ---
@app.route('/kyc', methods=['GET'])
def kyc_form():
    # Ab bina kisi token ya restriction ke direct form open hoga
    return render_template('kyc_form.html')

# --- 2. SUBMIT ROUTE FOR ALL CUSTOMERS ---
@app.route('/submit_kyc', methods=['POST'])
def submit_kyc():
    c_name = request.form.get('company_name')
    gstin = request.form.get('gstin')
    pan = request.form.get('pan')
    p_name = request.form.get('contact_person')
    mobile = request.form.get('mobile')
    email = request.form.get('email')
    bank = request.form.get('bank_account')
    ifsc = request.form.get('ifsc_code')
    sub_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO kyc_data (company_name, gstin, pan, contact_person, mobile, email, bank_account, ifsc_code, submission_time)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (c_name, gstin, pan, p_name, mobile, email, bank, ifsc, sub_time))
    conn.commit()
    conn.close()

    doc_fields = ['gst_doc', 'pan_doc', 'aadhaar_doc', 'address_doc', 'cheque_doc']
    for field in doc_fields:
        file = request.files.get(field)
        if file and file.filename != '':
            filename = f"{c_name}_{field}_{file.filename}".replace(" ", "_")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    return f"<h2 style='text-align:center;font-family:sans-serif;color:green;margin-top:50px;'>✅ KYC Submitted Successfully for {c_name}!</h2>"

# --- 3. DOWNLOAD & ADMIN ROUTES ---
@app.route('/download-zip/<int:row_id>', methods=['GET'])
def download_zip(row_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kyc_data WHERE id=?", (row_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return "Data not found.", 404
        
    company_name = row[1]
    c_name_clean = company_name.replace(" ", "_")
    
    csv_headers = "Field,Customer Details\n"
    csv_rows = [
        f"ID,{row[0]}", f"Company Name,{row[1]}", f"GSTIN,{row[2]}", f"PAN,{row[3]}",
        f"Contact Person,{row[4]}", f"Mobile,{row[5]}", f"Email,{row[6]}",
        f"Bank Account,{row[7]}", f"IFSC Code,{row[8]}", f"Submission Time,{row[9]}"
    ]
    csv_data = csv_headers + "\n".join(csv_rows)
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(f"{c_name_clean}_Details.csv", csv_data.encode('utf-8'))
        
        if os.path.exists(UPLOAD_FOLDER):
            all_files = os.listdir(UPLOAD_FOLDER)
            customer_files = [f for f in all_files if f.startswith(f"{c_name_clean}_")]
            for file in customer_files:
                file_path = os.path.join(UPLOAD_FOLDER, file)
                zip_file.write(file_path, arcname=file)
                
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name=f"{c_name_clean}_Complete_KYC.zip")

@app.route('/download-excel', methods=['GET'])
def download_excel():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kyc_data")
    rows = cursor.fetchall()
    conn.close()
    
    csv_data = "ID,Company Name,GSTIN,PAN,Contact Person,Mobile,Email,Bank Account,IFSC Code,Submission Time\n"
    for row in rows:
        cleaned_row = [str(item).replace(",", " ") for item in row]
        csv_data += ",".join(cleaned_row) + "\n"
        
    output = io.BytesIO()
    output.write(csv_data.encode('utf-8'))
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name="CourierBird_Master_KYC_Data.csv")

@app.route('/view-secret-data', methods=['GET', 'POST'])
def view_data():
    password_entered = request.form.get('password', '')
    
    if request.method == 'POST' and password_entered == ADMIN_PASSWORD:
        pass 
    else:
        error_msg = ""
        if request.method == 'POST':
            error_msg = "<p style='color:red;'>❌ Incorrect Password! Try again.</p>"
            
        return f'''
        <div style="font-family:sans-serif; max-width:400px; margin:100px auto; padding:30px; border:1px solid #ccc; border-radius:8px; text-align:center; box-shadow: 0px 4px 10px rgba(0,0,0,0.1);">
            <h2>🦅 Courier Bird Admin Login</h2>
            {error_msg}
            <form method="POST" action="/view-secret-data">
                <input type="password" name="password" placeholder="Enter Admin Password" style="width:100%; padding:10px; margin:15px 0; border:1px solid #ccc; border-radius:4px;" required>
                <button type="submit" style="background:#1e3a8a; color:white; border:none; padding:10px 20px; width:100%; cursor:pointer; border-radius:4px; font-weight:bold;">Access Dashboard</button>
            </form>
        </div>
        '''

    conn = sqlite3.connect(DB_PATH)
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
        .btn { display: inline-block; padding: 6px 12px; background: #f59e0b; color: white; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 12px; }
        .btn-excel { background: #1e3a8a; padding: 10px 20px; font-size: 14px; margin-bottom: 20px; }
    </style>
    <div style="padding: 20px;">
        <h2>🦅 Courier Bird - Received KYC Applications</h2>
        
        <a href="/download-excel" class="btn btn-excel">📥 Download Master Excel (All Data)</a>
        
        <table>
            <tr>
                <th>ID</th><th>Company Name</th><th>GSTIN</th><th>PAN</th><th>Contact Person</th>
                <th>Mobile</th><th>Email</th><th>Bank & IFSC</th><th>Submission Time</th><th>Action</th>
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
                    <a href="/download-zip/{row[0]}" class="btn">📦 Download Complete ZIP</a>
                </td>
            </tr>
        '''
    html += '</table></div>'
    return html

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)