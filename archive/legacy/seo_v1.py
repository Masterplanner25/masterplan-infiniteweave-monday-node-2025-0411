from pydantic import BaseModel
from typing import Optional

class SEOInput(BaseModel):
    text: str
    top_n: Optional[int] = 10

class MetaInput(BaseModel):
    text: str
    limit: Optional[int] = 160
