"""Read-only PMS connection management, import, and reconciliation."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.integrations.pms.contracts import (
    ImportedInventoryDay,
    ImportedRatePlan,
)
from app.integrations.pms.errors import PMSProviderError
from app.integrations.pms.registry import (
    PMSProviderRegistry,
    get_pms_provider_registry,
)
from app.integrations.pms.security import (
    EncryptedPMSCredentials,
    PMSCredentialCipher,
    PMSCredentialSecurityError,
)
from app.models.audit import AuditActorType, AuditArea, AuditResult
from app.models.hotel import InventoryDate, Property, RatePlan, RoomType
from app.models.pms import (
    PMSConnection,
    PMSConnectionStatus,
    PMSEntityType,
    PMSExternalMapping,
    PMSInventoryAuthority,
    PMSIssueStatus,
    PMSReconciliationIssue,
    PMSSyncMode,
    PMSSyncRun,
    PMSSyncRunStatus,
)
from app.models.stay import HotelRoom
from app.schemas.pms import PMSConnectionCreate, PMSConnectionPatch, PMSMappingCreate
from app.services.audit import AuditService, current_actor_user_id

logger = logging.getLogger(__name__)

MAX_SYNC_PAGES = 100
MAX_SYNC_ENTITIES = 5000
PROVIDER_ATTEMPTS = 3


class PMSValidationError(AppError):
    status_code = 422
    code = "PMS_VALIDATION_ERROR"
    message = "PMS configuration or mapping is invalid"


class PMSSyncConflictError(AppError):
    status_code = 409
    code = "PMS_SYNC_CONFLICT"
    message = "A PMS sync is already running for this connection"


class PMSProviderRequestError(AppError):
    status_code = 502
    code = "PMS_UNAVAILABLE"
    message = "PMS provider is temporarily unavailable"


class PMSService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        registry: PMSProviderRegistry | None = None,
        cipher: PMSCredentialCipher | None = None,
    ) -> None:
        self.session = session
        self.registry = registry or get_pms_provider_registry()
        self.cipher = cipher or PMSCredentialCipher()

    async def create_connection(
        self, workspace_id: uuid.UUID, payload: PMSConnectionCreate
    ) -> PMSConnection:
        if payload.sync_mode is not PMSSyncMode.READ_ONLY_IMPORT:
            raise PMSValidationError("Only READ_ONLY_IMPORT is supported")
        try:
            self.registry.create(payload.provider, payload.credentials)
        except ValueError as exc:
            raise PMSValidationError("Unknown PMS provider") from exc
        connection = PMSConnection(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            provider=payload.provider.lower(),
            name=payload.name,
            active=True,
            status=PMSConnectionStatus.PENDING.value,
            sync_mode=payload.sync_mode.value,
            inventory_authority=payload.inventory_authority.value,
            credential_ciphertext=b"",
            credential_nonce=b"",
            credential_key_version="",
            external_account_id=payload.external_account_id,
            sync_cursor={},
        )
        encrypted = self.cipher.encrypt(
            payload.credentials,
            workspace_id=workspace_id,
            connection_id=connection.id,
            provider=connection.provider,
        )
        connection.credential_ciphertext = encrypted.ciphertext
        connection.credential_nonce = encrypted.nonce
        connection.credential_key_version = encrypted.key_version
        self.session.add(connection)
        AuditService(self.session).record(
            workspace_id=workspace_id,
            actor_user_id=current_actor_user_id(),
            actor_type=AuditActorType.USER,
            action="PMS_CONNECTION_CREATED",
            area=AuditArea.PMS,
            resource_type="PMSConnection",
            resource_id=connection.id,
            metadata={"provider": connection.provider},
        )
        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    async def list_connections(self, workspace_id: uuid.UUID) -> list[PMSConnection]:
        return list(
            await self.session.scalars(
                select(PMSConnection)
                .where(PMSConnection.workspace_id == workspace_id)
                .order_by(PMSConnection.created_at, PMSConnection.id)
            )
        )

    async def get_connection(
        self, workspace_id: uuid.UUID, connection_id: uuid.UUID
    ) -> PMSConnection:
        item = await self.session.scalar(
            select(PMSConnection).where(
                PMSConnection.workspace_id == workspace_id,
                PMSConnection.id == connection_id,
            )
        )
        if item is None:
            raise NotFoundError("PMS connection not found")
        return item

    async def update_connection(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        payload: PMSConnectionPatch,
    ) -> PMSConnection:
        connection = await self.get_connection(workspace_id, connection_id)
        values = payload.model_dump(exclude_unset=True)
        credentials = values.pop("credentials", None)
        for key, value in values.items():
            setattr(connection, key, value.value if hasattr(value, "value") else value)
        if credentials is not None:
            encrypted = self.cipher.encrypt(
                credentials,
                workspace_id=workspace_id,
                connection_id=connection.id,
                provider=connection.provider,
            )
            connection.credential_ciphertext = encrypted.ciphertext
            connection.credential_nonce = encrypted.nonce
            connection.credential_key_version = encrypted.key_version
        AuditService(self.session).record(
            workspace_id=workspace_id,
            actor_user_id=current_actor_user_id(),
            actor_type=AuditActorType.USER,
            action="PMS_CONNECTION_UPDATED",
            area=AuditArea.PMS,
            resource_type="PMSConnection",
            resource_id=connection.id,
            metadata={
                "changed_fields": sorted(
                    key for key in payload.model_fields_set if key != "credentials"
                ),
                "credentials_rotated": credentials is not None,
            },
        )
        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    def credentials(self, connection: PMSConnection) -> dict[str, str]:
        try:
            return self.cipher.decrypt(
                EncryptedPMSCredentials(
                    connection.credential_ciphertext,
                    connection.credential_nonce,
                    connection.credential_key_version,
                ),
                workspace_id=connection.workspace_id,
                connection_id=connection.id,
                provider=connection.provider,
            )
        except PMSCredentialSecurityError as exc:
            raise PMSProviderRequestError("PMS credentials are unavailable") from exc

    def provider(self, connection: PMSConnection):
        try:
            return self.registry.create(
                connection.provider, self.credentials(connection)
            )
        except ValueError as exc:
            raise PMSValidationError("Unknown PMS provider") from exc

    async def test_connection(
        self, workspace_id: uuid.UUID, connection_id: uuid.UUID
    ) -> PMSConnection:
        connection = await self.get_connection(workspace_id, connection_id)
        try:
            provider = self.provider(connection)
            result = await provider.test_connection()
        except (PMSProviderError, PMSProviderRequestError) as exc:
            connection.status = PMSConnectionStatus.ERROR.value
            connection.last_error_code = exc.code
            await self.session.commit()
            if isinstance(exc, PMSProviderError):
                raise self._provider_error(exc) from exc
            raise
        connection.status = PMSConnectionStatus.CONNECTED.value
        connection.last_error_code = None
        if result.account_id:
            connection.external_account_id = result.account_id
        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    async def create_mapping(
        self, workspace_id: uuid.UUID, payload: PMSMappingCreate
    ) -> PMSExternalMapping:
        await self.get_connection(workspace_id, payload.connection_id)
        await self._validate_local_target(
            workspace_id, payload.entity_type, payload.local_entity_id
        )
        mapping = PMSExternalMapping(
            workspace_id=workspace_id,
            **payload.model_dump(mode="python"),
        )
        self.session.add(mapping)
        try:
            await self.session.flush()
            AuditService(self.session).record(
                workspace_id=workspace_id,
                actor_user_id=current_actor_user_id(),
                actor_type=AuditActorType.USER,
                action="PMS_MAPPING_CHANGED",
                area=AuditArea.PMS,
                resource_type="PMSExternalMapping",
                resource_id=mapping.id,
                metadata={"entity_type": mapping.entity_type},
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise PMSSyncConflictError(
                "External PMS identity is already mapped"
            ) from exc
        await self.session.refresh(mapping)
        return mapping

    async def _validate_local_target(
        self,
        workspace_id: uuid.UUID,
        entity_type: PMSEntityType,
        local_entity_id: uuid.UUID,
    ) -> None:
        models = {
            PMSEntityType.PROPERTY: Property,
            PMSEntityType.ROOM_TYPE: RoomType,
            PMSEntityType.ROOM: HotelRoom,
            PMSEntityType.RATE_PLAN: RatePlan,
        }
        model = models.get(entity_type)
        if model is None:
            raise PMSValidationError("Reservation mapping is deferred in Sprint 10.8")
        exists = await self.session.scalar(
            select(model.id).where(
                model.id == local_entity_id,
                model.workspace_id == workspace_id,
            )
        )
        if exists is None:
            raise PMSValidationError("Mapped local entity does not exist in Workspace")

    async def list_mappings(
        self,
        workspace_id: uuid.UUID,
        *,
        connection_id: uuid.UUID | None = None,
        entity_type: PMSEntityType | None = None,
    ) -> list[PMSExternalMapping]:
        query = select(PMSExternalMapping).where(
            PMSExternalMapping.workspace_id == workspace_id
        )
        if connection_id:
            query = query.where(PMSExternalMapping.connection_id == connection_id)
        if entity_type:
            query = query.where(PMSExternalMapping.entity_type == entity_type.value)
        return list(
            await self.session.scalars(
                query.order_by(
                    PMSExternalMapping.entity_type,
                    PMSExternalMapping.external_id,
                )
            )
        )

    async def list_runs(
        self, workspace_id: uuid.UUID, *, connection_id: uuid.UUID | None = None
    ) -> list[PMSSyncRun]:
        query = select(PMSSyncRun).where(PMSSyncRun.workspace_id == workspace_id)
        if connection_id:
            query = query.where(PMSSyncRun.connection_id == connection_id)
        return list(
            await self.session.scalars(
                query.order_by(PMSSyncRun.created_at.desc()).limit(100)
            )
        )

    async def get_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> PMSSyncRun:
        item = await self.session.scalar(
            select(PMSSyncRun).where(
                PMSSyncRun.workspace_id == workspace_id,
                PMSSyncRun.id == run_id,
            )
        )
        if item is None:
            raise NotFoundError("PMS sync run not found")
        return item

    async def list_issues(
        self,
        workspace_id: uuid.UUID,
        *,
        connection_id: uuid.UUID | None = None,
        status: PMSIssueStatus | None = None,
    ) -> list[PMSReconciliationIssue]:
        query = select(PMSReconciliationIssue).where(
            PMSReconciliationIssue.workspace_id == workspace_id
        )
        if connection_id:
            query = query.where(PMSReconciliationIssue.connection_id == connection_id)
        if status:
            query = query.where(PMSReconciliationIssue.status == status.value)
        return list(
            await self.session.scalars(
                query.order_by(PMSReconciliationIssue.created_at.desc()).limit(500)
            )
        )

    async def sync(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        initiated_by_user_id: uuid.UUID | None,
    ) -> PMSSyncRun:
        connection = await self.get_connection(workspace_id, connection_id)
        if not connection.active:
            raise PMSValidationError("PMS connection is inactive")
        locked_connection_id = connection.id
        run = PMSSyncRun(
            workspace_id=workspace_id,
            connection_id=locked_connection_id,
            status=PMSSyncRunStatus.PENDING.value,
            cursor_before=dict(connection.sync_cursor or {}),
            initiated_by_user_id=initiated_by_user_id,
        )
        self.session.add(run)
        try:
            await self.session.flush()
            AuditService(self.session).record(
                workspace_id=workspace_id,
                actor_user_id=initiated_by_user_id,
                actor_type=(
                    AuditActorType.USER
                    if initiated_by_user_id
                    else AuditActorType.SYSTEM
                ),
                action="PMS_SYNC_STARTED",
                area=AuditArea.PMS,
                resource_type="PMSSyncRun",
                resource_id=run.id,
                metadata={"connection_id": str(connection_id)},
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.session.scalar(
                select(PMSSyncRun).where(
                    PMSSyncRun.connection_id == locked_connection_id,
                    PMSSyncRun.status.in_(
                        [
                            PMSSyncRunStatus.PENDING.value,
                            PMSSyncRunStatus.RUNNING.value,
                        ]
                    ),
                )
            )
            raise PMSSyncConflictError(
                details={"sync_run_id": str(existing.id) if existing else None}
            ) from exc

        run.status = PMSSyncRunStatus.RUNNING.value
        run.started_at = datetime.now(UTC)
        await self.session.commit()
        candidate_cursor = dict(connection.sync_cursor or {})
        try:
            provider = self.provider(connection)
            operations: tuple[tuple[str, bool, Callable[..., Awaitable[Any]]], ...] = (
                (
                    "properties",
                    provider.capabilities.properties,
                    provider.list_properties,
                ),
                (
                    "room_types",
                    provider.capabilities.room_types,
                    provider.fetch_room_types,
                ),
                ("rooms", provider.capabilities.physical_rooms, provider.fetch_rooms),
                (
                    "rate_plans",
                    provider.capabilities.rate_plans,
                    provider.fetch_rate_plans,
                ),
                (
                    "inventory",
                    provider.capabilities.inventory,
                    provider.fetch_inventory,
                ),
            )
            for key, enabled, fetch in operations:
                if enabled:
                    candidate_cursor[key] = await self._sync_stream(
                        connection, run, key, fetch, candidate_cursor.get(key)
                    )
            run.cursor_after = candidate_cursor
            run.completed_at = datetime.now(UTC)
            if run.conflict_count or run.warning_count:
                run.status = PMSSyncRunStatus.PARTIAL.value
            else:
                run.status = PMSSyncRunStatus.SUCCEEDED.value
                connection.sync_cursor = candidate_cursor
                connection.last_successful_sync_at = run.completed_at
                connection.last_error_code = None
            AuditService(self.session).record(
                workspace_id=workspace_id,
                actor_user_id=initiated_by_user_id,
                actor_type=(
                    AuditActorType.USER
                    if initiated_by_user_id
                    else AuditActorType.SYSTEM
                ),
                action="PMS_SYNC_COMPLETED",
                area=AuditArea.PMS,
                resource_type="PMSSyncRun",
                resource_id=run.id,
                result=AuditResult.SUCCESS,
                metadata={
                    "status": run.status,
                    "entities_fetched": run.entities_fetched,
                    "entities_applied": run.entities_applied,
                    "conflict_count": run.conflict_count,
                },
            )
            await self.session.commit()
            await self.session.refresh(run)
            logger.info(
                "pms_sync_completed",
                extra={
                    "workspace_id": str(workspace_id),
                    "connection_id": str(connection.id),
                    "sync_run_id": str(run.id),
                    "provider": connection.provider,
                    "status": run.status,
                    "entities_fetched": run.entities_fetched,
                    "entities_applied": run.entities_applied,
                    "conflicts": run.conflict_count,
                },
            )
            return run
        except PMSProviderError as exc:
            await self.session.rollback()
            run = await self.session.get(PMSSyncRun, run.id)
            connection = await self.session.get(PMSConnection, connection.id)
            assert run is not None and connection is not None
            run.status = PMSSyncRunStatus.FAILED.value
            run.completed_at = datetime.now(UTC)
            run.error_code = exc.code
            connection.last_failed_sync_at = run.completed_at
            connection.last_error_code = exc.code
            AuditService(self.session).record(
                workspace_id=workspace_id,
                actor_user_id=initiated_by_user_id,
                actor_type=AuditActorType.SYSTEM,
                action="PMS_SYNC_COMPLETED",
                area=AuditArea.PMS,
                resource_type="PMSSyncRun",
                resource_id=run.id,
                result=AuditResult.FAILED,
                metadata={"error_code": exc.code},
            )
            await self.session.commit()
            raise self._provider_error(exc) from exc
        except Exception:
            await self.session.rollback()
            run = await self.session.get(PMSSyncRun, run.id)
            connection = await self.session.get(PMSConnection, connection.id)
            if run is not None and connection is not None:
                run.status = PMSSyncRunStatus.FAILED.value
                run.completed_at = datetime.now(UTC)
                run.error_code = "PMS_SYNC_FAILED"
                connection.last_failed_sync_at = run.completed_at
                connection.last_error_code = run.error_code
                await self.session.commit()
            raise

    async def _sync_stream(self, connection, run, key, fetch, cursor):
        seen: set[str | None] = set()
        current = cursor
        for _ in range(MAX_SYNC_PAGES):
            if current in seen:
                raise PMSProviderError("PMS cursor cycle detected")
            seen.add(current)
            page = await self._call_provider(fetch, current)
            run.entities_fetched += len(page.items)
            if run.entities_fetched > MAX_SYNC_ENTITIES:
                raise PMSProviderError("PMS import exceeds bounded entity limit")
            for item in page.items:
                await self._apply_item(connection, run, key, item)
            await self.session.commit()
            if page.next_cursor is None:
                return current
            current = page.next_cursor
        raise PMSProviderError("PMS import exceeds bounded page limit")

    async def _call_provider(self, fetch, cursor):
        last: PMSProviderError | None = None
        for _ in range(PROVIDER_ATTEMPTS):
            try:
                return await fetch(cursor)
            except PMSProviderError as exc:
                last = exc
                if not exc.retryable:
                    raise
        assert last is not None
        raise last

    async def _apply_item(self, connection, run, key, item) -> None:
        handlers = {
            "properties": (PMSEntityType.PROPERTY, "UNMAPPED_PROPERTY"),
            "room_types": (PMSEntityType.ROOM_TYPE, "UNMAPPED_ROOM_TYPE"),
            "rooms": (PMSEntityType.ROOM, "UNMAPPED_ROOM"),
            "rate_plans": (PMSEntityType.RATE_PLAN, "UNMAPPED_RATE_PLAN"),
        }
        if key == "inventory":
            await self._apply_inventory(connection, run, item)
            return
        entity_type, issue_type = handlers[key]
        mapping = await self._mapping(connection.id, entity_type, item.external_id)
        if mapping is None:
            await self._issue(
                connection,
                run,
                entity_type,
                item.external_id,
                issue_type,
                "WARNING",
                {
                    "name": getattr(item, "name", None),
                    "code": getattr(item, "code", None),
                },
            )
            return
        mapping.external_version = item.external_version
        mapping.external_updated_at = item.external_updated_at
        if key == "rate_plans":
            await self._reconcile_rate_plan(connection, run, mapping, item)

    async def _reconcile_rate_plan(
        self,
        connection: PMSConnection,
        run: PMSSyncRun,
        mapping: PMSExternalMapping,
        item: ImportedRatePlan,
    ) -> None:
        local = await self.session.scalar(
            select(RatePlan).where(
                RatePlan.workspace_id == connection.workspace_id,
                RatePlan.id == mapping.local_entity_id,
            )
        )
        if local is None:
            raise PMSValidationError("Mapped RatePlan no longer exists")
        if item.base_price is not None and Decimal(local.base_price) != item.base_price:
            await self._issue(
                connection,
                run,
                PMSEntityType.RATE_PLAN,
                item.external_id,
                "RATE_DIFFERENCE",
                "WARNING",
                {
                    "external_price": str(item.base_price),
                    "local_price": str(local.base_price),
                    "authority": "LOCAL_RECONCILIATION_ONLY",
                },
                local.id,
            )

    async def _apply_inventory(
        self,
        connection: PMSConnection,
        run: PMSSyncRun,
        item: ImportedInventoryDay,
    ) -> None:
        property_mapping = await self._mapping(
            connection.id, PMSEntityType.PROPERTY, item.property_external_id
        )
        room_mapping = await self._mapping(
            connection.id, PMSEntityType.ROOM_TYPE, item.room_type_external_id
        )
        external_key = (
            f"{item.property_external_id}:{item.room_type_external_id}:"
            f"{item.inventory_date.isoformat()}"
        )
        if property_mapping is None or room_mapping is None:
            await self._issue(
                connection,
                run,
                PMSEntityType.ROOM_TYPE,
                external_key,
                "UNMAPPED_INVENTORY",
                "WARNING",
                {
                    "property_mapped": property_mapping is not None,
                    "room_type_mapped": room_mapping is not None,
                },
            )
            return
        inventory = await self.session.scalar(
            select(InventoryDate)
            .where(
                InventoryDate.workspace_id == connection.workspace_id,
                InventoryDate.property_id == property_mapping.local_entity_id,
                InventoryDate.room_type_id == room_mapping.local_entity_id,
                InventoryDate.inventory_date == item.inventory_date,
            )
            .with_for_update()
        )
        if inventory is None:
            if connection.inventory_authority == PMSInventoryAuthority.LOCAL.value:
                await self._issue(
                    connection,
                    run,
                    PMSEntityType.ROOM_TYPE,
                    external_key,
                    "MISSING_LOCAL_INVENTORY",
                    "WARNING",
                    {"external_total_units": item.total_units},
                    room_mapping.local_entity_id,
                )
                return
            inventory = InventoryDate(
                workspace_id=connection.workspace_id,
                property_id=property_mapping.local_entity_id,
                room_type_id=room_mapping.local_entity_id,
                inventory_date=item.inventory_date,
                total_units=item.total_units,
                reserved_units=0,
                blocked_units=0,
            )
            self.session.add(inventory)
            run.entities_applied += 1
            return
        committed = inventory.reserved_units + inventory.blocked_units
        if item.total_units < committed:
            await self._issue(
                connection,
                run,
                PMSEntityType.ROOM_TYPE,
                external_key,
                "INVENTORY_BELOW_LOCAL_RESERVED",
                "ERROR",
                {
                    "external_total_units": item.total_units,
                    "local_reserved_units": inventory.reserved_units,
                    "local_blocked_units": inventory.blocked_units,
                    "local_total_units": inventory.total_units,
                },
                inventory.room_type_id,
            )
            return
        if inventory.total_units == item.total_units:
            await self._resolve_inventory_issues(connection.id, external_key)
            return
        if connection.inventory_authority == PMSInventoryAuthority.LOCAL.value:
            await self._issue(
                connection,
                run,
                PMSEntityType.ROOM_TYPE,
                external_key,
                "INVENTORY_DIFFERENCE",
                "WARNING",
                {
                    "external_total_units": item.total_units,
                    "local_total_units": inventory.total_units,
                    "authority": "LOCAL",
                },
                inventory.room_type_id,
            )
            return
        inventory.total_units = item.total_units
        run.entities_applied += 1
        await self._resolve_inventory_issues(connection.id, external_key)

    async def _mapping(self, connection_id, entity_type, external_id):
        return await self.session.scalar(
            select(PMSExternalMapping).where(
                PMSExternalMapping.connection_id == connection_id,
                PMSExternalMapping.entity_type == entity_type.value,
                PMSExternalMapping.external_id == external_id,
            )
        )

    async def _issue(
        self,
        connection,
        run,
        entity_type,
        external_id,
        issue_type,
        severity,
        details,
        local_entity_id=None,
    ):
        issue = await self.session.scalar(
            select(PMSReconciliationIssue).where(
                PMSReconciliationIssue.connection_id == connection.id,
                PMSReconciliationIssue.entity_type == entity_type.value,
                PMSReconciliationIssue.external_id == external_id,
                PMSReconciliationIssue.issue_type == issue_type,
                PMSReconciliationIssue.status == PMSIssueStatus.OPEN.value,
            )
        )
        if issue is None:
            issue = PMSReconciliationIssue(
                workspace_id=connection.workspace_id,
                connection_id=connection.id,
                sync_run_id=run.id,
                entity_type=entity_type.value,
                external_id=external_id,
                local_entity_id=local_entity_id,
                issue_type=issue_type,
                severity=severity,
                status=PMSIssueStatus.OPEN.value,
                details=details,
            )
            self.session.add(issue)
        else:
            issue.sync_run_id = run.id
            issue.local_entity_id = local_entity_id
            issue.severity = severity
            issue.details = details
        if severity == "ERROR":
            run.conflict_count += 1
        else:
            run.warning_count += 1

    async def _resolve_inventory_issues(self, connection_id, external_id):
        issues = list(
            await self.session.scalars(
                select(PMSReconciliationIssue).where(
                    PMSReconciliationIssue.connection_id == connection_id,
                    PMSReconciliationIssue.external_id == external_id,
                    PMSReconciliationIssue.status == PMSIssueStatus.OPEN.value,
                    PMSReconciliationIssue.issue_type.in_(
                        [
                            "INVENTORY_BELOW_LOCAL_RESERVED",
                            "INVENTORY_DIFFERENCE",
                            "MISSING_LOCAL_INVENTORY",
                        ]
                    ),
                )
            )
        )
        now = datetime.now(UTC)
        for issue in issues:
            issue.status = PMSIssueStatus.RESOLVED.value
            issue.resolved_at = now

    @staticmethod
    def _provider_error(exc: PMSProviderError) -> PMSProviderRequestError:
        error = PMSProviderRequestError()
        error.code = exc.code
        return error
