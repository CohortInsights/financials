# drive.py
import pickle
import os
import io

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# NEW: catch refresh/invalid token cases cleanly
try:
    from google.auth.exceptions import RefreshError
except Exception:  # fallback if package version differs
    class RefreshError(Exception):
        pass


def is_folder_type():
    """
    Return query condition for a mime_type matching a folder
    """
    return "mimeType='application/vnd.google-apps.folder'"


def _token_filename(name: str) -> str:
    return f"token.{name}.pickle"


def _delete_file_safely(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        # Non-fatal; if deletion fails we'll just overwrite later
        pass


def get_credentials(name, scopes):
    """
    Get credentials; if a cached token exists but is invalid/unrefreshable,
    delete it and run the OAuth flow so the user sees the login dialog.
    """
    creds = None
    token_name = _token_filename(name)

    # Try to load cached token
    if os.path.exists(token_name):
        try:
            with open(token_name, 'rb') as token:
                creds = pickle.load(token)
        except Exception:
            # Corrupt/old token file -> treat as absent
            _delete_file_safely(token_name)
            creds = None

    # If we don't have valid creds, attempt refresh or re-auth
    def _reauth():
        cred_file = os.path.join('json', f'{name}.json')
        flow = InstalledAppFlow.from_client_secrets_file(cred_file, scopes)
        # Use an ephemeral port; launches local browser for consent
        fresh = flow.run_local_server(port=0)
        # Persist the new token
        with open(token_name, 'wb') as token:
            pickle.dump(fresh, token)
        return fresh

    if not creds or not creds.valid:
        # If expired but refreshable, try refresh; on any failure, reauth
        if creds and getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
            try:
                creds.refresh(Request())
            except Exception:
                # Any refresh error (invalid_grant, revoked, network, etc.) -> reauth
                _delete_file_safely(token_name)
                creds = _reauth()
        else:
            # No creds or not refreshable -> reauth
            _delete_file_safely(token_name)
            creds = _reauth()

    return creds


def get_google_drive_service(name):
    """
    Gets authenticated object that can be used to query for google drive contents
    """
    SCOPES = ['https://www.googleapis.com/auth/drive']
    creds = get_credentials(name, SCOPES)
    service = build('drive', 'v3', credentials=creds)
    return service


class GoogleDrive:
    def __init__(self, name='credentials', drive=None):
        """
        Constructor
        """
        if drive is None:
            drive = get_google_drive_service(name)
        self.drive = drive

    def query(self, query, page_size=500):
        """
        Perform a query and return the file results (ignores trashed files).
        """
        if "trashed" not in query:
            query = f"({query}) and trashed = false"

        response = self.drive.files().list(
            q=query,
            pageSize=page_size,
            spaces='drive',
            fields='nextPageToken, files(id, name, size, mimeType, trashed)'
        ).execute()
        return response.get('files')


    def by_name(self, name):
        """
        Perform a query by name
        """
        query = f"name='{name}'"
        result = self.query(query)
        if len(result) == 1:
            result = result[0]
        return result

    def by_id(self, id):
        """
        Perform a query by id
        """
        drive = self.drive
        return drive.files().get(fileId=id, fields="id, name, mimeType").execute()

    def in_dir(self, dir_id, page_size=500):
        """
        Perform a query by directory id
        """
        query = f"'{dir_id}' in parents"
        return self.query(query, page_size=page_size)

    def child_folders(self, dir_id):
        """
        List child folders of a directory
        """
        query = (
            f"'{dir_id}' in parents and "
            f"mimeType='application/vnd.google-apps.folder'"
        )
        return self.query(query)

    def in_dir_with_name(self, dir_id, name):
        """
        Query contents by directory id and exact name
        """
        query = f"'{dir_id}' in parents and name='{name}'"
        return self.query(query)

    def walk(self, dir, callback, level=0):
        """
        Recursive walk starting with top level directory
        """
        dir_id = dir.get('id')
        contents = self.in_dir(dir_id)
        folder_list = []
        file_list = []
        for item in contents:
            mime_type = item.get('mimeType')
            if 'folder' in mime_type:
                folder_list.append(item)
            else:
                file_list.append(item)
        args = (dir, folder_list, file_list, level)
        flag = callback(args)
        if flag and len(folder_list) > 0:
            for subdir in folder_list:
                self.walk(dir=subdir, callback=callback, level=(level + 1))

    def download(self, file_id):
        """
        Download into memory a file object
        """
        try:
            service = self.drive
            request = service.files().get_media(fileId=file_id)
            file = io.BytesIO()
            downloader = MediaIoBaseDownload(file, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        except HttpError as error:
            raise Exception(f'Error downloading file: {error}')
        return file.getvalue()
