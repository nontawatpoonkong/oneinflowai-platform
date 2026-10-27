import {api,unwrap} from "@/services/api/client";
import type {ApiEnvelope} from "@/types/api";
import type {HousekeepingTask,HousekeepingTaskPage,HousekeepingTaskParams,ReadinessOverrideResult} from "@/types/housekeeping";
export const housekeepingService={
 async tasks(params:HousekeepingTaskParams={}):Promise<HousekeepingTaskPage>{return unwrap(await api.get<ApiEnvelope<HousekeepingTaskPage>>("/hotel/housekeeping/tasks",{params}));},
 async task(id:string):Promise<HousekeepingTask>{return unwrap(await api.get<ApiEnvelope<HousekeepingTask>>(`/hotel/housekeeping/tasks/${id}`));},
 async assign(id:string,userId:string):Promise<HousekeepingTask>{return unwrap(await api.post<ApiEnvelope<HousekeepingTask>>(`/hotel/housekeeping/tasks/${id}/assign`,{assigned_to_user_id:userId}));},
 async start(id:string):Promise<HousekeepingTask>{return unwrap(await api.post<ApiEnvelope<HousekeepingTask>>(`/hotel/housekeeping/tasks/${id}/start`));},
 async complete(id:string):Promise<HousekeepingTask>{return unwrap(await api.post<ApiEnvelope<HousekeepingTask>>(`/hotel/housekeeping/tasks/${id}/complete`));},
 async cancel(id:string):Promise<HousekeepingTask>{return unwrap(await api.post<ApiEnvelope<HousekeepingTask>>(`/hotel/housekeeping/tasks/${id}/cancel`));},
 async overrideReadiness(id:string,readinessStatus:"READY"|"DIRTY",reason:string):Promise<ReadinessOverrideResult>{return unwrap(await api.post<ApiEnvelope<ReadinessOverrideResult>>(`/hotel/housekeeping/rooms/${id}/readiness-override`,{readiness_status:readinessStatus,reason}));},
};
