from pydantic import BaseModel
from typing import Optional


class ManychatPayload(BaseModel):
    instagram_user_id: str
    message: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
