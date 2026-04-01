from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from core.execution_helper import execute_with_pipeline_sync
from services.seo import SEOInput, MetaInput
from services.calculation_services import save_calculation
from services.auth_service import get_current_user
from db.database import get_db
from services.search_service import generate_meta as generate_meta_result, search_seo, suggest_seo_improvements

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
def analyze_seo(request: Request, data: SEOInput, db: Session = Depends(get_db)):
    results = search_seo(data.text, data.top_n)

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
def generate_meta(request: Request, data: MetaInput):
    def handler(_ctx):
        return generate_meta_result(data.text, data.limit)
    return _execute_seo(request, "seo.meta", handler)


@router.post("/suggest")
def suggest_improvements(request: Request, data: SEOInput):
    def handler(_ctx):
        return suggest_seo_improvements(data.text, data.top_n)
    return _execute_seo(request, "seo.suggest", handler)


@router.post("/analyze_seo/")
def analyze_seo_compat(request: Request, data: LegacyContentInput, db: Session = Depends(get_db)):
    def handler(_ctx):
        return search_seo(data.content, 10)
    return _execute_seo(request, "seo.analyze.compat", handler, db=db)


@router.post("/generate_meta/")
def generate_meta_compat(request: Request, data: LegacyContentInput):
    def handler(_ctx):
        return generate_meta_result(data.content, 160)
    return _execute_seo(request, "seo.meta.compat", handler)


@router.post("/suggest_improvements/")
def suggest_improvements_compat(request: Request, data: LegacyContentInput):
    def handler(_ctx):
        return suggest_seo_improvements(data.content)
    return _execute_seo(request, "seo.suggest.compat", handler)
