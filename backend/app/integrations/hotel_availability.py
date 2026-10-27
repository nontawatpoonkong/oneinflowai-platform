"""Typed read-only tool boundary for authoritative Hotel availability."""

import uuid

from app.schemas.hotel import AvailabilitySearchRequest, AvailabilitySearchResponse
from app.services.hotel import HotelAvailabilityService


class SearchAvailabilityTool:
    name = "search_availability"
    description = "Search trusted structured Hotel inventory and rate-plan data."
    input_model = AvailabilitySearchRequest
    output_model = AvailabilitySearchResponse
    read_only = True

    def __init__(self, session) -> None:
        self.service = HotelAvailabilityService(session)

    async def execute(
        self, workspace_id: uuid.UUID, request: AvailabilitySearchRequest
    ) -> AvailabilitySearchResponse:
        return await self.service.search(workspace_id, request)
