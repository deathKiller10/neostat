from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import DatabaseError
from backend.app.models.document import Document


class DocumentRepository:
    """Sole point of DB access for documents. Routes and services go through this,
    never through a raw Session, so a DB failure always surfaces as DatabaseError.
    """

    def __init__(self, db: Session):
        self.db = db

    def create(self, **fields) -> Document:
        try:
            doc = Document(**fields)
            self.db.add(doc)
            self.db.commit()
            self.db.refresh(doc)
            return doc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise DatabaseError(f"Failed to persist document: {exc}") from exc

    def get_latest_by_name(self, document_name: str) -> Document | None:
        try:
            stmt = (
                select(Document)
                .where(func.lower(Document.document_name) == document_name.lower())
                .order_by(Document.processed_at.desc())
                .limit(1)
            )
            result = self.db.execute(stmt).scalar_one_or_none()
            if result is not None:
                return result

            stem = document_name.rsplit(".", 1)[0].lower()
            stmt = (
                select(Document)
                .where(func.lower(Document.document_name) == stem)
                .order_by(Document.processed_at.desc())
                .limit(1)
            )
            return self.db.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Failed to fetch document: {exc}") from exc

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        document_type: str | None = None,
    ) -> tuple[list[Document], int]:
        try:
            stmt = select(Document).order_by(Document.processed_at.desc())
            count_stmt = select(func.count()).select_from(Document)
            if document_type:
                stmt = stmt.where(Document.document_type == document_type)
                count_stmt = count_stmt.where(Document.document_type == document_type)
            total = self.db.execute(count_stmt).scalar_one()
            items = self.db.execute(stmt.limit(limit).offset(offset)).scalars().all()
            return list(items), total
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Failed to list documents: {exc}") from exc
