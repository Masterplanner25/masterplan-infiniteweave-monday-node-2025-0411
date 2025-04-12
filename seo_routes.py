from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from seo import SEOInput, MetaInput
from seo_services import seo_analysis, generate_meta_description
from services import save_calculation
from app.db.database import get_db  # Assuming this is your DB session handler

router = APIRouter()

@router.post("/seo/analyze")
def analyze_seo(data: SEOInput, db: Session = Depends(get_db)):
    results = seo_analysis(data.text, data.top_n)

    # Save key SEO metrics
    save_calculation(db, "seo_readability", results["readability"])
    save_calculation(db, "seo_word_count", results["word_count"])

    # Optionally save average density
    if results["keyword_densities"]:
        avg_density = sum(results["keyword_densities"].values()) / len(results["keyword_densities"])
        save_calculation(db, "seo_avg_keyword_density", round(avg_density, 2))

    return results

@router.post("/seo/meta")
def generate_meta(data: MetaInput):
    return {"meta_description": generate_meta_description(data.text, data.limit)}
