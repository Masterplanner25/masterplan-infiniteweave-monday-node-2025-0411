from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from services.seo import SEOInput, MetaInput
from services.seo_services import seo_analysis, generate_meta_description
from services.search_scoring import score_seo_result
from services.calculation_services import save_calculation
from services.auth_service import get_current_user
from db.database import get_db

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.post("/seo/analyze")
def analyze_seo(data: SEOInput, db: Session = Depends(get_db)):
    results = seo_analysis(data.text, data.top_n)

    # Save key SEO metrics
    save_calculation(db, "seo_readability", results["readability"])
    save_calculation(db, "seo_word_count", results["word_count"])

    # Optionally save average density
    avg_density = 0.0
    if results["keyword_densities"]:
        avg_density = sum(results["keyword_densities"].values()) / len(results["keyword_densities"])
        save_calculation(db, "seo_avg_keyword_density", round(avg_density, 2))

    results["search_score"] = score_seo_result(
        readability=results["readability"],
        avg_keyword_density=avg_density,
        word_count=results["word_count"],
    )

    return results

@router.post("/seo/meta")
def generate_meta(data: MetaInput):
    return {"meta_description": generate_meta_description(data.text, data.limit)}
