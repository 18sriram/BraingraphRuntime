from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.database import DatabaseCreate, DatabaseRead, DatabaseUpdate
from app.services.database_manager import DatabaseManager

router = APIRouter(prefix="/api/databases", tags=["databases"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[DatabaseRead])
def list_databases(db: Session = Depends(get_db)) -> list[DatabaseRead]:
    return DatabaseManager(db).list_databases()


@router.get("/active", response_model=DatabaseRead)
def get_active_database(db: Session = Depends(get_db)) -> DatabaseRead:
    database = DatabaseManager(db).get_active()
    if database is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active database")
    return database


@router.post("", response_model=DatabaseRead, status_code=status.HTTP_201_CREATED)
def add_database(payload: DatabaseCreate, db: Session = Depends(get_db)) -> DatabaseRead:
    try:
        return DatabaseManager(db).add_database(**payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.put("/{database_id}", response_model=DatabaseRead)
def update_database(database_id: int, payload: DatabaseUpdate, db: Session = Depends(get_db)) -> DatabaseRead:
    try:
        database = DatabaseManager(db).update_database(database_id, **payload.model_dump(exclude_unset=True))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if database is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")
    return database


@router.delete("/{database_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_database(database_id: int, db: Session = Depends(get_db)) -> None:
    if not DatabaseManager(db).remove_database(database_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")


@router.post("/{database_id}/activate", response_model=DatabaseRead)
def activate_database(database_id: int, db: Session = Depends(get_db)) -> DatabaseRead:
    database = DatabaseManager(db).set_active(database_id)
    if database is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")
    return database


@router.post("/{database_id}/test")
def test_database_connection(database_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    manager = DatabaseManager(db)
    if manager._get(database_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")
    return {"connected": manager.test_connection(database_id)}