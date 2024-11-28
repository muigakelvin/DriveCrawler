import os
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import logging
from ttkbootstrap import Style

# Define Google Drive API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

# Global variables to store selected folders and destination folder ID
selected_folders = []
destination_folder_id = None

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

def explore_folder(service, folder_id, parent_node=None):
    """ Recursively explore a folder and list files in all its subfolders. """
    file_count = 0
    page_token = None

    while True:
        # Use the page token to fetch the next page of files
        query = f"'{folder_id}' in parents and trashed=false"
        response = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, webViewLink)",
            pageToken=page_token
        ).execute()

        files = response.get('files', [])
        if not files:
            break

        # Loop through the files/folders in the current folder
        for item in files:
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                # If the item is a folder, add it to the Treeview and explore it recursively
                folder_node = tree.insert(parent_node, 'end', text=f"{item['name']} [0]", values=("Folder", item['webViewLink']))
                folder_file_count = explore_folder(service, item['id'], folder_node)  # Recursive call for subfolders
                # Update the folder node text with the actual file count after recursion
                tree.item(folder_node, text=f"{item['name']} [{folder_file_count}]")
                file_count += folder_file_count  # Add subfolder file count to total
            else:
                # If the item is a file, add it to the current folder's node
                tree.insert(parent_node, 'end', text=item['name'], values=("File", item['webViewLink']))
                file_count += 1

        # Check for a next page of files
        page_token = response.get('nextPageToken', None)
        if not page_token:
            break

    return file_count

def select_folders(tree):
    """Select folders from Google Drive."""
    global selected_folders
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)
    folders = service.files().list(
        q="mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name, webViewLink)"
    ).execute().get('files', [])

    selected_folders = []
    if folders:
        popup = tk.Toplevel()
        popup.title("Select Folders")
        popup.geometry("400x300")
        popup.attributes('-topmost', True)

        # Create a canvas with a scrollbar
        canvas = tk.Canvas(popup)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = tk.Scrollbar(popup, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Create a frame inside the canvas
        frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=frame, anchor=tk.NW)

        def configure_scrollregion(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        frame.bind("<Configure>", configure_scrollregion)

        checkbutton_value = {}

        # Create checkbuttons for folders
        for folder in folders:
            var = tk.IntVar(value=0)
            checkbutton = tk.Checkbutton(frame, text=folder['name'], variable=var)
            checkbutton.pack(anchor=tk.W)
            checkbutton_value[checkbutton] = (var, folder['id'], folder['webViewLink'])

        def get_selected_folders():
            global selected_folders
            total_cumulative_files = 0

            for checkbutton, (var, folder_id, url) in checkbutton_value.items():
                if var.get() == 1:  # Check if the checkbutton is selected
                    folder_name = checkbutton.cget("text")
                    folder_node = tree.insert("", "end", text=f"Exploring folder: {folder_name}", values=("", ""))
                    folder_file_count = explore_folder(service, folder_id, folder_node)  # Recursively explore
                    total_cumulative_files += folder_file_count

                    # Display cumulative files for the selected folder
                    tree.insert(folder_node, "end", text=f"Total Files in {folder_name}", values=(folder_file_count, ""))

            # Show the total cumulative file count across all selected folders
            tree.insert("", "end", text="Total Cumulative Files", values=(total_cumulative_files, ""))

            popup.destroy()

        select_button = tk.Button(popup, text="Select", command=get_selected_folders)
        select_button.pack(pady=10)

# Destination folder selection popup
def select_destination_folder(destination_entry):
    global destination_folder_id
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)
    folders = service.files().list(q="mimeType='application/vnd.google-apps.folder'",
                                   fields="files(id, name, webViewLink)").execute().get('files', [])

    if not folders:
        messagebox.showerror("Error", "No folders found.")
        return

    popup = tk.Toplevel()
    popup.title("Select Destination Folder")
    popup.geometry("400x300")

    canvas = tk.Canvas(popup)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar = tk.Scrollbar(popup, orient=tk.VERTICAL, command=canvas.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.configure(yscrollcommand=scrollbar.set)

    frame = tk.Frame(canvas)
    canvas.create_window((0, 0), window=frame, anchor=tk.NW)

    radio_value = tk.StringVar()
    for folder in folders:
        radio = tk.Radiobutton(frame, text=folder['name'], variable=radio_value, value=folder['id'])
        radio.pack(anchor=tk.W)

    def get_selected_destination_folder():
        global destination_folder_id
        destination_folder_id = radio_value.get()
        if not destination_folder_id:
            messagebox.showerror("Error", "Please select a destination folder.")
            return
        destination_entry.delete(0, tk.END)
        destination_entry.insert(0, destination_folder_id)
        popup.destroy()

    select_button = tk.Button(popup, text="Select", command=get_selected_destination_folder)
    select_button.pack(pady=10)

# Migration logic
def migrate_files(service, progress, progress_label):
    total_files = 0
    for folder_name, folder_id, _ in selected_folders:
        page_token = None
        while True:
            response = service.files().list(q=f"'{folder_id}' in parents and trashed=false",
                                            fields="nextPageToken, files(id, name)", pageToken=page_token).execute()
            files = response.get('files', [])
            if not files:
                break
            for file in files:
                service.files().update(fileId=file['id'], addParents=destination_folder_id,
                                       removeParents=folder_id, fields='id, parents').execute()
                total_files += 1
                progress['value'] += 1
                progress_label.config(text=f"Migrating: {progress['value']} of {progress['maximum']}")
                progress.update_idletasks()
            page_token = response.get('nextPageToken', None)
            if not page_token:
                break

# Start migration in a thread
def start_migration(progress, progress_label):
    if not selected_folders or not destination_folder_id:
        messagebox.showerror("Error", "Select folders and a destination folder.")
        return

    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)

    total_files = sum(explore_folder(service, folder_id) for _, folder_id, _ in selected_folders)
    progress['maximum'] = total_files
    progress['value'] = 0

    threading.Thread(target=migrate_files, args=(service, progress, progress_label)).start()

