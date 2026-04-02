from pydantic import BaseModel


class FavouriteRequest(BaseModel):
    stuid: str
    stoken: str
    mid: str
    game_uid: str
    game_region: str = "cn_gf01"
    offset: str = ""
    size: int = 20


class RolesRequest(BaseModel):
    stuid: str
    stoken: str
    mid: str


class RAGIngestRequest(BaseModel):
    stuid: str
    stoken: str
    mid: str
    game_uid: str = ""
    game_region: str = "cn_gf01"
    size: int = 20
    selected_game_id: int | None = None


class RAGQueryRequest(BaseModel):
    question: str
    game_id: int | None = None
