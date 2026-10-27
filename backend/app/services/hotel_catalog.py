"""Rich room catalog, image storage, and bounded calendar services."""

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.audit import AuditActorType, AuditArea
from app.models.hotel import InventoryDate, RoomType
from app.models.hotel_catalog import (
    AmenityDefinition,
    AmenityValueType,
    RoomTypeAmenity,
    RoomTypeBed,
    RoomTypeImage,
)
from app.models.pms import PMSConnection, PMSEntityType, PMSExternalMapping
from app.models.stay import HotelRoom, RoomOperationalStatus, RoomReadinessStatus
from app.schemas.hotel import RoomTypeResponse
from app.schemas.hotel_catalog import (
    AvailabilityCalendarCell,
    AvailabilityCalendarResponse,
    AvailabilityCalendarRow,
    CustomerRoomFacts,
    RichRoomTypeCreate,
    RoomCatalogDetail,
    RoomTypeAmenityInput,
    RoomTypeAmenityResponse,
    RoomTypeBedInput,
    RoomTypeBedResponse,
    RoomTypeImageCreate,
    RoomTypeImageOrderItem,
    RoomTypeImageResponse,
)
from app.services.audit import AuditService, current_actor_user_id
from app.services.hotel import (
    HotelCatalogService,
    HotelConflictError,
    HotelValidationError,
)
from app.storage import StorageProvider, create_storage_provider

ROOM_IMAGE_MAX_BYTES = 10 * 1024 * 1024

_AMENITIES: dict[str, tuple[str, str, str, str]] = {}


def _register(
    category: str, value_type: str, entries: list[tuple[str, str, str]]
) -> None:
    for code, en, th in entries:
        _AMENITIES[code] = (category, value_type, en, th)


