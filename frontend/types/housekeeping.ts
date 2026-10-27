import type { RoomOperationalStatus,RoomReadinessStatus,Paged } from "@/types/stay";
export type HousekeepingTaskStatus="PENDING"|"IN_PROGRESS"|"COMPLETED"|"CANCELLED";
export type HousekeepingPriority="LOW"|"NORMAL"|"HIGH";
export interface HousekeepingEvent{id:string;event_type:string;actor_user_id:string|null;event_metadata:Record<string,unknown>;sequence:number;created_at:string;}
export interface HousekeepingTask{id:string;workspace_id:string;property_id:string;property_name:string;room_id:string;room_code:string;room_type_name:string;stay_id:string|null;status:HousekeepingTaskStatus;priority:HousekeepingPriority;assigned_to_user_id:string|null;source:string;operational_status:RoomOperationalStatus;readiness_status:RoomReadinessStatus;checkout_at:string|null;started_at:string|null;completed_at:string|null;created_at:string;events:HousekeepingEvent[];}
export type HousekeepingTaskPage=Paged<HousekeepingTask>;
export interface HousekeepingTaskParams { property_id?:string; room_id?:string; status?:HousekeepingTaskStatus; assignee_id?:string; priority?:HousekeepingPriority; readiness_status?:RoomReadinessStatus; page?:number; page_size?:number; }
export interface ReadinessOverrideResult { room_id:string; operational_status:RoomOperationalStatus; readiness_status:RoomReadinessStatus; event:{id:string;workspace_id:string;property_id:string;room_id:string;actor_user_id:string|null;previous_readiness:string;new_readiness:string;reason:string;sequence:number;created_at:string}; }
