from __future__ import annotations

from datetime import datetime, timezone
import json
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from AINDY.db.mongo_setup import get_mongo_client
from AINDY.platform_layer.external_call_service import perform_external_call


SUPPORTED_AUTOMATION_TYPES = {
    "social",
    "crm",
    "email",
    "webhook",
    "stripe",
    "content_generation",
}


def execute_automation_action(payload: dict[str, Any], db) -> dict[str, Any]:
    automation_type = str(payload.get("automation_type") or "").strip()
    config = dict(payload.get("automation_config") or {})

    if automation_type not in SUPPORTED_AUTOMATION_TYPES:
        raise ValueError(f"unsupported_automation_type:{automation_type or 'unknown'}")

    if automation_type == "social":
        return _execute_social_action(payload, config)
    if automation_type == "crm":
        return _execute_crm_action(payload, config)
    if automation_type == "email":
        return _execute_email_action(payload, config, db=db)
    if automation_type == "webhook":
        return _execute_webhook_action(payload, config, db=db)
    if automation_type == "stripe":
        return _execute_stripe_action(payload, config, db=db)
    return _execute_content_generation(payload, config)


def _execute_social_action(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    content = str(config.get("content") or payload.get("task_name") or "").strip()
    if not content:
        raise ValueError("social_content_required")

    mongo = get_mongo_client()
    social_db = mongo["aindy_social_layer"]
    posts = social_db["posts"]
    post_id = str(config.get("post_id") or "")
    now = datetime.now(timezone.utc)
    document = {
        "user_id": str(payload.get("user_id") or ""),
        "content": content,
        "visibility": config.get("visibility", "private"),
        "tags": config.get("tags") or ["masterplan", "automation"],
        "created_at": now,
        "updated_at": now,
        "origin": "masterplan_automation",
        "task_id": payload.get("task_id"),
        "masterplan_id": payload.get("masterplan_id"),
    }
    inserted = posts.insert_one(document)
    return {
        "automation_type": "social",
        "status": "completed",
        "post_id": str(inserted.inserted_id),
        "content": content,
        "requested_post_id": post_id or None,
    }


def _execute_crm_action(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "automation_type": "crm",
        "status": "completed",
        "action": config.get("action", "record_follow_up"),
        "contact": config.get("contact"),
        "details": config.get("details") or config.get("notes"),
        "task_id": payload.get("task_id"),
    }


def _execute_email_action(payload: dict[str, Any], config: dict[str, Any], *, db) -> dict[str, Any]:
    subject = str(config.get("subject") or payload.get("task_name") or "A.I.N.D.Y. automated message")
    body = str(config.get("body") or config.get("content") or "")
    recipient = config.get("recipient")
    if not recipient:
        raise ValueError("email_recipient_required")
    sender = str(config.get("sender") or config.get("from") or "no-reply@aindy.local")
    smtp_host = config.get("smtp_host")
    smtp_port = int(config.get("smtp_port") or 587)
    smtp_username = config.get("smtp_username")
    smtp_password = config.get("smtp_password")
    smtp_starttls = bool(config.get("smtp_starttls", True))
    provider_url = config.get("provider_url")

    if smtp_host:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content(body)

        def _send_smtp():
            with smtplib.SMTP(str(smtp_host), smtp_port, timeout=15) as smtp:
                if smtp_starttls:
                    smtp.starttls()
                if smtp_username:
                    smtp.login(str(smtp_username), str(smtp_password or ""))
                smtp.send_message(message)
            return {"transport": "smtp", "host": smtp_host, "port": smtp_port}

        response = perform_external_call(
            service_name="smtp",
            db=db,
            user_id=payload.get("user_id"),
            endpoint=f"{smtp_host}:{smtp_port}",
            method="smtp.send",
            extra={"purpose": "email_delivery", "recipient": recipient},
            operation=_send_smtp,
        )
    elif provider_url:
        headers = {"Content-Type": "application/json"}
        if config.get("auth_header"):
            headers["Authorization"] = str(config.get("auth_header"))

        def _send_provider():
            req = urllib_request.Request(
                str(provider_url),
                data=json.dumps(
                    {
                        "to": recipient,
                        "from": sender,
                        "subject": subject,
                        "body": body,
                    }
                ).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=15) as resp:
                return {
                    "transport": "api",
                    "status_code": getattr(resp, "status", 200),
                    "body": resp.read().decode("utf-8", errors="ignore")[:2000],
                }

        response = perform_external_call(
            service_name="email_api",
            db=db,
            user_id=payload.get("user_id"),
            endpoint=str(provider_url),
            method="http.post",
            extra={"purpose": "email_delivery", "recipient": recipient},
            operation=_send_provider,
        )
    else:
        raise ValueError("email_delivery_transport_required")

    return {
        "automation_type": "email",
        "status": "completed",
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "response": response,
    }


def _execute_webhook_action(payload: dict[str, Any], config: dict[str, Any], *, db) -> dict[str, Any]:
    webhook_url = config.get("url") or config.get("webhook_url")
    if not webhook_url:
        raise ValueError("webhook_url_required")
    method = str(config.get("method") or "POST").upper()
    headers = dict(config.get("headers") or {})
    headers.setdefault("Content-Type", "application/json")
    body = config.get("body")
    if body is None:
        body = {
            "task_name": payload.get("task_name"),
            "user_id": payload.get("user_id"),
            "content": config.get("content"),
            "metadata": config.get("metadata") or {},
        }

    def _send_webhook():
        req = urllib_request.Request(
            str(webhook_url),
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method=method,
        )
        with urllib_request.urlopen(req, timeout=15) as resp:
            return {
                "status_code": getattr(resp, "status", 200),
                "body": resp.read().decode("utf-8", errors="ignore")[:2000],
            }

    response = perform_external_call(
        service_name="webhook",
        db=db,
        user_id=payload.get("user_id"),
        endpoint=str(webhook_url),
        method=f"http.{method.lower()}",
        extra={"purpose": "webhook_delivery"},
        operation=_send_webhook,
    )
    return {
        "automation_type": "webhook",
        "status": "completed",
        "response": response,
    }


def _execute_stripe_action(payload: dict[str, Any], config: dict[str, Any], *, db=None) -> dict[str, Any]:
    from AINDY.config import settings

    stripe_key = config.get("stripe_secret_key") or settings.STRIPE_SECRET_KEY
    if not stripe_key:
        raise ValueError(
            "stripe_secret_key not configured. Set STRIPE_SECRET_KEY in environment "
            "or provide stripe_secret_key in delivery_config."
        )

    amount_raw = config.get("amount") or (payload.get("automation_config") or {}).get("amount")
    if amount_raw is None:
        metadata = config.get("metadata") or {}
        price_float = float(metadata.get("price") or config.get("price") or 0.0)
        amount_cents = int(round(price_float * 100))
    else:
        amount_cents = int(amount_raw)

    if amount_cents <= 0:
        raise ValueError("stripe_payment_amount_required: amount must be > 0 cents")

    currency = str(config.get("currency") or "usd").lower()
    product_name = str(
        config.get("product_name")
        or payload.get("task_name")
        or "Freelance Service"
    )
    customer_email = config.get("customer_email") or config.get("recipient")

    def _stripe_post(path: str, form_data: dict[str, Any]) -> dict[str, Any]:
        encoded = urllib_parse.urlencode(form_data).encode("utf-8")
        req = urllib_request.Request(
            f"https://api.stripe.com{path}",
            data=encoded,
            headers={
                "Authorization": f"Bearer {stripe_key}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _create_payment_link() -> dict[str, Any]:
        product = _stripe_post(
            "/v1/products",
            {
                "name": product_name,
                "description": str(config.get("description") or product_name)[:500],
            },
        )
        product_id = product["id"]

        price = _stripe_post(
            "/v1/prices",
            {
                "product": product_id,
                "unit_amount": str(amount_cents),
                "currency": currency,
            },
        )
        price_id = price["id"]

        link_data = {
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
        }
        if customer_email:
            link_data["customer_creation"] = "always"
            link_data["customer_email"] = str(customer_email)

        link = _stripe_post("/v1/payment_links", link_data)
        return {
            "product_id": product_id,
            "price_id": price_id,
            "payment_link_id": link["id"],
            "payment_link_url": link["url"],
        }

    response = perform_external_call(
        service_name="stripe",
        db=db,
        user_id=payload.get("user_id"),
        endpoint="/v1/payment_links",
        method="stripe.payment_links.create",
        extra={
            "purpose": "freelance_payment_link",
            "customer_email": customer_email,
            "amount_cents": amount_cents,
            "currency": currency,
        },
        operation=_create_payment_link,
    )

    return {
        "automation_type": "stripe",
        "status": "completed",
        "payment_link_id": response["payment_link_id"],
        "payment_link_url": response["payment_link_url"],
        "product_id": response["product_id"],
        "price_id": response["price_id"],
        "amount_cents": amount_cents,
        "currency": currency,
        "customer_email": customer_email,
    }


def _execute_content_generation(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    prompt = str(config.get("prompt") or payload.get("task_name") or "").strip()
    if not prompt:
        raise ValueError("content_prompt_required")
    tone = str(config.get("tone") or "operational")
    generated = config.get("template") or f"[{tone}] {prompt}"
    return {
        "automation_type": "content_generation",
        "status": "completed",
        "prompt": prompt,
        "generated_content": generated,
        "format": config.get("format", "text"),
    }


# ── automation log access ─────────────────────────────────────────────────────

def get_automation_log(db, log_id: str, user_id: str) -> Any | None:
    """
    Fetch an AutomationLog row by id.

    Returns the row if it exists (ownership is not enforced at the DB level —
    the replay endpoint validates the execution_token instead).
    Returns None when no row matches log_id.
    """
    from apps.automation.models import AutomationLog

    return db.query(AutomationLog).filter(AutomationLog.id == log_id).first()


