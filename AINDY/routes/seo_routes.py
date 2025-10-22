from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from services.seo import SEOInput, MetaInput
from services.seo_services import seo_analysis, generate_meta_description
from services.calculation_services import save_calculation
from db.database import Base
from db.config import get_db    # <- import the dependency from config

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
