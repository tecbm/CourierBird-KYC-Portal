import os
import json
from io import BytesIO
from flask import Flask, request, render_template
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__)

# Personal Account Email
PERSONAL_EMAIL = "operations@bhayajimercantile.com"

def get_drive_service():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable is missing!")
    
    creds_json = creds_json.strip()
    creds_dict = json.loads(creds_json)
    
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, 
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build('drive', 'v3', credentials=creds)

MAIN_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

@app.route('/kyc', methods=['GET'])
def kyc_form():
    return render_template('kyc_form.html')

@app.route('/submit_kyc', methods=['POST'])
def submit_kyc():
    try:
        if not MAIN_FOLDER_ID:
            return "Error: GOOGLE_DRIVE_FOLDER_ID is missing!", 500

        drive_service = get_drive_service()

        company_name = request.form.get('company_name', 'Unknown_Company').strip().replace(" ", "_")
        pan_number = request.form.get('pan_number', '')
        gst_number = request.form.get('gst_number', '')
        contact_person = request.form.get('contact_person', '')
        phone = request.form.get('phone', '')
        email = request.form.get('email', '')

        # 1. Create Main Company Sub-folder inside your Shared Folder
        # (Is folder ka main owner aapka personal email rahega kyunki main folder aapka hai)
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

        # 2. Upload text details file inside sub-folder (supportsAllDrives configuration included)
        details_content = f"Company Name: {company_name}\nPAN: {pan_number}\nGST: {gst_number}\nContact: {contact_person}\nPhone: {phone}\nEmail: {email}\n"
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

        # 3. Upload structural attachments inside sub-folder
        uploaded_files = request.files.getlist('files')
        for file in uploaded_files:
            if file and file.filename != '':
                file_metadata = {
                    'name': file.filename,
                    'parents': [subfolder_id]
                }
                file_media = MediaIoBaseUpload(file.stream, mimetype=file.content_type if file.content_type else 'application/octet-stream', resumable=False)
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
