"""Small, clearly labeled sample records for local development."""

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models import FundingSource, FundingType
from backend.schemas import OpportunityCreate
from backend.services import create_opportunity


def seed():
    with SessionLocal() as db:
        source = db.scalar(select(FundingSource).where(FundingSource.name == "Sample funding directory"))
        if source is None:
            source = FundingSource(name="Sample funding directory", base_url="https://example.org/funding", kind="directory", notes="Demonstration source only")
            db.add(source)
            db.commit()
            db.refresh(source)
        if db.scalar(select(FundingSource).where(FundingSource.name == "Sample funding directory")):
            from backend.models import FundingProgram
            if not db.scalar(select(FundingProgram).where(FundingProgram.title == "Sample Community Growth Grant")):
                create_opportunity(db, OpportunityCreate(source_id=source.id, title="Sample Community Growth Grant", funding_type=FundingType.grant, summary="Demonstration opportunity. Replace with verified information before publication.", url="https://example.org/funding", geography="Canada"))


if __name__ == "__main__":
    seed()
