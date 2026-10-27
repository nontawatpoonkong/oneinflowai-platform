"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { crmService } from "@/services/crm/crm.service";
import type { CRMListParams, PreferenceKey, PreferenceSource } from "@/types/crm";

export function useCRMCustomers(params:CRMListParams){return useQuery({queryKey:["crm","customers",params],queryFn:()=>crmService.customers(params)});}
export function useCustomer360(id:string){return useQuery({queryKey:["crm","customer",id],queryFn:()=>crmService.customer(id),enabled:Boolean(id)});}
export function useCRMTimeline(id:string){return useQuery({queryKey:["crm","customer",id,"timeline"],queryFn:()=>crmService.timeline(id),enabled:Boolean(id)});}
export function useCRMTags(){return useQuery({queryKey:["crm","tags"],queryFn:crmService.tags});}
export function useCRMMutations(customerId:string){const client=useQueryClient();const refresh=async()=>{await client.invalidateQueries({queryKey:["crm","customer",customerId]});await client.invalidateQueries({queryKey:["crm","customers"]});await client.invalidateQueries({queryKey:["crm","customer",customerId,"timeline"]});};return {
  addNote:useMutation({mutationFn:(body:string)=>crmService.addNote(customerId,body),onSuccess:refresh}),
  setPreference:useMutation({mutationFn:(payload:{key:PreferenceKey;value:string;source:PreferenceSource})=>crmService.setPreference(customerId,payload),onSuccess:refresh}),
  createAndAssignTag:useMutation({mutationFn:async(name:string)=>{const tag=await crmService.createTag(name);await crmService.assignTag(customerId,tag.id);return tag;},onSuccess:async()=>{await client.invalidateQueries({queryKey:["crm","tags"]});await refresh();}}),
  removeTag:useMutation({mutationFn:(tagId:string)=>crmService.removeTag(customerId,tagId),onSuccess:refresh}),
};}
