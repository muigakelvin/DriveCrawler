import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.simpledialog import askstring
import sqlite3
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import os
from google.auth.transport.requests import Request


# Google Drive API Setup
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def authenticate():
    """Authenticate with Google APIs."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def init_db():
    """Initialize SQLite database in the same directory as the script."""
    db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "documents.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        doc_index TEXT,    -- Renamed from 'index' to 'doc_index'
                        folder TEXT,
                        url TEXT)''')
    conn.commit()
    conn.close()

def insert_into_db(name, index, folder, url):
    """Insert document info into SQLite database."""
    db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "documents.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO documents (name, index, folder, url) VALUES (?, ?, ?, ?)", 
                   (name, index, folder, url))
    conn.commit()
    conn.close()

# Regex for extracting index
def extract_index(filename):
    """Extract index from PDF name using regex."""
    match = re.search(r'CKS\s*(\d+)(?:-(\d{8})(?:\(\d+\))?)?\s*(?:\.pdf)?$', filename)
    return match.group(0) if match else None

# Fetch Folders from Google Drive
def fetch_drive_folders(service):
    """Fetch folders from Google Drive."""
    try:
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)").execute()
        folders = results.get('files', [])
        return folders
    except HttpError as error:
        messagebox.showerror("Error", f"Failed to fetch folders: {error}")
        return []

# Fetch Files from Folder
def fetch_files_from_folder(service, folder_id):
    """Fetch PDF files from a Google Drive folder (including subfolders)."""
    try:
        query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
        results = service.files().list(q=query, fields="files(id, name, webViewLink)").execute()
        files = results.get('files', [])
        return files
    except HttpError as error:
        messagebox.showerror("Error", f"Failed to fetch files: {error}")
        return []

# GUI Components
class DriveGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Drive to SQLite")

        # Authenticate and set up the Google Drive service
        creds = authenticate()
        self.service = build('drive', 'v3', credentials=creds)

        self.load_button = tk.Button(root, text="Select Folders", command=self.select_folders)
        self.load_button.pack(pady=10)

    def select_folders(self):
        """Display a popup to select folders."""
        folders = fetch_drive_folders(self.service)
        if not folders:
            return

        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title("Select Folders")
        popup.geometry("400x400")

        # Add search bar
        search_var = tk.StringVar()
        search_bar = tk.Entry(popup, textvariable=search_var)
        search_bar.pack(fill="x", padx=5, pady=5)

        # Add treeview
        tree = ttk.Treeview(popup, columns=("Name"), show="headings")
        tree.heading("Name", text="Folder Name")
        tree.pack(fill="both", expand=True, padx=5, pady=5)

        # Populate treeview with folder names
        for folder in folders:
            tree.insert("", "end", values=(folder['name']), iid=folder['id'])

        # Search functionality
        def filter_folders():
            query = search_var.get().lower()
            tree.delete(*tree.get_children())
            for folder in folders:
                if query in folder['name'].lower():
                    tree.insert("", "end", values=(folder['name']), iid=folder['id'])

        search_bar.bind("<KeyRelease>", lambda event: filter_folders())

        # Add buttons to confirm selection
        def confirm_selection():
            selected_ids = tree.selection()
            for folder_id in selected_ids:
                self.process_folder(folder_id)
            popup.destroy()

        confirm_button = tk.Button(popup, text="Confirm", command=confirm_selection)
        confirm_button.pack(pady=10)

    def process_folder(self, folder_id):
        """Process files in a selected folder."""
        files = fetch_files_from_folder(self.service, folder_id)
        if not files:
            return

        for file in files:
            name = file['name']
            index = extract_index(name)
            url = file['webViewLink']
            folder_name = "Selected Folder"
            insert_into_db(name, index, folder_name, url)
        messagebox.showinfo("Success", f"Folder processed and stored in database!")

# Main Application
if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    app = DriveGUI(root)
    root.mainloop()
