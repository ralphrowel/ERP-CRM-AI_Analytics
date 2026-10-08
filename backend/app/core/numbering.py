from sqlalchemy import BigInteger, Boolean, SmallInteger, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.clock import Clock, get_clock
from app.core.database import Base


class DocumentSequence(Base):
    __tablename__ = "document_sequences"

    doc_type: Mapped[str] = mapped_column(String, primary_key=True)
    prefix: Mapped[str] = mapped_column(String, nullable=False)
    include_year: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    padding: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=6)
    current_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


def generate_next_number(
    db: Session,
    doc_type: str,
    clock: Clock | None = None,
) -> str:
    """
    Generates gapless business document numbers using SELECT ... FOR UPDATE (Roadmap §4.5).
    Runs within the caller's active database transaction.
    """
    current_clock = clock or get_clock()
    current_year = current_clock.today().year

    # Lock sequence row for update
    stmt = select(DocumentSequence).where(DocumentSequence.doc_type == doc_type).with_for_update()
    seq = db.execute(stmt).scalar_one_or_none()

    if seq is None:
        raise ValueError(f"Document sequence configuration for '{doc_type}' not found.")

    # Yearly reset if year changed
    if seq.include_year:
        if seq.current_year != current_year:
            seq.current_year = current_year
            seq.next_value = 1

    current_val = seq.next_value
    seq.next_value += 1

    # Format output e.g. CUS-000001 or INV-2026-000001
    formatted_num = str(current_val).zfill(seq.padding)
    if seq.include_year:
        return f"{seq.prefix}-{seq.current_year}-{formatted_num}"
    return f"{seq.prefix}-{formatted_num}"
