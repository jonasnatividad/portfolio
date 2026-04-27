import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth import default
from google.cloud import storage

# ---- Config ----
DRIVE_FOLDER_ID = "your-drive-folder-id"   # Shared Drive folder for this domain
BUCKET_NAME     = "pitchbook-companies"     # GCS landing bucket
DELETE_MODE     = "delete"                  # "delete" (permanent) or "trash"

# Drive MIME types
FOLDER_MIME   = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"

# Export formats for Google Workspace files
EXPORTS = {
    "application/vnd.google-apps.spreadsheet":  ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.document":     ("application/pdf", ".pdf"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}

def _drive():
    creds, _ = default(scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def _gcs():
    return storage.Client()

def _list_children(drive, folder_id):
    """List direct children of a folder (no recursion)."""
    print(f"[list] folder={folder_id}")
    q = f"'{folder_id}' in parents and trashed = false"
    fields = "nextPageToken, files(id,name,mimeType,modifiedTime,shortcutDetails)"
    items, token = [], None
    while True:
        resp = drive.files().list(
            q=q, fields=fields, pageToken=token, pageSize=1000,
            includeItemsFromAllDrives=True, supportsAllDrives=True, spaces="drive"
        ).execute()
        batch = resp.get("files", [])
        print(f"[list] returned {len(batch)} item(s)")
        items.extend(batch)
        token = resp.get("nextPageToken")
        if not token:
            break
    return items

def _resolve_shortcut_if_needed(drive, item):
    """Follow Drive shortcuts to the real file."""
    if item["mimeType"] != SHORTCUT_MIME:
        return item
    target_id = item.get("shortcutDetails", {}).get("targetId")
    if not target_id:
        return item
    real = drive.files().get(
        fileId=target_id,
        fields="id,name,mimeType,modifiedTime"
    ).execute()
    print(f"[shortcut] {item['name']} -> {real['id']} ({real['mimeType']})")
    return real

def _download_bytes(drive, file_obj):
    """
    Return (bytes, output_name).
    Google Workspace files are exported to their conventional formats;
    binary files are downloaded raw.
    """
    mime = file_obj["mimeType"]
    name = file_obj["name"]

    if mime in EXPORTS:
        export_mime, ext = EXPORTS[mime]
        data = drive.files().export_media(fileId=file_obj["id"], mimeType=export_mime).execute()
        out_name = name if name.lower().endswith(ext) else name + ext
        return data, out_name

    buf = io.BytesIO()
    req = drive.files().get_media(fileId=file_obj["id"])
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return buf.read(), name

def _remove_from_drive(drive, file_id):
    """
    Permanently delete a file, with trash fallback if delete is not permitted
    (e.g. file owned by another user in a Shared Drive).
    """
    if DELETE_MODE == "delete":
        try:
            drive.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            print(f"[drive] deleted {file_id}")
        except Exception as e:
            if "404" in str(e) or "insufficientFilePermissions" in str(e):
                drive.files().update(
                    fileId=file_id,
                    body={"trashed": True},
                    supportsAllDrives=True
                ).execute()
                print(f"[drive] could not delete {file_id}, moved to Trash instead")
            else:
                raise
    else:
        drive.files().update(fileId=file_id, body={"trashed": True}, supportsAllDrives=True).execute()
        print(f"[drive] trashed {file_id}")

def sync_newest(request):
    """
    Cloud Run entrypoint (triggered by Cloud Scheduler every minute).
    Moves every file in DRIVE_FOLDER_ID to GCS, then removes it from Drive.
    Subfolders are skipped.
    """
    drive = _drive()
    bucket = _gcs().bucket(BUCKET_NAME)

    items = _list_children(drive, DRIVE_FOLDER_ID)
    if not items:
        print("[sync] folder empty")
        return {"moved_count": 0, "message": "Folder empty."}, 200

    moved = []
    for item in items:
        if item["mimeType"] == FOLDER_MIME:
            print(f"[skip] subfolder: {item['name']}")
            continue

        file_obj = _resolve_shortcut_if_needed(drive, item)
        data, out_name = _download_bytes(drive, file_obj)

        bucket.blob(out_name).upload_from_string(data)
        print(f"[gcs] uploaded gs://{BUCKET_NAME}/{out_name}")

        _remove_from_drive(drive, file_obj["id"])
        moved.append(out_name)

    return {"moved_count": len(moved), "objects": moved}, 200
