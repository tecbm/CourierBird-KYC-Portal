import os
import json
import secrets
from datetime import datetime
from flask import Flask, render_template, request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__)

app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(16))
PARENT_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID', '1nYbGJGfMjGi7V0ffSkP9xjNLQRJfA8AX')
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')

def get_drive_service():
    if GOOGLE_CREDENTIALS_JSON:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=['https://www.googleapis.com/auth/drive']
        )
    else:
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json', scopes=['https://www.googleapis.com/auth/drive']
        )
    return build('drive', 'v3', credentials=creds)

def create_customer_folder(service, company_name):
    file_metadata = {
        'name': f"KYC_{company_name.replace(' ', '_')}",
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [PARENT_FOLDER_ID]
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')

def save_details_to_drive(service, folder_id, data):
    content = f"--- KYC DETAILS ({data['submission_time']}) ---\n\n"
    for key, val in data.items():
        content += f"{key.upper()}: {val}\n"
    
    file_metadata = {
        'name': f"{data['company_name'].replace(' ', '_')}_details.txt",
        'parents': [folder_id]
    }
    
    from io import BytesIO
    media = MediaIoBaseUpload(BytesIO(content.encode('utf-8')), mimetype='text/plain', resumable=True)
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

@app.route('/kyc', methods=['GET'])
def kyc_form():
    return render_template('kyc_form.html')

@app.route('/submit_kyc', methods=['POST'])
def submit_kyc():
    c_name = request.form.get('company_name', '').strip()
    
    data = {
        'company_name': c_name,
        'gstin': request.form.get('gstin'),
        'pan': request.form.get('pan'),
        'contact_person': request.form.get('contact_person'),
        'mobile': request.form.get('mobile'),
        'email': request.form.get('email'),
        'bank_account': request.form.get('bank_account'),
        'ifsc_code': request.form.get('ifsc_code'),
        'submission_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    if not c_name:
        return "Company Name is required.", 400

    try:
        service = get_drive_service()
        customer_folder_id = create_customer_folder(service, c_name)
        save_details_to_drive(service, customer_folder_id, data)
        
        doc_fields = ['gst_doc', 'pan_doc', 'aadhaar_doc', 'address_doc', 'cheque_doc']
        for field in doc_fields:
            file = request.files.get(field)
            if file and file.filename != '':
                filename = f"{c_name.replace(' ', '_')}_{field}_{file.filename}"
                file_metadata = {
                    'name': filename,
                    'parents': [customer_folder_id]
                }
                media = MediaIoBaseUpload(file.stream, mime_type=file.content_type, resumable=True)
                service.files().create(body=file_metadata, media_body=media, fields='id').execute()

        return f"<h2 style='text-align:center;font-family:sans-serif;color:green;margin-top:50px;'>✅ KYC Data & Documents Uploaded Directly to Google Drive for {c_name}!</h2>"

    except Exception as e:
        return f"<h2 style='text-align:center;font-family:sans-serif;color:red;margin-top:50px;'>❌ Error uploading to Google Drive: {str(e)}</h2>", 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
