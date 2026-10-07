"""Guest CRM aggregation over authoritative workspace-scoped domains."""

import uuid

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, WorkspaceAccessDeniedError
from app.models.booking import (
    Booking,
    BookingEvent,
    BookingEventType,
    BookingItem,
    BookingStatus,
)
from app.models.conversation import Conversation
from app.models.conversation_read_state import ConversationReadState
from app.models.crm import (
    CustomerCRMEvent,
    CustomerCRMEventType,
    CustomerNote,
    CustomerPreference,
    CustomerTag,
    CustomerTagAssignment,
)
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity
from app.models.hotel import Property
from app.models.message import Message
from app.models.payment import Payment, PaymentStatus
from app.models.stay import HotelRoom, Stay, StayEvent, StayRoomAssignment
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.crm import (
    BookingSummary,
    ConversationSummary,
    CRMCustomer,
    Customer360Response,
    CustomerIdentitySummary,
    CustomerListItem,
    CustomerListResponse,
    CustomerNoteCreate,
    CustomerNoteResponse,
    CustomerPreferenceResponse,
    CustomerPreferenceUpdate,
    CustomerPreferenceWrite,
    CustomerTagCreate,
    CustomerTagResponse,
    PaymentExceptionSummary,
    PaymentSummary,
    RepeatGuestSummary,
    StaySummary,
    TimelineEvent,
    TimelineResponse,
)


