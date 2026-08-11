"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { actionService, type ActionFilters } from "@/services/action/action.service";

export function useActions(filters: ActionFilters = {}) { return useQuery({ queryKey: ["actions", filters], queryFn: () => actionService.list(filters) }); }
export function useActionDefinitions() { return useQuery({ queryKey: ["actions", "definitions"], queryFn: actionService.definitions }); }
export function useActionOperations() {
  const client = useQueryClient(); const refresh = () => client.invalidateQueries({ queryKey: ["actions"] });
  return {
    assign: useMutation({ mutationFn: ({ id, userId }: { id: string; userId: string }) => actionService.assign(id, userId), onSuccess: refresh }),
    transition: useMutation({ mutationFn: ({ id, transition }: { id: string; transition: "start" | "complete" | "fail" | "cancel" }) => actionService.transition(id, transition), onSuccess: refresh }),
  };
}

export function useActionDefinitionOperations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["actions", "definitions"] });
  return {
    create: useMutation({ mutationFn: actionService.createDefinition, onSuccess: refresh }),
    update: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof actionService.updateDefinition>[1] }) => actionService.updateDefinition(id, payload), onSuccess: refresh }),
  };
}
