from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from AINDY.core.execution_helper import execute_with_pipeline_sync
from apps.search.schemas.seo import SEOInput, MetaInput
from apps.analytics.services.calculation_services import save_calculation
from AINDY.services.auth_service import get_current_user
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from apps.search.services.search_service import (
    analyze_seo_content,
    generate_meta as generate_meta_result,
    suggest_seo_improvements,
)

router = APIRouter(prefix="/seo", tags=["SEO"], dependencies=[Depends(get_current_user)])


def _execute_seo(request: Request, route_name: str, handler, *, db: Session | None = None):
    metadata = {"source": "seo_routes"}
    if db is not None:
        metadata["db"] = db
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        metadata=metadata,
    )


class LegacyContentInput(BaseModel):
    content: str


@router.post("/analyze")
@limiter.limit("30/minute")
def analyze_seo(
    request: Request,
    data: SEOInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    results = analyze_seo_content(data.text, data.top_n, db=db, user_id=str(current_user["sub"]))

    # Save key SEO metrics
    save_calculation(db, "seo_readability", results["readability"])
    save_calculation(db, "seo_word_count", results["word_count"])

    # Optionally save average density
    avg_density = 0.0
    if results["keyword_densities"]:
        avg_density = sum(results["keyword_densities"].values()) / len(results["keyword_densities"])
        save_calculation(db, "seo_avg_keyword_density", round(avg_density, 2))

    def handler(_ctx):
        return results
    return _execute_seo(request, "seo.analyze", handler, db=db)

@router.post("/meta")
@limiter.limit("30/minute")
def generate_meta(request: Request, data: MetaInput):
    def handler(_ctx):
        return generate_meta_result(data.text, data.limit)
    return _execute_seo(request, "seo.meta", handler)


@router.post("/suggest")
@limiter.limit("30/minute")
def suggest_improvements(
    request: Request,
    data: SEOInput,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(_ctx):
        return suggest_seo_improvements(data.text, data.top_n, db=db, user_id=str(current_user["sub"]))
    return _execute_seo(request, "seo.suggest", handler, db=db)


@router.post("/analyze_seo/")
@limiter.limit("30/minute")
def analyze_seo_compat(request: Request, data: LegacyContentInput, db: Session = Depends(get_db)):
    def handler(_ctx):
        return analyze_seo_content(data.content, 10, db=db)
    return _execute_seo(request, "seo.analyze.compat", handler, db=db)


@router.post("/generate_meta/")
@limiter.limit("30/minute")
def generate_meta_compat(request: Request, data: LegacyContentInput):
    def handler(_ctx):
        return generate_meta_result(data.content, 160)
    return _execute_seo(request, "seo.meta.compat", handler)


@router.post("/suggest_improvements/")
@limiter.limit("30/minute")
def suggest_improvements_compat(request: Request, data: LegacyContentInput, db: Session = Depends(get_db)):
    def handler(_ctx):
        return suggest_seo_improvements(data.content, db=db)
    return _execute_seo(request, "seo.suggest.compat", handler, db=db)

