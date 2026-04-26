from AINDY.runtime.flow_helpers import register_nodes, register_single_node_flows


def freelance_order_create_node(state, context):
    try:
        from apps.freelance.schemas.freelance import FreelanceOrderCreate, FreelanceOrderResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        order = FreelanceOrderCreate(**state.get("order", {}))
        created, was_created = freelance_service.create_order(
            db,
            order,
            user_id=user_id,
            idempotency_key=state.get("idempotency_key"),
            return_created=True,
        )
        return {"status": "SUCCESS", "output_patch": {"freelance_order_create_result": {
            "data": {
                **FreelanceOrderResponse.model_validate(created).model_dump(mode="json"),
                "_idempotency": {"created": was_created},
            },
        }}}
    except ValueError as e:
        return {"status": "FAILURE", "error": f"HTTP_422:{e}"}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to create order: {e}"}


def freelance_order_deliver_node(state, context):
    try:
        import uuid as _uuid
        from apps.freelance.models.freelance import FreelanceOrder
        from apps.freelance.schemas.freelance import FreelanceOrderResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        order_id = state.get("order_id")
        ai_output = state.get("ai_output")
        order = db.query(FreelanceOrder).filter(
            FreelanceOrder.id == order_id,
            FreelanceOrder.user_id == _uuid.UUID(user_id),
        ).first()
        if not order:
            return {"status": "FAILURE", "error": "HTTP_404:Order not found"}
        delivered = freelance_service.deliver_order(db, order_id, ai_output, generated_by_ai=False)
        return {"status": "SUCCESS", "output_patch": {"freelance_order_deliver_result": {
            "data": FreelanceOrderResponse.model_validate(delivered).model_dump(mode="json"),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to deliver order: {e}"}


def freelance_delivery_update_node(state, context):
    try:
        from apps.freelance.schemas.freelance import FreelanceOrderResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        try:
            updated = freelance_service.update_delivery_config(
                db=db, order_id=state.get("order_id"), user_id=user_id,
                delivery_type=state.get("delivery_type"), delivery_config=state.get("delivery_config"),
            )
        except ValueError as e:
            return {"status": "FAILURE", "error": f"HTTP_404:{e}"}
        return {"status": "SUCCESS", "output_patch": {"freelance_delivery_update_result":
            FreelanceOrderResponse.model_validate(updated).model_dump(mode="json")
        }}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to update delivery configuration: {e}"}


def freelance_feedback_collect_node(state, context):
    try:
        from apps.freelance.schemas.freelance import FeedbackCreate, FeedbackResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        feedback = FeedbackCreate(**state.get("feedback", {}))
        try:
            collected = freelance_service.collect_feedback(db, feedback, user_id=user_id)
        except ValueError as e:
            return {"status": "FAILURE", "error": f"HTTP_404:{e}"}
        return {"status": "SUCCESS", "output_patch": {"freelance_feedback_collect_result": {
            "data": FeedbackResponse.model_validate(collected).model_dump(mode="json"),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to collect feedback: {e}"}


def freelance_orders_list_node(state, context):
    try:
        from apps.freelance.schemas.freelance import FreelanceOrderResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        orders = freelance_service.get_all_orders(db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"freelance_orders_list_result": [
            FreelanceOrderResponse.model_validate(o).model_dump(mode="json") for o in orders
        ]}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def freelance_feedback_list_node(state, context):
    try:
        from apps.freelance.schemas.freelance import FeedbackResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        items = freelance_service.get_all_feedback(db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"freelance_feedback_list_result": [
            FeedbackResponse.model_validate(i).model_dump(mode="json") for i in items
        ]}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def freelance_metrics_latest_node(state, context):
    try:
        from apps.freelance.schemas.freelance import RevenueMetricsResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        metric = freelance_service.get_latest_metrics(db)
        if not metric:
            return {"status": "FAILURE", "error": "HTTP_404:No revenue metrics found"}
        return {"status": "SUCCESS", "output_patch": {"freelance_metrics_latest_result":
            RevenueMetricsResponse.model_validate(metric).model_dump(mode="json")
        }}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def freelance_metrics_update_node(state, context):
    try:
        from apps.freelance.schemas.freelance import RevenueMetricsResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        metric = freelance_service.update_revenue_metrics(db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"freelance_metrics_update_result":
            RevenueMetricsResponse.model_validate(metric).model_dump(mode="json")
        }}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Metrics update failed: {e}"}


def freelance_delivery_generate_node(state, context):
    try:
        import uuid as _uuid
        from apps.freelance.models.freelance import FreelanceOrder
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        order_id = state.get("order_id")
        order = db.query(FreelanceOrder).filter(
            FreelanceOrder.id == order_id,
            FreelanceOrder.user_id == _uuid.UUID(user_id),
        ).first()
        if not order:
            return {"status": "FAILURE", "error": "HTTP_404:Order not found"}
        try:
            dispatch = freelance_service.queue_delivery_generation(db, order_id=order_id, user_id=user_id)
        except (LookupError, ValueError) as e:
            return {"status": "FAILURE", "error": f"HTTP_404:{e}"}
        return {"status": "SUCCESS", "output_patch": {"freelance_delivery_generate_result": dispatch}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to queue freelance delivery generation: {e}"}


def freelance_refund_node(state, context):
    try:
        from apps.freelance.schemas.freelance import RefundResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        order_id = state.get("order_id")
        reason = state.get("reason")
        try:
            order, was_created = freelance_service.issue_refund(
                db,
                order_id,
                user_id=user_id,
                reason=reason,
                idempotency_key=state.get("idempotency_key"),
                return_created=True,
            )
        except ValueError as e:
            return {"status": "FAILURE", "error": f"HTTP_422:{e}"}
        amount_cents = int(round(float(order.price or 0.0) * 100)) if order.price is not None else None
        return {
            "status": "SUCCESS",
            "output_patch": {
                "freelance_refund_result": {
                    "data": RefundResponse(
                        order_id=order.id,
                        refund_id=str(order.refund_id or ""),
                        status=str(order.status or "refunded"),
                        payment_status=str(order.payment_status or "refunded"),
                        refunded_at=order.refunded_at,
                        reason=order.refund_reason,
                        amount_cents=amount_cents,
                    ).model_dump(mode="json") | {"_idempotency": {"created": was_created}},
                }
            },
        }
    except RuntimeError as e:
        return {"status": "FAILURE", "error": f"HTTP_500:{e}"}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Refund failed: {e}"}


def freelance_subscription_cancel_node(state, context):
    try:
        from apps.freelance.schemas.freelance import SubscriptionStatusResponse
        from apps.freelance.services import freelance_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        order_id = state.get("order_id")
        reason = state.get("reason")
        try:
            order = freelance_service.cancel_subscription(
                db,
                order_id,
                user_id=user_id,
                reason=reason,
            )
        except ValueError as e:
            return {"status": "FAILURE", "error": f"HTTP_422:{e}"}
        return {
            "status": "SUCCESS",
            "output_patch": {
                "freelance_subscription_cancel_result": {
                    "data": SubscriptionStatusResponse(
                        order_id=order.id,
                        status=str(order.status or "subscription_cancelled"),
                        subscription_status=order.subscription_status,
                        subscription_period_end=order.subscription_period_end,
                        reason=reason,
                    ).model_dump(mode="json"),
                }
            },
        }
    except RuntimeError as e:
        return {"status": "FAILURE", "error": f"HTTP_500:{e}"}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Subscription cancel failed: {e}"}


def register() -> None:
    register_nodes(
        {
            "freelance_order_create_node": freelance_order_create_node,
            "freelance_order_deliver_node": freelance_order_deliver_node,
            "freelance_delivery_update_node": freelance_delivery_update_node,
            "freelance_feedback_collect_node": freelance_feedback_collect_node,
            "freelance_orders_list_node": freelance_orders_list_node,
            "freelance_feedback_list_node": freelance_feedback_list_node,
            "freelance_metrics_latest_node": freelance_metrics_latest_node,
            "freelance_metrics_update_node": freelance_metrics_update_node,
            "freelance_delivery_generate_node": freelance_delivery_generate_node,
            "freelance_refund_node": freelance_refund_node,
            "freelance_subscription_cancel_node": freelance_subscription_cancel_node,
        }
    )
    register_single_node_flows(
        {
            "freelance_order_create": "freelance_order_create_node",
            "freelance_order_deliver": "freelance_order_deliver_node",
            "freelance_delivery_update": "freelance_delivery_update_node",
            "freelance_feedback_collect": "freelance_feedback_collect_node",
            "freelance_orders_list": "freelance_orders_list_node",
            "freelance_feedback_list": "freelance_feedback_list_node",
            "freelance_metrics_latest": "freelance_metrics_latest_node",
            "freelance_metrics_update": "freelance_metrics_update_node",
            "freelance_delivery_generate": "freelance_delivery_generate_node",
            "freelance_refund": "freelance_refund_node",
            "freelance_subscription_cancel": "freelance_subscription_cancel_node",
        }
    )
