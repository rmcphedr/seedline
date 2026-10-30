"""Local-only demo profile API. Every read and write resolves the cookie server-side."""

import os

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from backend import onboarding as service
from backend import onboarding_schemas as s
from backend.db import get_db


def demo_guard() -> None:
    enabled = os.getenv("ENABLE_DEMO_MODE", "").lower() == "true"
    local = os.getenv("APP_ENV", "").lower() in {"development", "local", "test"}
    deployment = any(os.getenv(name, "").lower() in {"production", "preview", "staging"}
                     for name in ("VERCEL_ENV", "DEPLOYMENT_ENV", "ENVIRONMENT"))
    if not (enabled and local and not deployment):
        raise HTTPException(status_code=404, detail="Not found")


router = APIRouter(prefix="/api/demo", dependencies=[Depends(demo_guard)], tags=["local demo"])


def current_session(seedline_demo: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    return service.resolve_session(db, seedline_demo)


def _create(db: Session, response: Response, display_name: str | None = None, *, example: bool = False):
    token, session = service.create_demo(db, display_name, example=example)
    response.set_cookie(
        key="seedline_demo", value=token, max_age=int(service.SESSION_LIFETIME.total_seconds()),
        httponly=True, samesite="lax", secure=False, path="/",
    )
    return service.context(db, session)


@router.post("/create", response_model=s.DemoContext, status_code=201)
def create_demo(data: s.DemoCreate, response: Response, db: Session = Depends(get_db)):
    return _create(db, response, data.display_name)


@router.post("/example", response_model=s.DemoContext, status_code=201)
def create_example(response: Response, db: Session = Depends(get_db)):
    return _create(db, response, example=True)


@router.post("/reset", response_model=s.DemoContext, status_code=201)
def reset_demo(response: Response, db: Session = Depends(get_db)):
    return _create(db, response)


@router.get("/context", response_model=s.DemoContext)
def get_context(session=Depends(current_session), db: Session = Depends(get_db)):
    return service.context(db, session)


@router.get("/summary", response_model=s.DemoContext)
def get_summary(session=Depends(current_session), db: Session = Depends(get_db)):
    return service.context(db, session)


@router.get("/founder", response_model=s.FounderRead)
def get_founder(session=Depends(current_session), db: Session = Depends(get_db)):
    founder, membership, *_ = service.load(db, session)
    return service.founder_read(founder, membership)


@router.patch("/founder", response_model=s.FounderRead)
def patch_founder(data: s.FounderPatch, session=Depends(current_session), db: Session = Depends(get_db)):
    return service.patch_founder(db, session, data)


@router.get("/organization", response_model=s.OrganizationRead)
def get_organization(session=Depends(current_session), db: Session = Depends(get_db)):
    _, _, organization, *_ = service.load(db, session)
    return service.organization_read(organization)


@router.patch("/organization", response_model=s.OrganizationRead)
def patch_organization(data: s.OrganizationPatch, session=Depends(current_session), db: Session = Depends(get_db)):
    return service.patch_organization(db, session, data)


@router.get("/funding-intent", response_model=s.FundingIntentRead)
def get_funding_intent(session=Depends(current_session), db: Session = Depends(get_db)):
    return service.load(db, session)[3]


@router.patch("/funding-intent", response_model=s.FundingIntentRead)
def patch_funding_intent(data: s.FundingIntentPatch, session=Depends(current_session), db: Session = Depends(get_db)):
    return service.patch_funding_intent(db, session, data)


@router.get("/details", response_model=s.BusinessDetailsRead)
def get_details(session=Depends(current_session), db: Session = Depends(get_db)):
    return service.load(db, session)[4]


@router.patch("/details", response_model=s.BusinessDetailsRead)
def patch_details(data: s.BusinessDetailsPatch, session=Depends(current_session), db: Session = Depends(get_db)):
    return service.patch_details(db, session, data)


@router.get("/interests", response_model=s.InterestsRead)
def get_interests(session=Depends(current_session), db: Session = Depends(get_db)):
    return service.load(db, session)[5]


@router.patch("/interests", response_model=s.InterestsRead)
def patch_interests(data: s.InterestsPatch, session=Depends(current_session), db: Session = Depends(get_db)):
    return service.patch_interests(db, session, data)


@router.get("/onboarding", response_model=s.OnboardingRead)
def get_onboarding(session=Depends(current_session), db: Session = Depends(get_db)):
    return service.load(db, session)[6]


@router.patch("/onboarding", response_model=s.OnboardingRead)
def patch_onboarding(data: s.OnboardingPatch, session=Depends(current_session), db: Session = Depends(get_db)):
    return service.patch_onboarding(db, session, data)


@router.get("/completion", response_model=s.CompletionRead)
def get_completion(session=Depends(current_session), db: Session = Depends(get_db)):
    return service.context(db, session)["completion"]