class Customer360Service:
    """Compose CRM views without copying Booking, Payment, or Conversation state."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _customer(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID, *, lock: bool = False
    ) -> Customer:
        query = select(Customer).where(
            Customer.workspace_id == workspace_id,
            Customer.id == customer_id,
            Customer.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update()
        customer = await self.session.scalar(query)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    async def _role(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceRole:
        role = await self.session.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if role is None:
            raise NotFoundError("Customer not found")
        return role

    async def _require_admin(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        if await self._role(workspace_id, user_id) not in {
            WorkspaceRole.OWNER,
            WorkspaceRole.ADMIN,
        }:
            raise WorkspaceAccessDeniedError("Owner or admin access required")

    async def list_customers(
        self,
        workspace_id: uuid.UUID,
        *,
        search: str | None,
        tag_id: uuid.UUID | None,
        has_active_booking: bool | None,
        has_payment_exception: bool | None,
        repeat_guest: bool | None,
        needs_attention: bool | None,
        page: int,
        page_size: int,
    ) -> CustomerListResponse:
        booking_count = (
            select(func.count(Booking.id))
            .where(
                Booking.workspace_id == workspace_id,
                Booking.customer_id == Customer.id,
            )
            .correlate(Customer)
            .scalar_subquery()
        )
        confirmed_count = (
            select(func.count(Booking.id))
            .where(
                Booking.workspace_id == workspace_id,
                Booking.customer_id == Customer.id,
                Booking.status == BookingStatus.CONFIRMED,
            )
            .correlate(Customer)
            .scalar_subquery()
        )
        latest_status = (
            select(Booking.status)
            .where(
                Booking.workspace_id == workspace_id,
                Booking.customer_id == Customer.id,
            )
            .order_by(Booking.created_at.desc(), Booking.id.desc())
            .limit(1)
            .correlate(Customer)
            .scalar_subquery()
        )
        last_conversation = (
            select(func.max(Conversation.last_message_at))
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.customer_id == Customer.id,
            )
            .correlate(Customer)
            .scalar_subquery()
        )
        active_booking_exists = exists(
            select(Booking.id).where(
                Booking.workspace_id == workspace_id,
                Booking.customer_id == Customer.id,
                Booking.status.in_(
                    (
                        BookingStatus.DRAFT,
                        BookingStatus.HELD,
                        BookingStatus.PENDING_PAYMENT,
                        BookingStatus.CONFIRMED,
                    )
                ),
            )
        )
        attention_exists = exists(
            select(Conversation.id).where(
                Conversation.workspace_id == workspace_id,
                Conversation.customer_id == Customer.id,
                Conversation.needs_attention.is_(True),
            )
        )
        exception_exists = exists(
            select(Payment.id)
            .outerjoin(
                Booking,
                (Payment.booking_id == Booking.id)
                & (Payment.workspace_id == Booking.workspace_id),
            )
            .where(
                Payment.workspace_id == workspace_id,
                or_(
                    Payment.customer_id == Customer.id,
                    Booking.customer_id == Customer.id,
                ),
                Payment.status == PaymentStatus.VERIFIED,
                Payment.booking_applied_at.is_(None),
            )
        )
        query = select(
            Customer,
            booking_count.label("booking_count"),
            confirmed_count.label("confirmed_count"),
            latest_status.label("latest_status"),
            last_conversation.label("last_conversation"),
            exception_exists.label("has_exception"),
            attention_exists.label("needs_attention"),
        ).where(
            Customer.workspace_id == workspace_id,
            Customer.deleted_at.is_(None),
        )
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Customer.display_name.ilike(pattern),
                    Customer.full_name.ilike(pattern),
                    Customer.email.ilike(pattern),
                    Customer.phone.ilike(pattern),
                )
            )
        if tag_id is not None:
            query = query.where(
                exists(
                    select(CustomerTagAssignment.id).where(
                        CustomerTagAssignment.workspace_id == workspace_id,
                        CustomerTagAssignment.customer_id == Customer.id,
                        CustomerTagAssignment.tag_id == tag_id,
                    )
                )
            )
        if has_active_booking is not None:
            query = query.where(active_booking_exists == has_active_booking)
        if has_payment_exception is not None:
            query = query.where(exception_exists == has_payment_exception)
        if repeat_guest is not None:
            query = query.where((confirmed_count >= 2) == repeat_guest)
        if needs_attention is not None:
            query = query.where(attention_exists == needs_attention)

        total = int(
            await self.session.scalar(
                select(func.count()).select_from(query.subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                query.order_by(Customer.updated_at.desc(), Customer.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        customer_ids = [row[0].id for row in rows]
        tags_by_customer: dict[uuid.UUID, list[CustomerTag]] = {
            customer_id: [] for customer_id in customer_ids
        }
        if customer_ids:
            tag_rows = (
                await self.session.execute(
                    select(CustomerTagAssignment.customer_id, CustomerTag)
                    .join(
                        CustomerTag,
                        (CustomerTag.id == CustomerTagAssignment.tag_id)
                        & (
                            CustomerTag.workspace_id
                            == CustomerTagAssignment.workspace_id
                        ),
                    )
                    .where(
                        CustomerTagAssignment.workspace_id == workspace_id,
                        CustomerTagAssignment.customer_id.in_(customer_ids),
                    )
                    .order_by(CustomerTag.name, CustomerTag.id)
                )
            ).all()
            for customer_id, tag in tag_rows:
                tags_by_customer[customer_id].append(tag)
        items = [
            CustomerListItem(
                customer=CRMCustomer.model_validate(row[0]),
                tags=[
                    CustomerTagResponse.model_validate(tag)
                    for tag in tags_by_customer[row[0].id]
                ],
                booking_count=int(row.booking_count),
                confirmed_bookings=int(row.confirmed_count),
                repeat_guest=int(row.confirmed_count) >= 2,
                latest_booking_status=row.latest_status,
                has_payment_exception=bool(row.has_exception),
                last_conversation_at=row.last_conversation,
                needs_attention=bool(row.needs_attention),
            )
            for row in rows
        ]
        return CustomerListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    async def get_customer_360(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        limit: int = 20,
    ) -> Customer360Response:
        customer = await self._customer(workspace_id, customer_id)
        await self._role(workspace_id, user_id)
        identities = list(
            (
                await self.session.scalars(
                    select(CustomerIdentity)
                    .where(
                        CustomerIdentity.workspace_id == workspace_id,
                        CustomerIdentity.customer_id == customer_id,
                    )
                    .order_by(CustomerIdentity.created_at, CustomerIdentity.id)
                    .limit(limit)
                )
            ).all()
        )
        tags = await self._tags(workspace_id, customer_id, limit)
        preferences = list(
            (
                await self.session.scalars(
                    select(CustomerPreference)
                    .where(
                        CustomerPreference.workspace_id == workspace_id,
                        CustomerPreference.customer_id == customer_id,
                    )
                    .order_by(CustomerPreference.key, CustomerPreference.id)
                    .limit(limit)
                )
            ).all()
        )
        notes = list(
            (
                await self.session.scalars(
                    select(CustomerNote)
                    .where(
                        CustomerNote.workspace_id == workspace_id,
                        CustomerNote.customer_id == customer_id,
                    )
                    .order_by(CustomerNote.created_at.desc(), CustomerNote.id.desc())
                    .limit(limit)
                )
            ).all()
        )
        preview = (
            select(Message.content)
            .where(Message.conversation_id == Conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
        )
        conversation_rows = (
            await self.session.execute(
                select(Conversation, preview, ConversationReadState.last_read_at)
                .outerjoin(
                    ConversationReadState,
                    (ConversationReadState.conversation_id == Conversation.id)
                    & (ConversationReadState.workspace_id == workspace_id)
                    & (ConversationReadState.user_id == user_id),
                )
                .where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.customer_id == customer_id,
                )
                .order_by(
                    Conversation.last_message_at.desc().nullslast(), Conversation.id
                )
                .limit(limit)
            )
        ).all()
        confirmed_at = (
            select(func.max(BookingEvent.created_at))
            .where(
                BookingEvent.booking_id == Booking.id,
                BookingEvent.event_type == BookingEventType.BOOKING_CONFIRMED,
            )
            .correlate(Booking)
            .scalar_subquery()
        )
        booking_rows = (
            await self.session.execute(
                select(Booking, BookingItem.room_type_name_snapshot, confirmed_at)
                .outerjoin(
                    BookingItem,
                    (BookingItem.booking_id == Booking.id)
                    & (BookingItem.workspace_id == Booking.workspace_id),
                )
                .where(
                    Booking.workspace_id == workspace_id,
                    Booking.customer_id == customer_id,
                )
                .order_by(Booking.created_at.desc(), Booking.id.desc())
                .limit(limit)
            )
        ).all()
        customer_booking_ids = select(Booking.id).where(
            Booking.workspace_id == workspace_id, Booking.customer_id == customer_id
        )
        payments = list(
            (
                await self.session.scalars(
                    select(Payment)
                    .where(
                        Payment.workspace_id == workspace_id,
                        or_(
                            Payment.customer_id == customer_id,
                            Payment.booking_id.in_(customer_booking_ids),
                        ),
                    )
                    .order_by(Payment.created_at.desc(), Payment.id.desc())
                    .limit(limit)
                )
            ).all()
        )
        stay_rows = (
            await self.session.execute(
                select(Stay, Property.name)
                .join(
                    Property,
                    (Property.id == Stay.property_id)
                    & (Property.workspace_id == Stay.workspace_id),
                )
                .where(
                    Stay.workspace_id == workspace_id,
                    Stay.customer_id == customer_id,
                )
                .order_by(Stay.created_at.desc(), Stay.id.desc())
                .limit(limit)
            )
        ).all()
        stay_ids = [stay.id for stay, _ in stay_rows]
        rooms_by_stay: dict[uuid.UUID, list[str]] = {
            stay_id: [] for stay_id in stay_ids
        }
        if stay_ids:
            assignment_rows = (
                await self.session.execute(
                    select(StayRoomAssignment.stay_id, HotelRoom.code)
                    .join(
                        HotelRoom,
                        (HotelRoom.id == StayRoomAssignment.room_id)
                        & (HotelRoom.workspace_id == StayRoomAssignment.workspace_id),
                    )
                    .where(
                        StayRoomAssignment.workspace_id == workspace_id,
                        StayRoomAssignment.stay_id.in_(stay_ids),
                    )
                    .order_by(StayRoomAssignment.assigned_at, HotelRoom.code)
                )
            ).all()
            for stay_id, room_code in assignment_rows:
                rooms_by_stay[stay_id].append(room_code)
        repeat = await self._repeat_summary(workspace_id, customer_id)
        return Customer360Response(
            customer=CRMCustomer.model_validate(customer),
            identities=[
                CustomerIdentitySummary.model_validate(item) for item in identities
            ],
            tags=[CustomerTagResponse.model_validate(item) for item in tags],
            preferences=[
                CustomerPreferenceResponse.model_validate(item) for item in preferences
            ],
            notes=[CustomerNoteResponse.model_validate(item) for item in notes],
            conversations=[
                ConversationSummary(
                    id=conversation.id,
                    channel=conversation.channel,
                    status=conversation.status,
                    ai_mode=conversation.ai_mode,
                    assigned_user_id=conversation.assigned_user_id,
                    last_message_at=conversation.last_message_at,
                    needs_attention=conversation.needs_attention,
                    unread=conversation.last_message_at is not None
                    and (
                        last_read_at is None
                        or last_read_at < conversation.last_message_at
                    ),
                    preview=text[:200] if text else None,
                )
                for conversation, text, last_read_at in conversation_rows
            ],
            bookings=[
                BookingSummary(
                    id=booking.id,
                    property_name=booking.property_name_snapshot,
                    room_type_name=room_name,
                    check_in=booking.check_in,
                    check_out=booking.check_out,
                    status=booking.status,
                    total_amount=booking.total_amount,
                    currency=booking.currency,
                    created_at=booking.created_at,
                    confirmed_at=confirmed,
                )
                for booking, room_name, confirmed in booking_rows
            ],
            payments=[self._payment_summary(payment) for payment in payments],
            payment_exceptions=[
                PaymentExceptionSummary(
                    payment_id=payment.id,
                    booking_id=payment.booking_id,
                    reason=payment.booking_application_reason,
                    verified_amount=payment.verified_amount,
                    currency=payment.currency,
                    verified_at=payment.verified_at,
                )
                for payment in payments
                if payment.status == PaymentStatus.VERIFIED
                and payment.booking_applied_at is None
            ],
            stays=[
                StaySummary(
                    id=stay.id,
                    booking_id=stay.booking_id,
                    property_name=property_name,
                    room_codes=rooms_by_stay[stay.id],
                    planned_check_in_date=stay.planned_check_in_date,
                    planned_check_out_date=stay.planned_check_out_date,
                    actual_check_in_at=stay.actual_check_in_at,
                    actual_check_out_at=stay.actual_check_out_at,
                    status=stay.status.value,
                )
                for stay, property_name in stay_rows
            ],
            repeat_guest_summary=repeat,
        )

    async def create_tag(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, data: CustomerTagCreate
    ) -> CustomerTag:
        await self._require_admin(workspace_id, user_id)
        normalized = data.name.casefold()
        stmt = (
            insert(CustomerTag)
            .values(
                workspace_id=workspace_id, name=data.name, normalized_name=normalized
            )
            .on_conflict_do_nothing(
                index_elements=[CustomerTag.workspace_id, CustomerTag.normalized_name]
            )
            .returning(CustomerTag.id)
        )
        tag_id = await self.session.scalar(stmt)
        if tag_id is None:
            tag = await self.session.scalar(
                select(CustomerTag).where(
                    CustomerTag.workspace_id == workspace_id,
                    CustomerTag.normalized_name == normalized,
                )
            )
        else:
            tag = await self.session.get(CustomerTag, tag_id)
        await self.session.commit()
        return tag

    async def list_tags(self, workspace_id: uuid.UUID) -> list[CustomerTag]:
        return list(
            (
                await self.session.scalars(
                    select(CustomerTag)
                    .where(CustomerTag.workspace_id == workspace_id)
                    .order_by(CustomerTag.name, CustomerTag.id)
                    .limit(200)
                )
            ).all()
        )

    async def assign_tag(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        tag_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CustomerTag:
        await self._require_admin(workspace_id, user_id)
        await self._customer(workspace_id, customer_id, lock=True)
        tag = await self.session.scalar(
            select(CustomerTag).where(
                CustomerTag.workspace_id == workspace_id, CustomerTag.id == tag_id
            )
        )
        if tag is None:
            raise NotFoundError("Customer tag not found")
        assignment_id = await self.session.scalar(
            insert(CustomerTagAssignment)
            .values(
                workspace_id=workspace_id,
                customer_id=customer_id,
                tag_id=tag_id,
                created_by_user_id=user_id,
            )
            .on_conflict_do_nothing(constraint="uq_customer_tag_assignment")
            .returning(CustomerTagAssignment.id)
        )
        if assignment_id is not None:
            self._event(
                workspace_id,
                customer_id,
                CustomerCRMEventType.TAG_ADDED,
                user_id,
                {"tag_id": str(tag.id), "tag_name": tag.name},
            )
        await self.session.commit()
        return tag

    async def remove_tag(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        tag_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        await self._require_admin(workspace_id, user_id)
        await self._customer(workspace_id, customer_id, lock=True)
        tag = await self.session.scalar(
            select(CustomerTag).where(
                CustomerTag.workspace_id == workspace_id, CustomerTag.id == tag_id
            )
        )
        if tag is None:
            raise NotFoundError("Customer tag not found")
        result = await self.session.execute(
            delete(CustomerTagAssignment).where(
                CustomerTagAssignment.workspace_id == workspace_id,
                CustomerTagAssignment.customer_id == customer_id,
                CustomerTagAssignment.tag_id == tag_id,
            )
        )
        if result.rowcount:
            self._event(
                workspace_id,
                customer_id,
                CustomerCRMEventType.TAG_REMOVED,
                user_id,
                {"tag_id": str(tag.id), "tag_name": tag.name},
            )
        await self.session.commit()

    async def set_preference(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CustomerPreferenceWrite,
    ) -> CustomerPreference:
        await self._role(workspace_id, user_id)
        await self._customer(workspace_id, customer_id, lock=True)
        preference = await self.session.scalar(
            select(CustomerPreference).where(
                CustomerPreference.workspace_id == workspace_id,
                CustomerPreference.customer_id == customer_id,
                CustomerPreference.key == data.key,
            )
        )
        event_type = CustomerCRMEventType.PREFERENCE_UPDATED
        if preference is None:
            event_type = CustomerCRMEventType.PREFERENCE_ADDED
            preference = CustomerPreference(
                workspace_id=workspace_id,
                customer_id=customer_id,
                key=data.key,
            )
            self.session.add(preference)
        preference.value = data.value
        preference.source = data.source
        preference.confirmed_by_user_id = user_id
        await self.session.flush()
        self._event(
            workspace_id,
            customer_id,
            event_type,
            user_id,
            {"preference_id": str(preference.id), "key": data.key.value},
        )
        await self.session.commit()
        await self.session.refresh(preference)
        return preference

    async def add_note(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CustomerNoteCreate,
    ) -> CustomerNote:
        await self._role(workspace_id, user_id)
        await self._customer(workspace_id, customer_id)
        note = CustomerNote(
            workspace_id=workspace_id,
            customer_id=customer_id,
            body=data.body,
            created_by_user_id=user_id,
        )
        self.session.add(note)
        await self.session.flush()
        self._event(
            workspace_id,
            customer_id,
            CustomerCRMEventType.NOTE_ADDED,
            user_id,
            {"note_id": str(note.id)},
        )
        await self.session.commit()
        await self.session.refresh(note)
        return note

    async def update_preference(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        preference_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CustomerPreferenceUpdate,
    ) -> CustomerPreference:
        preference = await self.session.scalar(
            select(CustomerPreference).where(
                CustomerPreference.workspace_id == workspace_id,
                CustomerPreference.customer_id == customer_id,
                CustomerPreference.id == preference_id,
            )
        )
        if preference is None:
            raise NotFoundError("Customer preference not found")
        return await self.set_preference(
            workspace_id,
            customer_id,
            user_id,
            CustomerPreferenceWrite(
                key=preference.key, value=data.value, source=data.source
            ),
        )

    async def timeline(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
    ) -> TimelineResponse:
        await self._customer(workspace_id, customer_id)
        await self._role(workspace_id, user_id)
        # Customer timelines are operationally bounded per source. Fetching the
        # fixed cap keeps total/order deterministic across pages without an
        # unbounded history scan.
        source_limit = 1000
        events: list[TimelineEvent] = []
        crm_events = list(
            (
                await self.session.scalars(
                    select(CustomerCRMEvent)
                    .where(
                        CustomerCRMEvent.workspace_id == workspace_id,
                        CustomerCRMEvent.customer_id == customer_id,
                    )
                    .order_by(CustomerCRMEvent.created_at.desc(), CustomerCRMEvent.id)
                    .limit(source_limit)
                )
            ).all()
        )
        events.extend(
            TimelineEvent(
                id=f"crm:{event.id}",
                type=event.event_type.value,
                occurred_at=event.created_at,
                entity_type="customer",
                entity_id=customer_id,
                summary=event.event_type.value.replace("_", " ").title(),
                metadata={
                    key: value
                    for key, value in event.event_metadata.items()
                    if isinstance(value, (str, int, bool)) or value is None
                },
            )
            for event in crm_events
        )
        booking_events = (
            await self.session.execute(
                select(BookingEvent)
                .join(
                    Booking,
                    (Booking.id == BookingEvent.booking_id)
                    & (Booking.workspace_id == BookingEvent.workspace_id),
                )
                .where(
                    BookingEvent.workspace_id == workspace_id,
                    Booking.customer_id == customer_id,
                )
                .order_by(BookingEvent.created_at.desc(), BookingEvent.id)
                .limit(source_limit)
            )
        ).scalars()
        events.extend(
            TimelineEvent(
                id=f"booking:{event.id}",
                type=event.event_type.value,
                occurred_at=event.created_at,
                entity_type="booking",
                entity_id=event.booking_id,
                summary=event.event_type.value.replace("_", " ").title(),
                metadata={
                    key: value
                    for key, value in event.event_metadata.items()
                    if isinstance(value, (str, int, bool)) or value is None
                },
            )
            for event in booking_events
        )
        stay_events = (
            await self.session.execute(
                select(StayEvent)
                .join(
                    Stay,
                    (Stay.id == StayEvent.stay_id)
                    & (Stay.workspace_id == StayEvent.workspace_id),
                )
                .where(
                    StayEvent.workspace_id == workspace_id,
                    Stay.customer_id == customer_id,
                )
                .order_by(StayEvent.created_at.desc(), StayEvent.id)
                .limit(source_limit)
            )
        ).scalars()
        events.extend(
            TimelineEvent(
                id=f"stay:{event.id}",
                type=event.event_type.value,
                occurred_at=event.created_at,
                entity_type="stay",
                entity_id=event.stay_id,
                summary=event.event_type.value.replace("_", " ").title(),
                metadata={"room_id": str(event.room_id)} if event.room_id else {},
            )
            for event in stay_events
        )
        conversations = list(
            (
                await self.session.scalars(
                    select(Conversation)
                    .where(
                        Conversation.workspace_id == workspace_id,
                        Conversation.customer_id == customer_id,
                    )
                    .order_by(Conversation.created_at.desc(), Conversation.id)
                    .limit(source_limit)
                )
            ).all()
        )
        for conversation in conversations:
            events.append(
                TimelineEvent(
                    id=f"conversation:{conversation.id}:created",
                    type="CONVERSATION_STARTED",
                    occurred_at=conversation.created_at,
                    entity_type="conversation",
                    entity_id=conversation.id,
                    summary="Conversation started",
                    metadata={"channel": conversation.channel.value},
                )
            )
            if conversation.handoff_requested_at:
                events.append(
                    TimelineEvent(
                        id=f"conversation:{conversation.id}:handoff",
                        type="HANDOFF_REQUESTED",
                        occurred_at=conversation.handoff_requested_at,
                        entity_type="conversation",
                        entity_id=conversation.id,
                        summary="Human handoff requested",
                        metadata={
                            "reason": conversation.handoff_reason.value
                            if conversation.handoff_reason
                            else None
                        },
                    )
                )
            if conversation.assigned_at:
                events.append(
                    TimelineEvent(
                        id=f"conversation:{conversation.id}:assigned",
                        type="CONVERSATION_ASSIGNED",
                        occurred_at=conversation.assigned_at,
                        entity_type="conversation",
                        entity_id=conversation.id,
                        summary="Conversation assigned",
                    )
                )
        payments = list(
            (
                await self.session.scalars(
                    select(Payment)
                    .outerjoin(
                        Booking,
                        (Payment.booking_id == Booking.id)
                        & (Payment.workspace_id == Booking.workspace_id),
                    )
                    .where(
                        Payment.workspace_id == workspace_id,
                        or_(
                            Payment.customer_id == customer_id,
                            Booking.customer_id == customer_id,
                        ),
                    )
                    .order_by(Payment.created_at.desc(), Payment.id)
                    .limit(source_limit)
                )
            ).all()
        )
        for payment in payments:
            events.append(
                TimelineEvent(
                    id=f"payment:{payment.id}:created",
                    type="PAYMENT_CREATED",
                    occurred_at=payment.created_at,
                    entity_type="payment",
                    entity_id=payment.id,
                    summary="Payment created",
                )
            )
            if payment.verified_at:
                events.append(
                    TimelineEvent(
                        id=f"payment:{payment.id}:verified",
                        type="PAYMENT_VERIFIED",
                        occurred_at=payment.verified_at,
                        entity_type="payment",
                        entity_id=payment.id,
                        summary="Payment verified",
                    )
                )
        events.sort(
            key=lambda event: (event.occurred_at, event.type, event.id), reverse=True
        )
        total = len(events)
        start = (page - 1) * page_size
        return TimelineResponse(
            items=events[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    async def _tags(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID, limit: int
    ) -> list[CustomerTag]:
        return list(
            (
                await self.session.scalars(
                    select(CustomerTag)
                    .join(
                        CustomerTagAssignment,
                        (CustomerTagAssignment.tag_id == CustomerTag.id)
                        & (
                            CustomerTagAssignment.workspace_id
                            == CustomerTag.workspace_id
                        ),
                    )
                    .where(
                        CustomerTag.workspace_id == workspace_id,
                        CustomerTagAssignment.customer_id == customer_id,
                    )
                    .order_by(CustomerTag.name, CustomerTag.id)
                    .limit(limit)
                )
            ).all()
        )

    async def _repeat_summary(
        self, workspace_id: uuid.UUID, customer_id: uuid.UUID
    ) -> RepeatGuestSummary:
        row = (
            await self.session.execute(
                select(
                    func.count(Booking.id).filter(
                        Booking.status == BookingStatus.CONFIRMED
                    ),
                    func.count(Booking.id).filter(
                        Booking.status == BookingStatus.CANCELLED
                    ),
                    func.max(Booking.check_in),
                ).where(
                    Booking.workspace_id == workspace_id,
                    Booking.customer_id == customer_id,
                )
            )
        ).one()
        confirmed = int(row[0] or 0)
        return RepeatGuestSummary(
            repeat_guest=confirmed >= 2,
            confirmed_bookings=confirmed,
            cancelled_bookings=int(row[1] or 0),
            latest_booking_date=row[2],
        )

    @staticmethod
    def _payment_summary(payment: Payment) -> PaymentSummary:
        return PaymentSummary(
            id=payment.id,
            booking_id=payment.booking_id,
            expected_amount=payment.expected_amount,
            verified_amount=payment.verified_amount,
            currency=payment.currency,
            status=payment.status,
            application_status=payment.booking_application_status,
            application_reason=payment.booking_application_reason,
            created_at=payment.created_at,
            verified_at=payment.verified_at,
            booking_applied_at=payment.booking_applied_at,
        )

    def _event(
        self,
        workspace_id: uuid.UUID,
        customer_id: uuid.UUID,
        event_type: CustomerCRMEventType,
        actor_user_id: uuid.UUID,
        metadata: dict,
    ) -> None:
        self.session.add(
            CustomerCRMEvent(
                workspace_id=workspace_id,
                customer_id=customer_id,
                event_type=event_type,
                actor_user_id=actor_user_id,
                event_metadata=metadata,
            )
        )
