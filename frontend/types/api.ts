/** Types mirroring the FastAPI backend response contracts. */

export interface ApiEnvelope<T> {
  success: boolean;
  message: string;
  data: T;
  error: { code: string; details?: unknown } | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface UserDTO {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceDTO {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

export interface TokenDTO {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterResultDTO {
  user: UserDTO;
  workspace: WorkspaceDTO;
  token: TokenDTO;
}

export type CustomerStatusDTO = "active" | "inactive";

export interface CustomerDTO {
  id: string;
  workspace_id: string;
  display_name: string;
  full_name: string | null;
  phone: string | null;
  email: string | null;
  avatar_url: string | null;
  notes: string | null;
  status: CustomerStatusDTO;
  created_at: string;
  updated_at: string;
}

export type ConversationStatusDTO = "open" | "pending" | "resolved" | "closed";
export type ConversationAiModeDTO = "AUTO" | "COPILOT" | "HUMAN";
export type ChannelDTO =
  | "web"
  | "line"
  | "facebook"
  | "instagram"
  | "whatsapp"
  | "telegram"
  | "email";

export interface ConversationDTO {
  id: string;
  workspace_id: string;
  customer_id: string;
  status: ConversationStatusDTO;
  channel: ChannelDTO;
  subject: string | null;
  assigned_user_id: string | null;
  external_conversation_id: string | null;
  last_message_at: string | null;
  ai_mode: ConversationAiModeDTO;
  created_at: string;
  updated_at: string;
}

export interface LoginPayload {
  email: string;
  password: string;
  remember?: boolean;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name?: string;
}

export interface ListParams {
  page?: number;
  page_size?: number;
  sort_by?: string;
  order?: "asc" | "desc";
  q?: string;
}