_register(
    "BATHROOM",
    "BOOLEAN",
    [
        ("private_bathroom", "Private bathroom", "ห้องน้ำส่วนตัว"),
        ("hot_water", "Hot water", "น้ำร้อน"),
        ("water_heater", "Water heater", "เครื่องทำน้ำอุ่น"),
        ("shower", "Shower", "ฝักบัว"),
        ("bathtub", "Bathtub", "อ่างอาบน้ำ"),
        ("hair_dryer", "Hair dryer", "ไดร์เป่าผม"),
        ("towels", "Towels", "ผ้าเช็ดตัว"),
        ("bath_towels", "Bath towels", "ผ้าเช็ดตัวผืนใหญ่"),
        ("hand_towels", "Hand towels", "ผ้าเช็ดมือ"),
        ("toiletries", "Toiletries", "ของใช้ในห้องน้ำ"),
        ("shampoo", "Shampoo", "แชมพู"),
        ("conditioner", "Conditioner", "ครีมนวดผม"),
        ("body_wash", "Body wash", "ครีมอาบน้ำ"),
        ("soap", "Soap", "สบู่"),
        ("toothbrush_kit", "Toothbrush kit", "ชุดแปรงสีฟัน"),
        ("shower_cap", "Shower cap", "หมวกคลุมผม"),
        ("slippers", "Slippers", "รองเท้าแตะ"),
    ],
)
_register(
    "BEDROOM_FURNITURE",
    "BOOLEAN",
    [
        ("wardrobe", "Wardrobe", "ตู้เสื้อผ้า"),
        ("clothes_hangers", "Clothes hangers", "ไม้แขวนเสื้อ"),
        ("desk", "Desk", "โต๊ะทำงาน"),
        ("chair", "Chair", "เก้าอี้"),
        ("sofa", "Sofa", "โซฟา"),
        ("blackout_curtains", "Blackout curtains", "ม่านทึบแสง"),
        ("mirror", "Mirror", "กระจก"),
        ("full_length_mirror", "Full-length mirror", "กระจกเต็มตัว"),
        ("safe", "Safe", "ตู้นิรภัย"),
        ("luggage_rack", "Luggage rack", "ชั้นวางกระเป๋า"),
    ],
)
_register(
    "ENTERTAINMENT",
    "BOOLEAN",
    [
        ("television", "Television", "โทรทัศน์"),
        ("smart_tv", "Smart TV", "สมาร์ตทีวี"),
        ("cable_tv", "Cable TV", "เคเบิลทีวี"),
        ("streaming_support", "Streaming support", "รองรับสตรีมมิง"),
    ],
)
_register(
    "ENTERTAINMENT", "NUMBER", [("tv_size_inches", "TV size (inches)", "ขนาดทีวี (นิ้ว)")]
)
_register(
    "FOOD_AND_DRINK",
    "BOOLEAN",
    [
        ("refrigerator", "Refrigerator", "ตู้เย็น"),
        ("mini_fridge", "Mini fridge", "ตู้เย็นขนาดเล็ก"),
        ("minibar", "Minibar", "มินิบาร์"),
        ("free_drinking_water", "Free drinking water", "น้ำดื่มฟรี"),
        ("kettle", "Kettle", "กาต้มน้ำ"),
        ("coffee_maker", "Coffee maker", "เครื่องชงกาแฟ"),
        ("tea", "Tea", "ชา"),
        ("coffee", "Coffee", "กาแฟ"),
        ("snacks", "Snacks", "ของว่าง"),
        ("microwave", "Microwave", "ไมโครเวฟ"),
        ("kitchenette", "Kitchenette", "ครัวขนาดเล็ก"),
        ("dining_table", "Dining table", "โต๊ะรับประทานอาหาร"),
    ],
)
_register(
    "COMFORT",
    "BOOLEAN",
    [
        ("air_conditioning", "Air conditioning", "เครื่องปรับอากาศ"),
        ("fan", "Fan", "พัดลม"),
        ("heating", "Heating", "เครื่องทำความร้อน"),
        ("balcony", "Balcony", "ระเบียง"),
        ("terrace", "Terrace", "ชานระเบียง"),
    ],
)
_register(
    "CONNECTIVITY",
    "BOOLEAN",
    [
        ("wifi", "Wi-Fi", "Wi-Fi"),
        ("ethernet", "Ethernet", "อีเทอร์เน็ต"),
        ("telephone", "Telephone", "โทรศัพท์"),
    ],
)
_register(
    "SAFETY",
    "BOOLEAN",
    [
        ("smoke_detector", "Smoke detector", "เครื่องตรวจจับควัน"),
        ("fire_extinguisher", "Fire extinguisher", "ถังดับเพลิง"),
        ("emergency_light", "Emergency light", "ไฟฉุกเฉิน"),
        ("electronic_door_lock", "Electronic door lock", "กลอนประตูอิเล็กทรอนิกส์"),
    ],
)
_register(
    "ACCESSIBILITY",
    "BOOLEAN",
    [
        ("wheelchair_accessible", "Wheelchair accessible", "รองรับรถเข็น"),
        ("accessible_bathroom", "Accessible bathroom", "ห้องน้ำสำหรับผู้ใช้รถเข็น"),
        ("grab_bars", "Grab bars", "ราวจับ"),
        ("elevator_access", "Elevator access", "เข้าถึงด้วยลิฟต์"),
    ],
)
_register(
    "OTHER",
    "BOOLEAN",
    [
        ("iron", "Iron", "เตารีด"),
        ("ironing_board", "Ironing board", "โต๊ะรีดผ้า"),
        ("laundry_bag", "Laundry bag", "ถุงซักผ้า"),
        ("umbrella", "Umbrella", "ร่ม"),
    ],
)
_register(
    "OTHER", "TEXT", [("custom_amenity", "Custom amenity", "สิ่งอำนวยความสะดวกเพิ่มเติม")]
)


