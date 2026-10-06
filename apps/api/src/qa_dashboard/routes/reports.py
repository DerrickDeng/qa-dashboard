"""Uploaded Playwright HTML reports, served only to signed-in users.

A report holds screenshots, videos, and traces of the application under test, so
it is not a public static folder.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from .. import storage
from .dependencies import CurrentUser

router = APIRouter(tags=["reports"])


@router.get("/reports/{run_id}/{file_path:path}", include_in_schema=False)
def report_file(run_id: str, file_path: str, _: CurrentUser) -> FileResponse:
    target = storage.resolve_report_file(run_id, file_path)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return FileResponse(target)
