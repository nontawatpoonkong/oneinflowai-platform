"""Workspace-scoped PostgreSQL operational analytics."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.action import ActionDefinition, ActionRequest, ActionRequestStatus
from app.models.ai_tool import AIToolAction, AIToolActionStatus
from app.models.audit import ProductFeature, ProductUsageEvent
from app.models.automation import AutomationDefinition, AutomationExecution
from app.models.booking import Booking, BookingStatus
from app.models.conversation import Conversation
from app.models.hotel import Property
from app.models.housekeeping import HousekeepingEvent, HousekeepingEventType
from app.models.message import Message, SenderType
from app.models.payment import (
    Payment,
    PaymentApplicationStatus,
    PaymentStatus,
    PaymentVerification,
)
from app.models.promotion import (
    BookingAttribution,
    PromotionCampaign,
    PromotionCampaignStatus,
    PromotionCode,
    PromotionCodeStatus,
    PromotionRedemption,
    PromotionRedemptionStatus,
)
from app.models.stay import HotelRoom, StayEvent, StayEventType
from app.models.user import User


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def overview(self, workspace_id: uuid.UUID, start: datetime, end: datetime):
        conversation_filter = (
            Conversation.workspace_id == workspace_id,
            Conversation.created_at >= start,
            Conversation.created_at < end,
        )
        conversations = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(*conversation_filter)
            )
            or 0
        )
        customers = int(
            await self.session.scalar(
                select(func.count(distinct(Conversation.customer_id))).where(
                    *conversation_filter
                )
            )
            or 0
        )

        message_rows = await self.session.execute(
            select(Message.sender_type, func.count())
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.workspace_id == workspace_id,
                Message.created_at >= start,
                Message.created_at < end,
            )
            .group_by(Message.sender_type)
        )
        messages = {row[0].value: int(row[1]) for row in message_rows}
        ai_conversations = int(
            await self.session.scalar(
                select(func.count(distinct(Conversation.id)))
                .join(Message, Message.conversation_id == Conversation.id)
                .where(
                    *conversation_filter,
                    Message.sender_type == SenderType.AI,
                    Conversation.handoff_requested_at.is_(None),
                )
            )
            or 0
        )
        handoffs = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.handoff_requested_at >= start,
                    Conversation.handoff_requested_at < end,
                )
            )
            or 0
        )

        actions = int(
            await self.session.scalar(
                select(func.count())
                .select_from(ActionRequest)
                .where(
                    ActionRequest.workspace_id == workspace_id,
                    ActionRequest.created_at >= start,
                    ActionRequest.created_at < end,
                )
            )
            or 0
        )
        completed_actions = int(
            await self.session.scalar(
                select(func.count())
                .select_from(ActionRequest)
                .where(
                    ActionRequest.workspace_id == workspace_id,
                    ActionRequest.created_at >= start,
                    ActionRequest.created_at < end,
                    ActionRequest.status == ActionRequestStatus.COMPLETED,
                )
            )
            or 0
        )
        payments = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.workspace_id == workspace_id,
                    Payment.created_at >= start,
                    Payment.created_at < end,
                )
            )
            or 0
        )
        verified_payments = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.workspace_id == workspace_id,
                    Payment.created_at >= start,
                    Payment.created_at < end,
                    Payment.status == PaymentStatus.VERIFIED,
                )
            )
            or 0
        )

        return {
            "range": {"start": start, "end": end, "timezone": "UTC"},
            "kpis": {
                "unique_customers": customers,
                "conversations": conversations,
                "customer_messages": messages.get(SenderType.CUSTOMER.value, 0),
                "ai_messages": messages.get(SenderType.AI.value, 0),
                "staff_messages": messages.get(SenderType.AGENT.value, 0),
                "ai_handled_conversations": ai_conversations,
                "ai_handled_rate": self._rate(ai_conversations, conversations),
                "handoffs": handoffs,
                "handoff_rate": self._rate(handoffs, conversations),
                "actions_created": actions,
                "actions_completed": completed_actions,
                "action_completion_rate": self._rate(completed_actions, actions),
                "payments_created": payments,
                "verified_payments": verified_payments,
                "payment_verification_rate": self._rate(verified_payments, payments),
            },
            "conversation_trend": await self._trend(workspace_id, start, end),
            "conversations_by_channel": await self._group(
                Conversation.channel,
                (
                    *conversation_filter,
                    Conversation.channel.in_(["web", "line", "facebook"]),
                ),
            ),
            "message_counts": [
                {"key": key, "count": count} for key, count in sorted(messages.items())
            ],
            "handoff_reasons": await self._group(
                Conversation.handoff_reason,
                (
                    Conversation.workspace_id == workspace_id,
                    Conversation.handoff_requested_at >= start,
                    Conversation.handoff_requested_at < end,
                ),
            ),
            "actions_by_type": await self._actions_by_type(workspace_id, start, end),
            "action_statuses": await self._group(
                ActionRequest.status,
                (
                    ActionRequest.workspace_id == workspace_id,
                    ActionRequest.created_at >= start,
                    ActionRequest.created_at < end,
                ),
            ),
            "payment_statuses": await self._group(
                Payment.status,
                (
                    Payment.workspace_id == workspace_id,
                    Payment.created_at >= start,
                    Payment.created_at < end,
                ),
            ),
            "verified_amounts": await self._verified_amounts(workspace_id, start, end),
            "verification_statuses": await self._verification_statuses(
                workspace_id, start, end
            ),
            "current_queue": await self._queue(workspace_id),
            "sales": await self._sales(workspace_id, start, end),
            "operations": await self._operations(workspace_id, start, end),
            "ai_conversations": await self._ai(workspace_id, start, end),
            "automation": await self._automation(workspace_id, start, end),
            "usage": await self._usage(workspace_id, start, end),
        }

    async def _sales(self, workspace_id, start, end):
        filters = (
            Booking.workspace_id == workspace_id,
            Booking.created_at >= start,
            Booking.created_at < end,
        )
        status_rows = await self.session.execute(
            select(Booking.status, func.count())
            .where(*filters)
            .group_by(Booking.status)
        )
        counts = {row[0].value: int(row[1]) for row in status_rows}
        money_rows = (
            await self.session.execute(
                select(
                    Booking.currency,
                    func.sum(Booking.total_amount),
                    func.avg(Booking.total_amount),
                )
                .where(*filters, Booking.status == BookingStatus.CONFIRMED)
                .group_by(Booking.currency)
                .order_by(Booking.currency)
            )
        ).all()
        review_count = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.workspace_id == workspace_id,
                    Payment.created_at >= start,
                    Payment.created_at < end,
                    Payment.booking_application_status
                    == PaymentApplicationStatus.REQUIRES_REVIEW,
                )
            )
            or 0
        )
        return {
            "booking_counts": counts,
            "confirmed_value_by_currency": [
                {"currency": row[0], "amount": row[1]} for row in money_rows
            ],
            "average_confirmed_value_by_currency": [
                {
                    "currency": row[0],
                    "amount": row[2].quantize(Decimal("0.01")),
                }
                for row in money_rows
            ],
            "payment_requires_review": review_count,
            "funnel": {
                "attribution_supported": False,
                "unsupported_stages": ["CONVERSATION", "AVAILABILITY_SEARCHED"],
                "hold": counts.get(BookingStatus.HELD.value, 0),
                "payment_initiated": counts.get(BookingStatus.PENDING_PAYMENT.value, 0),
                "confirmed": counts.get(BookingStatus.CONFIRMED.value, 0),
            },
            "promotions": await self._promotion_sales(workspace_id, start, end),
        }

    async def _promotion_sales(self, workspace_id, start, end):
        filters = (
            PromotionRedemption.workspace_id == workspace_id,
            PromotionRedemption.status == PromotionRedemptionStatus.CONFIRMED,
            PromotionRedemption.redeemed_at >= start,
            PromotionRedemption.redeemed_at < end,
            Booking.status == BookingStatus.CONFIRMED,
        )
        money_rows = (
            await self.session.execute(
                select(
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.sum(Booking.subtotal),
                    func.sum(Booking.discount_amount),
                    func.sum(Booking.total_amount),
                )
                .join(Booking, Booking.id == PromotionRedemption.booking_id)
                .where(*filters)
                .group_by(Booking.currency)
                .order_by(Booking.currency)
            )
        ).all()

        async def grouped(key_column, label_column, join_model):
            rows = (
                await self.session.execute(
                    select(
                        key_column,
                        label_column,
                        Booking.currency,
                        func.count(PromotionRedemption.id),
                        func.sum(Booking.discount_amount),
                        func.sum(Booking.total_amount),
                    )
                    .join(Booking, Booking.id == PromotionRedemption.booking_id)
                    .join(
                        BookingAttribution,
                        BookingAttribution.booking_id == Booking.id,
                    )
                    .join(join_model, key_column == join_model.id)
                    .where(*filters)
                    .group_by(key_column, label_column, Booking.currency)
                    .order_by(func.count(PromotionRedemption.id).desc(), key_column)
                )
            ).all()
            return [
                {
                    "key": str(row[0]),
                    "label": row[1],
                    "currency": row[2],
                    "uses": int(row[3]),
                    "discount_amount": row[4],
                    "net_amount": row[5],
                }
                for row in rows
            ]

        source_rows = (
            await self.session.execute(
                select(
                    BookingAttribution.source,
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.sum(Booking.discount_amount),
                    func.sum(Booking.total_amount),
                )
                .join(Booking, Booking.id == PromotionRedemption.booking_id)
                .join(
                    BookingAttribution,
                    BookingAttribution.booking_id == Booking.id,
                )
                .where(*filters)
                .group_by(BookingAttribution.source, Booking.currency)
                .order_by(func.count(PromotionRedemption.id).desc())
            )
        ).all()
        return {
            **await self._promotion_lifecycle(workspace_id, start, end, filters),
            "redemptions": sum(int(row[1]) for row in money_rows),
            "by_currency": [
                {
                    "currency": row[0],
                    "uses": int(row[1]),
                    "gross_amount": row[2],
                    "discount_amount": row[3],
                    "net_amount": row[4],
                }
                for row in money_rows
            ],
            "campaigns": await grouped(
                BookingAttribution.campaign_id,
                PromotionCampaign.name,
                PromotionCampaign,
            ),
            "codes": await grouped(
                BookingAttribution.promotion_code_id,
                PromotionCode.code,
                PromotionCode,
            ),
            "sources": [
                {
                    "key": row[0].value,
                    "currency": row[1],
                    "uses": int(row[2]),
                    "discount_amount": row[3],
                    "net_amount": row[4],
                }
                for row in source_rows
            ],
            "definition": (
                "Confirmed promotion redemptions grouped by redemption time; "
                "gross=subtotal, discount=discount_amount, net=total_amount"
            ),
        }

    async def _promotion_lifecycle(self, workspace_id, start, end, confirmed):
        """Status counts, reservation funnel, daily trend, and property split."""

        now = datetime.now(UTC)
        campaign_status = dict(
            (
                await self.session.execute(
                    select(PromotionCampaign.status, func.count())
                    .where(PromotionCampaign.workspace_id == workspace_id)
                    .group_by(PromotionCampaign.status)
                )
            ).all()
        )
        code_status = dict(
            (
                await self.session.execute(
                    select(PromotionCode.status, func.count())
                    .where(PromotionCode.workspace_id == workspace_id)
                    .group_by(PromotionCode.status)
                )
            ).all()
        )
        lapsed = (PromotionRedemption.status == PromotionRedemptionStatus.RESERVED) & (
            PromotionRedemption.reserved_until < now
        )
        funnel = (
            await self.session.execute(
                select(
                    func.count(PromotionRedemption.id),
                    func.count(PromotionRedemption.id).filter(
                        PromotionRedemption.status
                        == PromotionRedemptionStatus.CONFIRMED
                    ),
                    func.count(PromotionRedemption.id).filter(
                        (
                            PromotionRedemption.status
                            == PromotionRedemptionStatus.RELEASED
                        )
                        | lapsed
                    ),
                ).where(
                    PromotionRedemption.workspace_id == workspace_id,
                    PromotionRedemption.created_at >= start,
                    PromotionRedemption.created_at < end,
                )
            )
        ).one()
        day = cast(func.timezone("UTC", PromotionRedemption.redeemed_at), Date)
        trend = (
            await self.session.execute(
                select(
                    day,
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.sum(Booking.discount_amount),
                )
                .join(Booking, Booking.id == PromotionRedemption.booking_id)
                .where(*confirmed)
                .group_by(day, Booking.currency)
                .order_by(day, Booking.currency)
            )
        ).all()
        properties = (
            await self.session.execute(
                select(
                    Property.id,
                    Property.name,
                    Booking.currency,
                    func.count(PromotionRedemption.id),
                    func.sum(Booking.discount_amount),
                    func.sum(Booking.total_amount),
                )
                .join(Booking, Booking.id == PromotionRedemption.booking_id)
                .join(
                    Property,
                    (Property.workspace_id == Booking.workspace_id)
                    & (Property.id == Booking.property_id),
                )
                .where(*confirmed)
                .group_by(Property.id, Property.name, Booking.currency)
                .order_by(func.count(PromotionRedemption.id).desc(), Property.name)
                .limit(50)
            )
        ).all()
        return {
            "campaigns_by_status": {
                item.value: int(campaign_status.get(item, 0))
                for item in PromotionCampaignStatus
            },
            "codes_by_status": {
                item.value: int(code_status.get(item, 0))
                for item in PromotionCodeStatus
            },
            "reservation_funnel": {
                "reserved": int(funnel[0]),
                "confirmed": int(funnel[1]),
                "released": int(funnel[2]),
                "definition": (
                    "Redemptions reserved at Booking Hold time in range, by "
                    "current outcome; lapsed reservations count as released."
                ),
            },
            "daily_trend": [
                {
                    "date": value.isoformat(),
                    "currency": currency,
                    "uses": int(count),
                    "discount_amount": amount,
                }
                for value, currency, count, amount in trend
            ],
            "properties": [
                {
                    "key": str(property_id),
                    "label": name,
                    "currency": currency,
                    "uses": int(count),
                    "discount_amount": discount,
                    "net_amount": net,
                }
                for property_id, name, currency, count, discount, net in properties
            ],
        }

    async def _operations(self, workspace_id, start, end):
        stay_rows = await self.session.execute(
            select(StayEvent.event_type, func.count())
            .where(
                StayEvent.workspace_id == workspace_id,
                StayEvent.event_type.in_(
                    (
                        StayEventType.CHECKED_IN,
                        StayEventType.CHECKED_OUT,
                        StayEventType.NO_SHOW,
                    )
                ),
                StayEvent.created_at >= start,
                StayEvent.created_at < end,
            )
            .group_by(StayEvent.event_type)
        )
        stay_counts = {row[0].value: int(row[1]) for row in stay_rows}
        readiness_rows = await self.session.execute(
            select(HotelRoom.readiness_status, func.count())
            .where(HotelRoom.workspace_id == workspace_id, HotelRoom.active.is_(True))
            .group_by(HotelRoom.readiness_status)
        )
        readiness = {row[0].value: int(row[1]) for row in readiness_rows}

        dirty = aliased(HousekeepingEvent)
        ready = aliased(HousekeepingEvent)
        turnaround = await self.session.scalar(
            select(
                func.avg(
                    func.extract("epoch", ready.created_at - dirty.created_at) / 60
                )
            )
            .select_from(dirty)
            .join(
                ready,
                (ready.task_id == dirty.task_id)
                & (ready.event_type == HousekeepingEventType.ROOM_READY)
                & (ready.created_at >= dirty.created_at),
            )
            .where(
                dirty.workspace_id == workspace_id,
                dirty.event_type == HousekeepingEventType.ROOM_DIRTY,
                ready.created_at >= start,
                ready.created_at < end,
            )
        )
        completed = int(
            await self.session.scalar(
                select(func.count())
                .select_from(HousekeepingEvent)
                .where(
                    HousekeepingEvent.workspace_id == workspace_id,
                    HousekeepingEvent.event_type
                    == HousekeepingEventType.HOUSEKEEPING_COMPLETED,
                    HousekeepingEvent.created_at >= start,
                    HousekeepingEvent.created_at < end,
                )
            )
            or 0
        )
        return {
            "stays": stay_counts,
            "room_readiness": readiness,
            "housekeeping_completed": completed,
            "housekeeping_turnaround_minutes": (
                round(float(turnaround), 1) if turnaround is not None else None
            ),
            "turnaround_definition": (
                "ROOM_DIRTY to ROOM_READY for completed task event pairs"
            ),
        }

    async def _ai(self, workspace_id, start, end):
        statuses = await self.session.execute(
            select(AIToolAction.status, func.count())
            .where(
                AIToolAction.workspace_id == workspace_id,
                AIToolAction.created_at >= start,
                AIToolAction.created_at < end,
            )
            .group_by(AIToolAction.status)
        )
        action_counts = {row[0].value: int(row[1]) for row in statuses}
        handoffs = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.handoff_requested_at >= start,
                    Conversation.handoff_requested_at < end,
                )
            )
            or 0
        )
        return {
            "tool_actions": sum(action_counts.values()),
            "tool_action_statuses": action_counts,
            "tool_actions_succeeded": action_counts.get(
                AIToolActionStatus.SUCCEEDED.value, 0
            ),
            "tool_actions_failed": action_counts.get(
                AIToolActionStatus.FAILED.value, 0
            ),
            "human_handoffs": handoffs,
            "privacy": "No prompts, message bodies, reasoning, or provider metadata",
        }

    async def _automation(self, workspace_id, start, end):
        rows = await self.session.execute(
            select(AutomationExecution.status, func.count())
            .where(
                AutomationExecution.workspace_id == workspace_id,
                AutomationExecution.created_at >= start,
                AutomationExecution.created_at < end,
            )
            .group_by(AutomationExecution.status)
        )
        statuses = {str(row[0]): int(row[1]) for row in rows}
        aggregates = (
            await self.session.execute(
                select(
                    func.count(),
                    func.avg(AutomationExecution.attempt_count),
                    func.sum(AutomationExecution.manual_retry_count),
                    func.count().filter(AutomationExecution.terminal_failure.is_(True)),
                ).where(
                    AutomationExecution.workspace_id == workspace_id,
                    AutomationExecution.created_at >= start,
                    AutomationExecution.created_at < end,
                )
            )
        ).one()
        most_used_rows = await self.session.execute(
            select(
                AutomationDefinition.id,
                AutomationDefinition.name,
                func.count(AutomationExecution.id),
            )
            .join(
                AutomationExecution,
                AutomationExecution.automation_id == AutomationDefinition.id,
            )
            .where(
                AutomationExecution.workspace_id == workspace_id,
                AutomationExecution.created_at >= start,
                AutomationExecution.created_at < end,
            )
            .group_by(AutomationDefinition.id, AutomationDefinition.name)
            .order_by(func.count(AutomationExecution.id).desc())
            .limit(5)
        )
        total = int(aggregates[0] or 0)
        retry_count = int(aggregates[2] or 0)
        succeeded = statuses.get("SUCCEEDED", 0)
        return {
            "execution_count": total,
            "statuses": statuses,
            "success_rate": self._rate(succeeded, total),
            "retry_rate": self._rate(retry_count, total),
            "average_attempts": round(float(aggregates[1] or 0), 2),
            "terminal_failed": int(aggregates[3] or 0),
            "most_used": [
                {"key": str(row[0]), "label": row[1], "count": int(row[2])}
                for row in most_used_rows
            ],
        }

    async def _usage(self, workspace_id, start, end):
        base = (
            ProductUsageEvent.workspace_id == workspace_id,
            ProductUsageEvent.occurred_at >= start,
            ProductUsageEvent.occurred_at < end,
        )
        summary = (
            await self.session.execute(
                select(
                    func.count(),
                    func.count(distinct(ProductUsageEvent.user_id)),
                    func.count().filter(
                        ProductUsageEvent.feature == ProductFeature.HOME.value
                    ),
                    func.count(distinct(ProductUsageEvent.user_id)).filter(
                        ProductUsageEvent.feature == ProductFeature.HOME.value
                    ),
                ).where(*base)
            )
        ).one()
        feature_rows = await self.session.execute(
            select(ProductUsageEvent.feature, func.count())
            .where(*base)
            .group_by(ProductUsageEvent.feature)
            .order_by(func.count().desc())
        )
        home_day = func.date_trunc("day", ProductUsageEvent.occurred_at)
        daily_rows = await self.session.execute(
            select(home_day, func.count())
            .where(*base, ProductUsageEvent.feature == ProductFeature.HOME.value)
            .group_by(home_day)
            .order_by(home_day)
        )
        viewers = await self.session.execute(
            select(
                ProductUsageEvent.user_id,
                User.full_name,
                User.email,
                func.max(ProductUsageEvent.occurred_at),
                func.count(),
            )
            .join(User, User.id == ProductUsageEvent.user_id)
            .where(*base, ProductUsageEvent.feature == ProductFeature.HOME.value)
            .group_by(ProductUsageEvent.user_id, User.full_name, User.email)
            .order_by(func.max(ProductUsageEvent.occurred_at).desc())
            .limit(50)
        )
        return {
            "page_views": int(summary[0]),
            "unique_active_users": int(summary[1]),
            "home_views": int(summary[2]),
            "home_unique_users": int(summary[3]),
            "feature_usage": [
                {"key": row[0], "count": int(row[1])} for row in feature_rows
            ],
            "home_views_by_day": [
                {"date": row[0].date(), "count": int(row[1])} for row in daily_rows
            ],
            "recent_home_viewers": [
                {
                    "user_id": row[0],
                    "name": row[1] or row[2],
                    "last_viewed_at": row[3],
                    "views": int(row[4]),
                }
                for row in viewers
            ],
            "privacy": (
                "Navigation counts only; no productivity scoring or interaction capture"
            ),
        }

    async def _trend(self, workspace_id, start, end):
        day = func.date_trunc("day", Conversation.created_at)
        rows = await self.session.execute(
            select(day, func.count())
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.created_at >= start,
                Conversation.created_at < end,
            )
            .group_by(day)
            .order_by(day)
        )
        values = {row[0].date(): int(row[1]) for row in rows}
        result = []
        current = start.date()
        final = (end - timedelta(microseconds=1)).date()
        while current <= final:
            result.append({"date": current, "count": values.get(current, 0)})
            current += timedelta(days=1)
        return result

    async def _group(self, column, filters):
        rows = await self.session.execute(
            select(column, func.count())
            .where(*filters, column.is_not(None))
            .group_by(column)
        )
        return [
            {
                "key": row[0].value if hasattr(row[0], "value") else str(row[0]),
                "count": int(row[1]),
            }
            for row in rows
        ]

    async def _actions_by_type(self, workspace_id, start, end):
        rows = await self.session.execute(
            select(ActionDefinition.key, ActionDefinition.name, func.count())
            .join(
                ActionRequest,
                ActionRequest.action_definition_id == ActionDefinition.id,
            )
            .where(
                ActionRequest.workspace_id == workspace_id,
                ActionRequest.created_at >= start,
                ActionRequest.created_at < end,
            )
            .group_by(ActionDefinition.key, ActionDefinition.name)
        )
        return [{"key": row[0], "label": row[1], "count": int(row[2])} for row in rows]

    async def _verified_amounts(self, workspace_id, start, end):
        rows = await self.session.execute(
            select(Payment.currency, func.sum(Payment.verified_amount))
            .where(
                Payment.workspace_id == workspace_id,
                Payment.created_at >= start,
                Payment.created_at < end,
                Payment.status == PaymentStatus.VERIFIED,
            )
            .group_by(Payment.currency)
        )
        return [{"currency": row[0], "amount": row[1]} for row in rows]

    async def _verification_statuses(self, workspace_id, start, end):
        rows = await self.session.execute(
            select(PaymentVerification.status, func.count())
            .where(
                PaymentVerification.workspace_id == workspace_id,
                PaymentVerification.created_at >= start,
                PaymentVerification.created_at < end,
            )
            .group_by(PaymentVerification.status)
        )
        return [{"key": row[0].value, "count": int(row[1])} for row in rows]

    async def _queue(self, workspace_id):
        open_statuses = [
            ActionRequestStatus.WAITING,
            ActionRequestStatus.ASSIGNED,
            ActionRequestStatus.IN_PROGRESS,
        ]
        row = (
            await self.session.execute(
                select(
                    func.count().filter(ActionRequest.status.in_(open_statuses)),
                    func.count().filter(
                        ActionRequest.status.in_(open_statuses),
                        ActionRequest.assigned_to_user_id.is_(None),
                    ),
                ).where(ActionRequest.workspace_id == workspace_id)
            )
        ).one()
        attention = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.needs_attention.is_(True),
                )
            )
            or 0
        )
        return {
            "open_actions": int(row[0]),
            "unassigned_actions": int(row[1]),
            "conversations_needing_attention": attention,
        }

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator * 100 / denominator, 1) if denominator else 0.0