class RichHotelCatalogService:
    def __init__(
        self, session: AsyncSession, storage: StorageProvider | None = None
    ) -> None:
        self.session = session
        self.catalog = HotelCatalogService(session)
        self.storage = storage or create_storage_provider()

    async def ensure_amenity_registry(self) -> list[AmenityDefinition]:
        rows = [
            {
                "id": uuid.uuid4(),
                "code": code,
                "category": values[0],
                "value_type": values[1],
                "default_name_en": values[2],
                "default_name_th": values[3],
                "active": True,
                "sort_order": index,
            }
            for index, (code, values) in enumerate(_AMENITIES.items())
        ]
        await self.session.execute(
            insert(AmenityDefinition)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["code"])
        )
        await self.session.flush()
        return list(
            (
                await self.session.scalars(
                    select(AmenityDefinition)
                    .where(AmenityDefinition.active.is_(True))
                    .order_by(
                        AmenityDefinition.category,
                        AmenityDefinition.sort_order,
                        AmenityDefinition.code,
                    )
                )
            ).all()
        )

    async def create_rich_room_type(
        self, workspace_id: uuid.UUID, payload: RichRoomTypeCreate
    ) -> RoomCatalogDetail:
        await self.catalog.get_property(workspace_id, payload.property_id)
        scalar = payload.model_dump(exclude={"beds", "amenities", "physical_rooms"})
        room_type = RoomType(workspace_id=workspace_id, **scalar)
        self.session.add(room_type)
        await self.session.flush()
        try:
            await self._replace_beds(workspace_id, room_type.id, payload.beds)
            await self._replace_amenities(workspace_id, room_type.id, payload.amenities)
            for room in payload.physical_rooms:
                self.session.add(
                    HotelRoom(
                        workspace_id=workspace_id,
                        property_id=room_type.property_id,
                        room_type_id=room_type.id,
                        **room.model_dump(),
                        active=True,
                        operational_status=RoomOperationalStatus.AVAILABLE,
                        readiness_status=RoomReadinessStatus.READY,
                    )
                )
            self._audit(
                workspace_id,
                "ROOM_TYPE_CREATED",
                room_type.id,
                {"physical_room_count": len(payload.physical_rooms)},
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HotelConflictError(
                "Room type, room code, or ordered catalog item already exists"
            ) from exc
        return await self.detail(workspace_id, room_type.id)

    async def detail(
        self, workspace_id: uuid.UUID, room_type_id: uuid.UUID
    ) -> RoomCatalogDetail:
        room = await self.catalog.get_room_type(workspace_id, room_type_id)
        beds = list(
            (
                await self.session.scalars(
                    select(RoomTypeBed)
                    .where(
                        RoomTypeBed.workspace_id == workspace_id,
                        RoomTypeBed.room_type_id == room_type_id,
                    )
                    .order_by(RoomTypeBed.sort_order, RoomTypeBed.id)
                )
            ).all()
        )
        amenities = await self._amenity_responses(workspace_id, room_type_id)
        images = list(
            (
                await self.session.scalars(
                    select(RoomTypeImage)
                    .where(
                        RoomTypeImage.workspace_id == workspace_id,
                        RoomTypeImage.room_type_id == room_type_id,
                    )
                    .order_by(
                        RoomTypeImage.is_cover.desc(),
                        RoomTypeImage.sort_order,
                        RoomTypeImage.id,
                    )
                )
            ).all()
        )
        count = int(
            await self.session.scalar(
                select(func.count(HotelRoom.id)).where(
                    HotelRoom.workspace_id == workspace_id,
                    HotelRoom.room_type_id == room_type_id,
                    HotelRoom.active.is_(True),
                )
            )
            or 0
        )
        return RoomCatalogDetail(
            room_type=RoomTypeResponse.model_validate(room).model_dump(mode="json"),
            beds=[RoomTypeBedResponse.model_validate(item) for item in beds],
            amenities=amenities,
            images=[self._image_response(item) for item in images],
            physical_room_count=count,
        )

    async def replace_beds(self, workspace_id, room_type_id, values):
        await self.catalog.get_room_type(workspace_id, room_type_id)
        await self._replace_beds(workspace_id, room_type_id, values)
        self._audit(
            workspace_id,
            "ROOM_TYPE_UPDATED",
            room_type_id,
            {"changed_fields": ["beds"]},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HotelConflictError("Bed sort order must be unique") from exc
        return (await self.detail(workspace_id, room_type_id)).beds

    async def _replace_beds(
        self, workspace_id, room_type_id, values: list[RoomTypeBedInput]
    ):
        if len({item.sort_order for item in values}) != len(values):
            raise HotelValidationError("Bed sort order must be unique")
        await self.session.execute(
            delete(RoomTypeBed).where(
                RoomTypeBed.workspace_id == workspace_id,
                RoomTypeBed.room_type_id == room_type_id,
            )
        )
        self.session.add_all(
            [
                RoomTypeBed(
                    workspace_id=workspace_id,
                    room_type_id=room_type_id,
                    **item.model_dump(mode="json"),
                )
                for item in values
            ]
        )
        await self.session.flush()

    async def replace_amenities(self, workspace_id, room_type_id, values):
        await self.catalog.get_room_type(workspace_id, room_type_id)
        await self._replace_amenities(workspace_id, room_type_id, values)
        self._audit(
            workspace_id,
            "ROOM_AMENITIES_CHANGED",
            room_type_id,
            {"amenity_count": len(values)},
        )
        await self.session.commit()
        return await self._amenity_responses(workspace_id, room_type_id)

    async def _replace_amenities(
        self, workspace_id, room_type_id, values: list[RoomTypeAmenityInput]
    ):
        if len({item.code for item in values}) != len(values):
            raise HotelValidationError("Amenity codes must be unique")
        definitions = {item.code: item for item in await self.ensure_amenity_registry()}
        await self.session.execute(
            delete(RoomTypeAmenity).where(
                RoomTypeAmenity.workspace_id == workspace_id,
                RoomTypeAmenity.room_type_id == room_type_id,
            )
        )
        for value in values:
            definition = definitions.get(value.code)
            if definition is None:
                raise HotelValidationError("Unknown amenity code")
            expected = {
                AmenityValueType.BOOLEAN.value: value.boolean_value,
                AmenityValueType.NUMBER.value: value.number_value,
                AmenityValueType.TEXT.value: value.text_value,
            }[definition.value_type]
            if expected is None:
                raise HotelValidationError(
                    f"Amenity {value.code} requires "
                    f"{definition.value_type.lower()} value"
                )
            supplied = [value.boolean_value, value.number_value, value.text_value]
            if sum(item is not None for item in supplied) != 1:
                raise HotelValidationError("Amenity value type is invalid")
            self.session.add(
                RoomTypeAmenity(
                    workspace_id=workspace_id,
                    room_type_id=room_type_id,
                    amenity_definition_id=definition.id,
                    boolean_value=value.boolean_value,
                    number_value=value.number_value,
                    text_value=value.text_value,
                )
            )
        await self.session.flush()

    async def _amenity_responses(self, workspace_id, room_type_id):
        rows = (
            await self.session.execute(
                select(RoomTypeAmenity, AmenityDefinition)
                .join(
                    AmenityDefinition,
                    AmenityDefinition.id == RoomTypeAmenity.amenity_definition_id,
                )
                .where(
                    RoomTypeAmenity.workspace_id == workspace_id,
                    RoomTypeAmenity.room_type_id == room_type_id,
                )
                .order_by(
                    AmenityDefinition.category,
                    AmenityDefinition.sort_order,
                    AmenityDefinition.code,
                )
            )
        ).all()
        return [
            RoomTypeAmenityResponse(
                id=value.id,
                amenity_definition_id=definition.id,
                code=definition.code,
                category=definition.category,
                name_en=definition.default_name_en,
                name_th=definition.default_name_th,
                value_type=definition.value_type,
                boolean_value=value.boolean_value,
                number_value=value.number_value,
                text_value=value.text_value,
            )
            for value, definition in rows
        ]

    async def add_image(
        self,
        workspace_id,
        room_type_id,
        metadata: RoomTypeImageCreate,
        data: bytes,
        mime_type: str,
    ):
        await self.catalog.get_room_type(workspace_id, room_type_id)
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HotelValidationError("Only JPEG, PNG, and WebP images are supported")
        if not data or len(data) > ROOM_IMAGE_MAX_BYTES:
            raise HotelValidationError("Room image must be between 1 byte and 10 MB")
        signatures = {
            "image/jpeg": data.startswith(b"\xff\xd8\xff"),
            "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        }
        if not signatures[mime_type]:
            raise HotelValidationError("Image content does not match its MIME type")
        image_id = uuid.uuid4()
        extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[
            mime_type
        ]
        key = f"{workspace_id}/hotel/room-types/{room_type_id}/{image_id}{extension}"
        existing_orders = set(
            await self.session.scalars(
                select(RoomTypeImage.sort_order).where(
                    RoomTypeImage.workspace_id == workspace_id,
                    RoomTypeImage.room_type_id == room_type_id,
                )
            )
        )
        image_order = metadata.sort_order
        if image_order in existing_orders:
            image_order = max(existing_orders, default=-1) + 1
        image_values = metadata.model_dump(mode="json")
        image_values["sort_order"] = image_order
        image = RoomTypeImage(
            id=image_id,
            workspace_id=workspace_id,
            room_type_id=room_type_id,
            storage_key=key,
            public_url=None,
            mime_type=mime_type,
            **image_values,
        )
        if image.is_cover:
            await self.session.execute(
                update(RoomTypeImage)
                .where(
                    RoomTypeImage.workspace_id == workspace_id,
                    RoomTypeImage.room_type_id == room_type_id,
                )
                .values(is_cover=False)
            )
        self.session.add(image)
        await self.storage.save(key=key, data=data)
        try:
            self._audit(
                workspace_id,
                "ROOM_IMAGE_ADDED",
                image.id,
                {"room_type_id": str(room_type_id), "mime_type": mime_type},
                resource_type="RoomTypeImage",
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await self.storage.delete(key=key)
            raise
        return self._image_response(image)

    async def reorder_images(
        self,
        workspace_id: uuid.UUID,
        room_type_id: uuid.UUID,
        values: list[RoomTypeImageOrderItem],
    ) -> list[RoomTypeImageResponse]:
        await self.catalog.get_room_type(workspace_id, room_type_id)
        if len({item.image_id for item in values}) != len(values) or len(
            {item.sort_order for item in values}
        ) != len(values):
            raise HotelValidationError("Image IDs and sort order must be unique")
        if sum(item.is_cover for item in values) > 1:
            raise HotelValidationError("Only one cover image is allowed")
        images = list(
            (
                await self.session.scalars(
                    select(RoomTypeImage)
                    .where(
                        RoomTypeImage.workspace_id == workspace_id,
                        RoomTypeImage.room_type_id == room_type_id,
                    )
                    .with_for_update()
                )
            ).all()
        )
        if {item.id for item in images} != {item.image_id for item in values}:
            raise HotelValidationError("Image order must include every room image")
        by_id = {item.image_id: item for item in values}
        for index, image in enumerate(images, start=1):
            image.sort_order = -index
            image.is_cover = False
        await self.session.flush()
        for image in images:
            value = by_id[image.id]
            image.sort_order = value.sort_order
            image.is_cover = value.is_cover
        self._audit(
            workspace_id,
            "ROOM_IMAGES_REORDERED",
            room_type_id,
            {"image_count": len(images)},
        )
        await self.session.commit()
        return [
            self._image_response(image)
            for image in sorted(
                images,
                key=lambda item: (not item.is_cover, item.sort_order, str(item.id)),
            )
        ]

    async def image_content(self, workspace_id, room_type_id, image_id):
        image = await self.session.scalar(
            select(RoomTypeImage).where(
                RoomTypeImage.workspace_id == workspace_id,
                RoomTypeImage.room_type_id == room_type_id,
                RoomTypeImage.id == image_id,
            )
        )
        if image is None:
            raise NotFoundError("Room image not found")
        return await self.storage.read(key=image.storage_key), image.mime_type

    @staticmethod
    def _image_response(image):
        return RoomTypeImageResponse(
            id=image.id,
            room_type_id=image.room_type_id,
            public_url=image.public_url,
            content_url=f"/api/v1/hotel/catalog/room-types/{image.room_type_id}/images/{image.id}/content",
            mime_type=image.mime_type,
            caption=image.caption,
            alt_text=image.alt_text,
            image_category=image.image_category,
            sort_order=image.sort_order,
            is_cover=image.is_cover,
        )

    def _audit(
        self,
        workspace_id,
        action,
        resource_id,
        metadata=None,
        *,
        resource_type="RoomType",
    ):
        AuditService(self.session).record(
            workspace_id=workspace_id,
            actor_user_id=current_actor_user_id(),
            actor_type=AuditActorType.USER,
            action=action,
            area=AuditArea.ROOMS,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )

    async def customer_facts(self, workspace_id, room_type_id) -> CustomerRoomFacts:
        detail = await self.detail(workspace_id, room_type_id)
        room = detail.room_type
        return CustomerRoomFacts(
            room_type_id=uuid.UUID(room["id"]),
            name=room["name"],
            short_description=room.get("short_description"),
            description=room.get("description"),
            room_size_sqm=room.get("room_size_sqm"),
            max_adults=room["max_adults"],
            max_children=room["max_children"],
            max_occupancy=room["max_occupancy"],
            smoking_policy=room["smoking_policy"],
            accessibility_available=room["accessibility_available"],
            public_highlights=room.get("public_highlights"),
            view_type=room["view_type"],
            custom_view_label=room.get("custom_view_label"),
            beds=detail.beds,
            amenities=detail.amenities,
            images=detail.images,
            physical_room_count=detail.physical_room_count,
        )


class AvailabilityCalendarService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.catalog = HotelCatalogService(session)

    async def calendar(
        self,
        workspace_id: uuid.UUID,
        property_id: uuid.UUID,
        start_date: date,
        days: int,
    ):
        if days not in {7, 14, 30}:
            raise HotelValidationError("days must be 7, 14, or 30")
        await self.catalog.get_property(workspace_id, property_id)
        end = start_date + timedelta(days=days)
        rooms = list(
            (
                await self.session.scalars(
                    select(RoomType)
                    .where(
                        RoomType.workspace_id == workspace_id,
                        RoomType.property_id == property_id,
                        RoomType.active.is_(True),
                    )
                    .order_by(RoomType.name, RoomType.id)
                )
            ).all()
        )
        inventory = list(
            (
                await self.session.scalars(
                    select(InventoryDate)
                    .where(
                        InventoryDate.workspace_id == workspace_id,
                        InventoryDate.property_id == property_id,
                        InventoryDate.inventory_date >= start_date,
                        InventoryDate.inventory_date < end,
                    )
                    .order_by(InventoryDate.room_type_id, InventoryDate.inventory_date)
                )
            ).all()
        )
        authority = await self._authority(workspace_id, property_id)
        mapped = {(item.room_type_id, item.inventory_date): item for item in inventory}
        rows = []
        for room in rooms:
            cells = []
            for offset in range(days):
                day = start_date + timedelta(days=offset)
                item = mapped.get((room.id, day))
                total = item.total_units if item else 0
                reserved = item.reserved_units if item else 0
                blocked = item.blocked_units if item else 0
                used = reserved + blocked
                ratio = (
                    (Decimal(used) / Decimal(total) * 100).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if total
                    else Decimal("0.00")
                )
                cells.append(
                    AvailabilityCalendarCell(
                        date=day,
                        total_units=total,
                        reserved_units=reserved,
                        blocked_units=blocked,
                        available_units=total - used,
                        used_units=used,
                        occupancy_ratio=ratio,
                        color_bucket=self.color_bucket(ratio),
                        authority=authority,
                        has_inventory=item is not None,
                    )
                )
            rows.append(
                AvailabilityCalendarRow(
                    room_type_id=room.id, room_type_name=room.name, cells=cells
                )
            )
        return AvailabilityCalendarResponse(
            property_id=property_id, start_date=start_date, days=days, rows=rows
        )

    async def _authority(self, workspace_id, property_id):
        value = await self.session.scalar(
            select(PMSConnection.inventory_authority)
            .join(
                PMSExternalMapping,
                (PMSExternalMapping.connection_id == PMSConnection.id)
                & (PMSExternalMapping.workspace_id == PMSConnection.workspace_id),
            )
            .where(
                PMSConnection.workspace_id == workspace_id,
                PMSConnection.active.is_(True),
                PMSExternalMapping.entity_type == PMSEntityType.PROPERTY.value,
                PMSExternalMapping.local_entity_id == property_id,
            )
            .order_by(PMSConnection.created_at.desc())
            .limit(1)
        )
        return value or "LOCAL"

    @staticmethod
    def color_bucket(ratio: Decimal) -> str:
        if ratio < 40:
            return "GREEN"
        if ratio < 70:
            return "YELLOW"
        if ratio < 90:
            return "ORANGE"
        return "RED"
