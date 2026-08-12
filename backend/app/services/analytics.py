"""Workspace-scoped PostgreSQL operational analytics."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action import ActionDefinition, ActionRequest, ActionRequestStatus
from app.models.conversation import Conversation
from app.models.message import Message, SenderType
from app.models.payment import Payment, PaymentStatus, PaymentVerification


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
