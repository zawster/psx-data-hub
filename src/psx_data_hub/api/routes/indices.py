from __future__ import annotations

from fastapi import APIRouter, Depends

from psx_data_hub.api.dependencies import get_repo, require_api_key
from psx_data_hub.storage.repo import DataRepository

router = APIRouter()


@router.get("", dependencies=[Depends(require_api_key)])
async def get_indices(repo: DataRepository = Depends(get_repo)):
    snapshot = await repo.get_latest_market_snapshot()
    if not snapshot:
        return {"indices": []}

    payload = snapshot.payload or {}
    if isinstance(payload, dict) and isinstance(payload.get("indices"), list):
        return {"indices": payload["indices"]}
    return {"indices": [], "payload": payload}
