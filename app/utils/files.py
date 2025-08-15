import uuid
from pathlib import Path
from fastapi import UploadFile

async def save_upload_to_tmp(file: UploadFile) -> str:
    """
    Save an UploadFile to a deterministic tmp path and return the path string.
    Raises ValueError for empty files.
    """
    suffix = Path(file.filename).suffix or ".webm"
    tmp_dir = Path("/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
    data = await file.read()
    if not data:
        raise ValueError("Empty audio file")
    with open(tmp_path, "wb") as f:
        f.write(data)
    return str(tmp_path)

async def save_upload_to_folder(file: UploadFile, folder: Path) -> dict:
    """
    Save uploaded file to provided folder. Returns metadata dict.
    """
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / file.filename
    data = await file.read()
    if not data:
        raise ValueError("Empty audio file")
    with open(dest, "wb") as f:
        f.write(data)
    return {"path": str(dest), "filename": file.filename, "content_type": file.content_type, "size": len(data)}