# Main window setup
def main():
    root = tk.Tk()
    root.geometry("800x600")
    root.title("Google Drive File Migration Tool")

    style = Style(theme="minty")

    folder_frame = tk.Frame(root)
    folder_frame.pack(pady=20)

    folder_button = tk.Button(folder_frame, text="Select Folders", command=lambda: select_folders(tree))
    folder_button.pack(side=tk.LEFT, padx=10)

    destination_label = tk.Label(folder_frame, text="Destination Folder ID:")
    destination_label.pack(side=tk.LEFT, padx=10)

    destination_entry = tk.Entry(folder_frame, width=30)
    destination_entry.pack(side=tk.LEFT)

    destination_button = tk.Button(folder_frame, text="Select Destination Folder",
                                   command=lambda: select_destination_folder(destination_entry))
    destination_button.pack(side=tk.LEFT, padx=10)

    progress = ttk.Progressbar(root, length=600, mode='determinate')
    progress.pack(pady=20)

    progress_label = tk.Label(root, text="")
    progress_label.pack()

    migrate_button = tk.Button(root, text="Start Migration", command=lambda: start_migration(progress, progress_label))
    migrate_button.pack(pady=10)

    tree_frame = tk.Frame(root)
    tree_frame.pack(fill=tk.BOTH, expand=True)

    tree_scrollbar = tk.Scrollbar(tree_frame)
    tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    global tree
    tree = ttk.Treeview(tree_frame, columns=("Type", "Files"), yscrollcommand=tree_scrollbar.set)
    tree.heading("#0", text="Folder/File Name")
    tree.heading("Type", text="Type")
    tree.heading("Files", text="Files")
    tree_scrollbar.config(command=tree.yview)
    tree.pack(fill=tk.BOTH, expand=True)

    root.mainloop()

if __name__ == "__main__":
    main()
