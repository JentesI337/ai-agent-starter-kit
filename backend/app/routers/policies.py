from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.policy_store import PolicyCreateRequest, PolicyStore

JsonDict = dict


def build_policies_router(*, policy_store: PolicyStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/policies")
    def list_policies():
        items = policy_store.list()
        return {
            "schema": "policy-list-v1",
            "items": [item.model_dump() for item in items],
            "count": len(items),
        }

    @router.get("/api/policies/{policy_id}")
    def get_policy(policy_id: str):
        item = policy_store.get(policy_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        return item.model_dump()

    @router.post("/api/policies")
    def create_policy(payload: JsonDict = Body(...)):
        request = PolicyCreateRequest.model_validate(payload)
        created = policy_store.create(request)
        return created.model_dump()

    @router.patch("/api/policies/{policy_id}")
    def update_policy(policy_id: str, patch: JsonDict = Body(...)):
        updated = policy_store.update(policy_id, patch)
        if updated is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        return updated.model_dump()

    @router.delete("/api/policies/{policy_id}")
    def delete_policy(policy_id: str):
        deleted = policy_store.delete(policy_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Policy not found")
        return {"ok": True}

    return router
