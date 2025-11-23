from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from services.seo import SEOInput, MetaInput
from services.seo_services import seo_analysis, generate_meta_description
from services.calculation_services import save_calculation
from db.database import Base
from db.database import get_db    # <- import the dependency from config
from pydantic import BaseModel
import re

router = APIRouter()

class ContentInput(BaseModel):
    content: str

@router.post("/analyze_seo/")
def analyze_seo(data: ContentInput):
    content = data.content
    words = content.split()
    word_count = len(words)
    readability = 100 - (len(words) / 200 * 10)
    keyword_densities = {}
    for w in words:
        keyword_densities[w] = keyword_densities.get(w, 0) + 1
    top_keywords = sorted(keyword_densities, key=keyword_densities.get, reverse=True)[:5]
    densities = {k: round(v / word_count * 100, 2) for k, v in keyword_densities.items()}
    return {"word_count": word_count, "readability": readability, "top_keywords": top_keywords, "keyword_densities": densities}

@router.post("/generate_meta/")
def generate_meta(data: ContentInput):
    snippet = data.content[:150]
    return {"meta_description": f"{snippet}..."}

@router.post("/suggest_improvements/")
def suggest_improvements(data: ContentInput):
    return {"seo_suggestions": "Add more focused keywords and improve sentence clarity."}

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