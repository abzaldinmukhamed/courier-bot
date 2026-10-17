import os
from google_auth_oauthlib.flow import InstalledAppFlow

# Расширенные права: доступ к Google Sheets и Google Drive
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

current_dir = os.path.dirname(os.path.abspath(__file__))
creds_path = os.path.join(current_dir, 'credentials.json')
token_path = os.path.join(current_dir, 'token.json')

flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
creds = flow.run_local_server(port=0, open_browser=False)

with open(token_path, 'w') as token:
    token.write(creds.to_json())

print(f"\n✅ Новый token.json с полными правами успешно создан!")