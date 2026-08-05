import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope, KnowledgeDocumentDTO, ListParams, Paginated } from "@/types/api";

export const knowledgeService = {
  async list(params: ListParams = {}): Promise<Paginated<KnowledgeDocumentDTO>> {
    const response = await api.get<ApiEnvelope<Paginated<KnowledgeDocumentDTO>>>("/knowledge", { params });
    return unwrap(response);
  },
  async upload(file: File, onProgress: (value: number) => void) {
    const body = new FormData();
    body.append("file", file);
    const response = await api.post<ApiEnvelope<KnowledgeDocumentDTO>>("/knowledge/upload", body, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (event) => {
        if (event.total) onProgress(Math.round((event.loaded / event.total) * 100));
      },
    });
    return unwrap(response);
  },
  async remove(documentId: string): Promise<void> {
    await api.delete(`/knowledge/${encodeURIComponent(documentId)}`);
  },
};
