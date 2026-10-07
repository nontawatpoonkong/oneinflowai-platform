import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { CRMCustomerListItem, CRMListParams, CRMNote, CRMPaginated, CRMPreference, CRMTag, CRMTimelineEvent, Customer360, PreferenceKey, PreferenceSource } from "@/types/crm";

export const crmService = {
  async customers(params:CRMListParams={}):Promise<CRMPaginated<CRMCustomerListItem>> { return unwrap(await api.get<ApiEnvelope<CRMPaginated<CRMCustomerListItem>>>("/crm/customers",{params})); },
  async customer(id:string):Promise<Customer360> { return unwrap(await api.get<ApiEnvelope<Customer360>>(`/crm/customers/${id}`)); },
  async timeline(id:string,page=1):Promise<CRMPaginated<CRMTimelineEvent>> { return unwrap(await api.get<ApiEnvelope<CRMPaginated<CRMTimelineEvent>>>(`/crm/customers/${id}/timeline`,{params:{page,page_size:50}})); },
  async tags():Promise<CRMTag[]> { return unwrap(await api.get<ApiEnvelope<CRMTag[]>>("/crm/tags")); },
  async createTag(name:string):Promise<CRMTag> { return unwrap(await api.post<ApiEnvelope<CRMTag>>("/crm/tags",{name})); },
  async assignTag(customerId:string,tagId:string):Promise<CRMTag> { return unwrap(await api.post<ApiEnvelope<CRMTag>>(`/crm/customers/${customerId}/tags/${tagId}`)); },
  async removeTag(customerId:string,tagId:string):Promise<{id:string}> { return unwrap(await api.delete<ApiEnvelope<{id:string}>>(`/crm/customers/${customerId}/tags/${tagId}`)); },
  async addNote(customerId:string,body:string):Promise<CRMNote> { return unwrap(await api.post<ApiEnvelope<CRMNote>>(`/crm/customers/${customerId}/notes`,{body})); },
  async setPreference(customerId:string,payload:{key:PreferenceKey;value:string;source:PreferenceSource}):Promise<CRMPreference> { return unwrap(await api.post<ApiEnvelope<CRMPreference>>(`/crm/customers/${customerId}/preferences`,payload)); },
};
