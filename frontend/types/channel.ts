export type ChannelProvider = "web" | "line" | "facebook";
export type ChannelConnectionStatus =
  | "DISCONNECTED"
  | "PENDING"
  | "CONNECTED"
  | "ERROR";

export interface ChannelConnectionDTO {
  id: string;
  workspace_id: string;
  provider: ChannelProvider;
  display_name: string;
  external_account_id: string;
  external_account_name: string | null;
  status: ChannelConnectionStatus;
  connected_at: string | null;
  last_verified_at: string | null;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface LineConnectionInput {
  display_name: string;
  external_account_id: string;
  channel_access_token: string;
  channel_secret: string;
}

export interface FacebookConnectionInput {
  display_name: string;
  external_account_id: string;
  page_access_token: string;
  app_secret: string;
  verify_token: string;
}
