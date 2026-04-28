from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.schemas import WebhookSubscription
from AINDY.services.auth_service import get_current_user

router = APIRouter()


def _execute_webhooks(
    request: Request,
    route_name: str,
    handler,
    *,
    db: Session | None = None,
    user_id: str,
    input_payload=None,
    success_status_code: int = 200,
):
    metadata = {"source": "platform.webhooks"}
    if db is not None:
        metadata["db"] = db
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata=metadata,
        success_status_code=success_status_code,
        return_result=True,
    )
    if not result.success:
        detail = result.metadata.get("detail") or result.error or "Execution failed"
        raise HTTPException(
            status_code=int(result.metadata.get("status_code", 500)),
            detail=detail,
        )
    data = result.data
    if isinstance(data, dict):
        data = dict(data)
        data.pop("execution_envelope", None)
    return data


@router.post("/webhooks", status_code=201, response_model=None)
@limiter.limit("30/minute")
def create_webhook(request: Request, body: WebhookSubscription, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.event_service import subscribe_webhook

        try:
            return subscribe_webhook(
                event_type=body.event_type,
                callback_url=body.callback_url,
                secret=body.secret,
                user_id=str(current_user["sub"]),
                db=db,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"error": str(exc)})

    return _execute_webhooks(request, "platform.webhooks.create", handler, db=db, user_id=str(current_user["sub"]), input_payload=body.model_dump(), success_status_code=201)


@router.get("/webhooks", response_model=None)
@limiter.limit("60/minute")
def list_webhook_subscriptions(request: Request, current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.event_service import list_webhooks

        return {"webhooks": list_webhooks(user_id=str(current_user["sub"]))}

    return _execute_webhooks(request, "platform.webhooks.list", handler, user_id=str(current_user["sub"]))


@router.get("/webhooks/{subscription_id}", response_model=None)
@limiter.limit("60/minute")
def get_webhook_subscription(request: Request, subscription_id: str, current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.event_service import get_webhook

        meta = get_webhook(subscription_id)
        if not meta or meta.get("created_by") != str(current_user["sub"]):
            raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
        return meta

    return _execute_webhooks(request, "platform.webhooks.get", handler, user_id=str(current_user["sub"]), input_payload={"subscription_id": subscription_id})


@router.delete("/webhooks/{subscription_id}", status_code=204, response_model=None)
@limiter.limit("30/minute")
def delete_webhook_subscription(request: Request, subscription_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.platform_layer.event_service import get_webhook, unsubscribe_webhook

        meta = get_webhook(subscription_id)
        if not meta or meta.get("created_by") != str(current_user["sub"]):
            raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
        unsubscribe_webhook(subscription_id, db=db)
        return None

    return _execute_webhooks(request, "platform.webhooks.delete", handler, db=db, user_id=str(current_user["sub"]), input_payload={"subscription_id": subscription_id}, success_status_code=204)
