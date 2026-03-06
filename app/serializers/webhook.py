from pydantic import BaseModel, ConfigDict
from typing import Optional


class ManychatContactPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None
    ig_username: Optional[str] = None
    ig_id: Optional[int] = None
    last_input_text: Optional[str] = None
    ig_last_interaction: Optional[str] = None
