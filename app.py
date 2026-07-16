import os
import json
from io import BytesIO
from flask import Flask, request, render_template, redirect
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__)

# Personal Account Email
PERSONAL_EMAIL = "operations@bhayajimercantile.com"

def get_drive_service():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    
    if not all([client_id, client_secret, refresh_token]):
        raise ValueError("Google OAuth credentials missing in Render environment variables!")
    
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    
    return build('drive', 'v3', credentials=creds)

MAIN_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

@app.route('/', methods=['GET'])
def home_redirect():
    return redirect('/kyc')

@app.route('/kyc', methods=['GET'])
def kyc_form():
    return render_template('kyc_form.html')

@app.route('/submit_kyc', methods=['POST'])
def submit_kyc():
    try:
        if not MAIN_FOLDER_ID:
            return "Error: GOOGLE_DRIVE_FOLDER_ID is missing!", 500

        drive_service = get_drive_service()

        # HTML Form Inputs ke naye accurate names (MAPPED CORRECTLY)
        company_name = request.form.get('company_name', 'Unknown_Company').strip().replace(" ", "_")
        gst_number = request.form.get('gstin', '')       # Form name="gstin"
        pan_number = request.form.get('pan', '')         # Form name="pan"
        contact_person = request.form.get('contact_person', '')
        phone = request.form.get('mobile', '')           # Form name="mobile"
        email = request.form.get('email', '')
        bank_account = request.form.get('bank_account', '') # Form name="bank_account"
        ifsc_code = request.form.get('ifsc_code', '')     # Form name="ifsc_code"

        # 1. Company Name Folder banana
        folder_metadata = {
            'name': f"KYC_{company_name}",
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [MAIN_FOLDER_ID.strip()]
        }
        subfolder = drive_service.files().create(
            body=folder_metadata, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        subfolder_id = subfolder.get('id')

        # 2. Text Details File taiyar karna (Naye Fields ke sath)
        details_content = (
            f"Company Name: {company_name}\n"
            f"PAN: {pan_number}\n"
            f"GST: {gst_number}\n"
            f"Contact Person: {contact_person}\n"
            f"Phone: {phone}\n"
            f"Email: {email}\n"
            f"Bank Account: {bank_account}\n"
            f"IFSC Code: {ifsc_code}\n"
        )
        
        text_metadata = {
            'name': f"{company_name}_details.txt",
            'parents': [subfolder_id]
        }
        
        bio = BytesIO(details_content.encode('utf-8'))
        text_media = MediaIoBaseUpload(bio, mimetype='text/plain', resumable=False)
        drive_service.files().create(
            body=text_metadata, 
            media_body=text_media,
            supportsAllDrives=True
        ).execute()

        # 3. HTML ke saare file fields ko loop karke Google Drive par bhejna
        file_fields = ['gst_doc', 'pan_doc', 'aadhaar_doc', 'address_doc', 'cheque_doc']
        for field in file_fields:
            file = request.files.get(field)
            if file and file.filename != '':
                # Purana extension format rakhne ke liye original name use karein
                file_metadata = {
                    'name': f"{field}_{file.filename}",
                    'parents': [subfolder_id]
                }
                file_media = MediaIoBaseUpload(
                    file.stream, 
                    mimetype=file.content_type if file.content_type else 'application/octet-stream', 
                    resumable=False
                )
                drive_service.files().create(
                    body=file_metadata, 
                    media_body=file_media,
                    supportsAllDrives=True
                ).execute()

        return "<h1>KYC Documents Submitted Successfully!</h1><p>Check your Google Drive folder now.</p>", 200

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        error_content = ""
        if hasattr(e, 'content'):
            try:
                error_content = f"\nAPI Response Content: {e.content.decode('utf-8')}"
            except:
                error_content = f"\nAPI Response Content: {str(e.content)}"
        return f"<h1>Error uploading to Google Drive:</h1><pre>{error_details}{error_content}</pre>", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
