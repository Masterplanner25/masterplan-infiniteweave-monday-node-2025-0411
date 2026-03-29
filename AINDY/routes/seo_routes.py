from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from services.seo import SEOInput, MetaInput
from services.calculation_services import save_calculation
from services.auth_service import get_current_user
from db.database import get_db
from services.search_service import generate_meta as generate_meta_result, search_seo, suggest_seo_improvements

router = APIRouter(dependencies=[Depends(get_current_user)])


class LegacyContentInput(BaseModel):
    content: str


@router.post("/seo/analyze")
def analyze_seo(data: SEOInput, db: Session = Depends(get_db)):
    results = search_seo(data.text, data.top_n)

    # Save key SEO metrics
    save_calculation(db, "seo_readability", results["readability"])
    save_calculation(db, "seo_word_count", results["word_count"])

    # Optionally save average density
    avg_density = 0.0
    if results["keyword_densities"]:
        avg_density = sum(results["keyword_densities"].values()) / len(results["keyword_densities"])
        save_calculation(db, "seo_avg_keyword_density", round(avg_density, 2))

    return results

@router.post("/seo/meta")
def generate_meta(data: MetaInput):
    return generate_meta_result(data.text, data.limit)


@router.post("/seo/suggest")
def suggest_improvements(data: SEOInput):
    return suggest_seo_improvements(data.text, data.top_n)


@router.post("/analyze_seo/")
def analyze_seo_compat(data: LegacyContentInput, db: Session = Depends(get_db)):
    return analyze_seo(SEOInput(text=data.content), db=db)


@router.post("/generate_meta/")
def generate_meta_compat(data: LegacyContentInput):
    return generate_meta(MetaInput(text=data.content))


@router.post("/suggest_improvements/")
def suggest_improvements_compat(data: LegacyContentInput):
    return suggest_seo_improvements(data.content)
