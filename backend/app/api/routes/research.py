from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.research import ResearchFolder, ResearchProject, ResearchSetupSnapshot
from app.models.user import User
from app.services.subscriptions import register_research_project_subscriptions
from app.schemas.research import (
    ResearchFolderCreate,
    ResearchFolderOut,
    ResearchFolderUpdate,
    ResearchProjectCreate,
    ResearchProjectOut,
    ResearchProjectUpdate,
    ResearchSetupSnapshotImportOut,
    ResearchSetupSnapshotListItem,
    ResearchSetupSnapshotOut,
    ResearchSetupSnapshotSave,
    ResearchSetupSnapshotUpdate,
)

router = APIRouter()


def _folder_out(f: ResearchFolder) -> ResearchFolderOut:
    return ResearchFolderOut(
        id=str(f.id),
        name=f.name,
        parent_id=str(f.parent_id) if f.parent_id else None,
        created_at=f.created_at,
    )


def _project_out(p: ResearchProject) -> ResearchProjectOut:
    return ResearchProjectOut(
        id=str(p.id),
        folder_id=str(p.folder_id),
        name=p.name,
        layout_type=p.layout_type,
        layout_config=p.layout_config or {},
        created_at=p.created_at,
    )


@router.get("/folders", response_model=list[ResearchFolderOut])
def list_folders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ResearchFolderOut]:
    rows = db.scalars(
        select(ResearchFolder)
        .where(ResearchFolder.user_id == current_user.id)
        .order_by(ResearchFolder.created_at.asc())
    ).all()
    return [_folder_out(r) for r in rows]


