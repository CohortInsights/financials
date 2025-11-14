import pickle
import os
import io
import time
import random

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


# ----------------------------------------------------------------------------
# UNIVERSAL RETRY HELPER
# ----------------------------------------------------------------------------

def _retry_api_call(callable_fn, *args, **kwargs):
    """
    Retry Google API calls on transient errors.
    Applies exponential backoff for HTTP 500/502/503/504.
    """
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            return callable_fn(*args, **kwargs)
        except HttpError as e:
            code = e.resp.status if hasattr(e, "resp") else None
            if code in (500, 502, 503, 504):
                sleep = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(sleep)
                continue
            raise  # Non-retryable error → propagate
    raise Exception(f"Google API failed after {max_attempts} attempts")


# ----------------------------------------------------------------------------
# TOKEN / AUTH HELPERS
# ----------------------------------------------------------------------------

def is_folder_type():
    return "mimeType='application/vnd.google-apps.folder'"


def _token_filename(name: str) -> str:
    return f"token.{name}.pickle"


def _delete_file_safely(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def get_credentials(name, scopes):
    """Load + refresh OAuth credentials with safe fallback."""
    creds = None
    token_name = _token_filename(name)

    # Load existing token
    if os.path.exists(token_name):
        try:
            with open(token_name, 'rb') as token:
                creds = pickle.load(token)
        except Exception:
            _delete_file_safely(token_name)
            creds = None

    # Auth flow
    def _reauth():
        cred_file = os.path.join('json', f'{name}.json')
        flow = InstalledAppFlow.from_client_secrets_file(cred_file, scopes)
        fresh = flow.run_local_server(port=0)
        with open(token_name, 'wb') as token:
            pickle.dump(fresh, token)
        return fresh

    # Refresh or re-auth as needed
    if not creds or not creds.valid:
        if creds and getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
            try:
                creds.refresh(Request())
            except Exception:
                _delete_file_safely(token_name)
                creds = _reauth()
        else:
            _delete_file_safely(token_name)
            creds = _reauth()

    return creds


def get_google_drive_service(name):
    SCOPES = ['https://www.googleapis.com/auth/drive']
    creds = get_credentials(name, SCOPES)
    return build('drive', 'v3', credentials=creds)


# ----------------------------------------------------------------------------
# GOOGLE DRIVE WRAPPER (WITH RETRIES + ROBUST DECODE)
# ----------------------------------------------------------------------------

class GoogleDrive:
    def __init__(self, name='credentials', drive=None):
        if drive is None:
            drive = get_google_drive_service(name)
        self.drive = drive

    # -------------------------------------------------------------
    # Robust decode helper (mirrors FinancialsCalculator)
    # -------------------------------------------------------------
    @staticmethod
    def decode_bytes(raw: bytes) -> str:
        """Robust, never-failing decoding chain."""
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            pass
        try:
            return raw.decode("cp1252")
        except Exception:
            pass
        try:
            return raw.decode("latin-1")
        except Exception:
            pass
        return raw.decode("utf-8", errors="backslashreplace")

    def load_csv_from_drive(self, item):
        """
        Downloads & decodes into text (FinancialsCalculator reads DataFrame from string).
        """
        raw = self.download(item.get("id"))
        text = self.decode_bytes(raw)
        text = text.replace("\ufeff", "").replace("\u200b", "").replace("\xa0", " ")
        return text

    # -------------------------------------------------------------
    # Query helpers (all with retry)
    # -------------------------------------------------------------

    def query(self, query, page_size=500):
        """Perform a Drive query, ignoring trashed files."""
        if "trashed" not in query:
            query = f"({query}) and trashed = false"

        request = self.drive.files().list(
            q=query,
            pageSize=page_size,
            spaces='drive',
            fields='nextPageToken, files(id, name, size, mimeType, trashed)'
        )

        # Execute with retry
        response = _retry_api_call(request.execute)
        return response.get('files')

    def by_name(self, name):
        query = f"name='{name}'"
        result = self.query(query)
        if len(result) == 1:
            return result[0]
        return result

    def by_id(self, id):
        request = self.drive.files().get(
            fileId=id,
            fields="id, name, mimeType"
        )
        return _retry_api_call(request.execute)

    def in_dir(self, dir_id, page_size=500):
        query = f"'{dir_id}' in parents"
        return self.query(query, page_size=page_size)

    def child_folders(self, dir_id):
        query = (
            f"'{dir_id}' in parents and "
            f"mimeType='application/vnd.google-apps.folder'"
        )
        return self.query(query)

    def in_dir_with_name(self, dir_id, name):
        query = f"'{dir_id}' in parents and name='{name}'"
        return self.query(query)

    def walk(self, dir, callback, level=0):
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

        if flag and folder_list:
            for subdir in folder_list:
                self.walk(dir=subdir, callback=callback, level=level + 1)

    # -------------------------------------------------------------
    # Download with retry
    # -------------------------------------------------------------

    def download(self, file_id):
        """
        Download raw bytes from Drive.
        Retries *each chunk* on transient errors.
        """
        try:
            request = self.drive.files().get_media(fileId=file_id)
            file = io.BytesIO()
            downloader = MediaIoBaseDownload(file, request)

            done = False
            while not done:
                # Retry each chunk, not the whole download
                status, done = _retry_api_call(downloader.next_chunk)

        except HttpError as error:
            raise Exception(f'Error downloading file: {error}')

        return file.getvalue()
