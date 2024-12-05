import tkinter as tk
from tkinter import messagebox
import sqlite3
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import os
import ttkbootstrap as ttkb
from ttkbootstrap.tableview import Tableview  # Correct import
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

# SQLite Database Setup
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
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO documents (name, doc_index, folder, url) VALUES (?, ?, ?, ?)", 
                       (name, index, folder, url))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred while accessing the database: {e}")

# Regex for extracting index
def extract_index(filename):
    """Extract index from PDF name using regex."""
    match = re.search(r'CKS\s*(\d+)(?:-(\d{8})(?:\(\d+\))?)?\s*(?:\.pdf)?$', filename)
    return match.group(1) if match else None

# Recursive function to explore folder and its subfolders
def explore_folder(service, folder_id, tableview, parent_node=None):
    """Recursively explore a folder and list files in all its subfolders."""
    file_count = 0
    page_token = None

    while True:
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            response = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, webViewLink, parents)",
                pageToken=page_token
            ).execute()

            files = response.get('files', [])
            if not files:
                break

            for item in files:
                if item['mimeType'] == 'application/vnd.google-apps.folder':
                    folder_file_count = explore_folder(service, item['id'], tableview, parent_node)
                    file_count += folder_file_count
                else:
                    index = extract_index(item['name'])
                    folder_name = get_folder_name(service, item['parents'][0])
                    
                    # Handle NoneType for index
                    if index is None:
                        index = "N/A"  # Use a placeholder or skip this file
                    
                    insert_into_db(item['name'], index, folder_name, item['webViewLink'])
                    
                    # Update Tableview
                    row = [(item['name'], index, folder_name, item['webViewLink'])]
                    tableview.insert_rows("end", row)  # Append rows to the end

                    file_count += 1

            page_token = response.get('nextPageToken', None)
            if not page_token:
                break
        except HttpError as error:
            messagebox.showerror("Error", f"Failed to fetch files: {error}")
            break
        except Exception as e:
            messagebox.showerror("Unexpected Error", f"An unexpected error occurred: {str(e)}")
            break

    return file_count


# Get the folder name using the folder ID
def get_folder_name(service, folder_id):
    """Get the folder name using the folder ID."""
    folder = service.files().get(fileId=folder_id, fields='name').execute()
    return folder['name']

# Fetch Folders from Google Drive
def fetch_drive_folders(service):
    """Fetch folders from Google Drive."""
    try:
        # List all folders in the Drive (excluding trashed ones)
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)"
        ).execute()
        
        folders = results.get('files', [])
        return folders
    except HttpError as error:
        messagebox.showerror("Error", f"Failed to fetch folders: {error}")
        return []

# GUI Components
class DriveGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Google Drive to SQLite")

        # Authenticate and set up the Google Drive service
        creds = authenticate()
        self.service = build('drive', 'v3', credentials=creds)

        # Initialize the SQLite database
        init_db()

        # Create a button to load folders and display data
        self.load_button = ttkb.Button(root, text="Select Folders", command=self.select_folders)
        self.load_button.pack(pady=10)

        # Tableview to display the data
        self.tableview = Tableview(root, coldata=[
            {"text": "Name", "stretch": True},
            {"text": "Index", "stretch": False},
            {"text": "Folder", "stretch": False},
            {"text": "URL", "stretch": False}
        ], rowdata=[], paginated=True, searchable=True, bootstyle="PRIMARY")
        self.tableview.pack(fill="both", expand=True, padx=5, pady=5)

        self.load_data_button = ttkb.Button(root, text="Load Data", command=self.load_data)
        self.load_data_button.pack(pady=10)

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

        # Create a frame for checkboxes
        checkboxes_frame = ttkb.Frame(popup)
        checkboxes_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Dictionary to hold the selected folder ids
        selected_folders = {}

        # Function to create a checkbox for each folder
        def create_checkbox(folder):
            folder_name = folder['name']
            folder_id = folder['id']
            var = tk.BooleanVar()
            checkbox = ttkb.Checkbutton(checkboxes_frame, text=folder_name, variable=var)
            checkbox.pack(anchor="w")
            selected_folders[folder_id] = var

        # Create checkboxes for each folder
        for folder in folders:
            create_checkbox(folder)

        # Search functionality to filter folders
        def filter_folders():
            query = search_var.get().lower()
            for checkbox in checkboxes_frame.winfo_children():
                checkbox.pack_forget()  # Remove all checkboxes
            for folder in folders:
                if query in folder['name'].lower():
                    create_checkbox(folder)  # Add checkbox if name matches search

        search_bar.bind("<KeyRelease>", lambda event: filter_folders())

        # Add button to confirm selection
        def confirm_selection():
            selected_ids = [folder_id for folder_id, var in selected_folders.items() if var.get()]
            for folder_id in selected_ids:
                self.process_folder(folder_id)
            popup.destroy()

        confirm_button = ttkb.Button(popup, text="Confirm", command=confirm_selection)
        confirm_button.pack(pady=10)

    def process_folder(self, folder_id):
        """Process files in a selected folder."""
        files = explore_folder(self.service, folder_id, self.tableview)  # Pass self.tableview to explore_folder
        if files == 0:
            messagebox.showinfo("No Files", "The selected folder contains no files.")
        else:
            messagebox.showinfo("Success", f"Folder processed and stored in database!")

    def load_data(self):
        """Load and display data from SQLite database into Tableview."""
        db_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "documents.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name, doc_index, folder, url FROM documents")  # Ensure columns match Tableview
        rows = cursor.fetchall()
        conn.close()

        # Clear existing data in Tableview
        self.tableview.delete_rows()  # Clear all rows in Tableview

        # Insert new data into Tableview
        for row in rows:
            self.tableview.insert_rows("end", [row])  # Insert rows one at a time


# Main Application
if __name__ == "__main__":
    root = ttkb.Window(themename="darkly")
    app = DriveGUI(root)
    root.mainloop()
