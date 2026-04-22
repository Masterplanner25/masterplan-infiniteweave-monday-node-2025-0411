from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.schemas import WebhookSubscription
from AINDY.services.auth_service import get_current_user

router = APIRouter()


@router.post("/webhooks", status_code=201, response_model=None)
@limiter.limit("30/minute")
def create_webhook(request: Request, body: WebhookSubscription, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
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


@router.get("/webhooks", response_model=None)
@limiter.limit("60/minute")
def list_webhook_subscriptions(request: Request, current_user: dict = Depends(get_current_user)):
    from AINDY.platform_layer.event_service import list_webhooks

    return {"webhooks": list_webhooks(user_id=str(current_user["sub"]))}


@router.get("/webhooks/{subscription_id}", response_model=None)
@limiter.limit("60/minute")
def get_webhook_subscription(request: Request, subscription_id: str, current_user: dict = Depends(get_current_user)):
    from AINDY.platform_layer.event_service import get_webhook

    meta = get_webhook(subscription_id)
    if not meta or meta.get("created_by") != str(current_user["sub"]):
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
    return meta


@router.delete("/webhooks/{subscription_id}", status_code=204, response_model=None)
@limiter.limit("30/minute")
def delete_webhook_subscription(request: Request, subscription_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from AINDY.platform_layer.event_service import get_webhook, unsubscribe_webhook

    meta = get_webhook(subscription_id)
    if not meta or meta.get("created_by") != str(current_user["sub"]):
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
    unsubscribe_webhook(subscription_id, db=db)
    return None