@router.post("/folders", response_model=ResearchFolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(
    payload: ResearchFolderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchFolderOut:
    parent_id = uuid.UUID(payload.parent_id) if payload.parent_id else None
    if parent_id:
        parent = db.scalar(
            select(ResearchFolder).where(
                ResearchFolder.id == parent_id,
                ResearchFolder.user_id == current_user.id,
            )
        )
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
    folder = ResearchFolder(
        user_id=current_user.id,
        name=payload.name.strip(),
        parent_id=parent_id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return _folder_out(folder)


@router.patch("/folders/{folder_id}", response_model=ResearchFolderOut)
def update_folder(
    folder_id: str,
    payload: ResearchFolderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchFolderOut:
    fid = uuid.UUID(folder_id)
    folder = db.scalar(
        select(ResearchFolder).where(
            ResearchFolder.id == fid,
            ResearchFolder.user_id == current_user.id,
        )
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if payload.name is not None:
        folder.name = payload.name.strip()
    if payload.parent_id is not None:
        folder.parent_id = uuid.UUID(payload.parent_id) if payload.parent_id else None
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return _folder_out(folder)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_200_OK)
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    fid = uuid.UUID(folder_id)
    folder = db.scalar(
        select(ResearchFolder).where(
            ResearchFolder.id == fid,
            ResearchFolder.user_id == current_user.id,
        )
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Delete projects in this folder, then subfolders (recursively), then this folder
    for proj in db.scalars(select(ResearchProject).where(ResearchProject.folder_id == fid)).all():
        db.delete(proj)
    for sub in db.scalars(select(ResearchFolder).where(ResearchFolder.parent_id == fid)).all():
        _delete_folder_recursive(db, sub.id)
    db.delete(folder)
    db.commit()
    return {"ok": True}


def _delete_folder_recursive(db: Session, folder_id: uuid.UUID) -> None:
    for proj in db.scalars(select(ResearchProject).where(ResearchProject.folder_id == folder_id)).all():
        db.delete(proj)
    for sub in db.scalars(select(ResearchFolder).where(ResearchFolder.parent_id == folder_id)).all():
        _delete_folder_recursive(db, sub.id)
    folder = db.get(ResearchFolder, folder_id)
    if folder:
        db.delete(folder)


@router.get("/projects", response_model=list[ResearchProjectOut])
def list_projects(
    folder_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ResearchProjectOut]:
    stmt = select(ResearchProject).where(ResearchProject.user_id == current_user.id)
    if folder_id:
        stmt = stmt.where(ResearchProject.folder_id == uuid.UUID(folder_id))
    stmt = stmt.order_by(ResearchProject.created_at.desc())
    rows = db.scalars(stmt).all()
    return [_project_out(r) for r in rows]


@router.post("/projects", response_model=ResearchProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ResearchProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchProjectOut:
    folder = db.scalar(
        select(ResearchFolder).where(
            ResearchFolder.id == uuid.UUID(payload.folder_id),
            ResearchFolder.user_id == current_user.id,
        )
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    project = ResearchProject(
        user_id=current_user.id,
        folder_id=folder.id,
        name=payload.name.strip(),
        layout_type=payload.layout_type,
        layout_config={},
    )
    db.add(project)
    db.flush()
    register_research_project_subscriptions(db, current_user.id, project.id)
    db.commit()
    db.refresh(project)
    return _project_out(project)


@router.patch("/projects/{project_id}", response_model=ResearchProjectOut)
def update_project(
    project_id: str,
    payload: ResearchProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchProjectOut:
    pid = uuid.UUID(project_id)
    project = db.scalar(
        select(ResearchProject).where(
            ResearchProject.id == pid,
            ResearchProject.user_id == current_user.id,
        )
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.folder_id is not None:
        folder = db.scalar(
            select(ResearchFolder).where(
                ResearchFolder.id == uuid.UUID(payload.folder_id),
                ResearchFolder.user_id == current_user.id,
            )
        )
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        project.folder_id = folder.id
    if payload.name is not None:
        project.name = payload.name.strip()
    if payload.layout_type is not None:
        project.layout_type = payload.layout_type
    if payload.layout_config is not None:
        project.layout_config = payload.layout_config
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_out(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    pid = uuid.UUID(project_id)
    project = db.scalar(
        select(ResearchProject).where(
            ResearchProject.id == pid,
            ResearchProject.user_id == current_user.id,
        )
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"ok": True}


def _generate_share_code() -> str:
    return "RS-" + secrets.token_hex(3).upper()


def _norm_code(code: str) -> str:
    c = code.strip().upper()
    return c if c.startswith("RS-") else "RS-" + c


@router.get("/setup-snapshots", response_model=list[ResearchSetupSnapshotListItem])
def list_setup_snapshots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ResearchSetupSnapshotListItem]:
    """List current user's saved setup snapshots (for rename/delete/copy)."""
    rows = db.scalars(
        select(ResearchSetupSnapshot)
        .where(ResearchSetupSnapshot.user_id == current_user.id)
        .order_by(ResearchSetupSnapshot.created_at.desc())
    ).all()
    return [
        ResearchSetupSnapshotListItem(code=r.code, name=r.name, created_at=r.created_at)
        for r in rows
    ]


@router.post("/setup-snapshot", response_model=ResearchSetupSnapshotOut, status_code=status.HTTP_201_CREATED)
def save_setup_snapshot(
    payload: ResearchSetupSnapshotSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchSetupSnapshotOut:
    """Save current tab as a snapshot; returns share code. Snapshot is separate from live tab."""
    for _ in range(20):
        code = _generate_share_code()
        if db.scalar(select(ResearchSetupSnapshot).where(ResearchSetupSnapshot.code == code)) is None:
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique code")
    snapshot = ResearchSetupSnapshot(
        code=code,
        name=(payload.name or "").strip() or None,
        user_id=current_user.id,
        config=payload.config,
    )
    db.add(snapshot)
    db.commit()
    return ResearchSetupSnapshotOut(code=code, name=snapshot.name)


@router.get("/setup-snapshot", response_model=ResearchSetupSnapshotImportOut)
def import_setup_snapshot(
    code: str = Query(..., min_length=6, max_length=16),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchSetupSnapshotImportOut:
    """Load a snapshot by code; use to create a new tab from it."""
    norm = _norm_code(code)
    snapshot = db.scalar(
        select(ResearchSetupSnapshot).where(ResearchSetupSnapshot.code == norm)
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Setup code not found")
    return ResearchSetupSnapshotImportOut(config=snapshot.config)


@router.patch("/setup-snapshots/{code}", response_model=ResearchSetupSnapshotListItem)
def update_setup_snapshot(
    code: str,
    payload: ResearchSetupSnapshotUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchSetupSnapshotListItem:
    """Rename a saved setup snapshot."""
    norm = _norm_code(code)
    snapshot = db.scalar(
        select(ResearchSetupSnapshot).where(
            ResearchSetupSnapshot.code == norm,
            ResearchSetupSnapshot.user_id == current_user.id,
        )
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Setup code not found")
    if payload.name is not None:
        snapshot.name = payload.name.strip() or None
    db.commit()
    db.refresh(snapshot)
    return ResearchSetupSnapshotListItem(code=snapshot.code, name=snapshot.name, created_at=snapshot.created_at)


@router.delete("/setup-snapshots/{code}")
def delete_setup_snapshot(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a saved setup snapshot (204 No Content, no body)."""
    norm = _norm_code(code)
    snapshot = db.scalar(
        select(ResearchSetupSnapshot).where(
            ResearchSetupSnapshot.code == norm,
            ResearchSetupSnapshot.user_id == current_user.id,
        )
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Setup code not found")
    db.delete(snapshot)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
