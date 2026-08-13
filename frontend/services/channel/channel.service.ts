import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type {
  ChannelConnectionDTO,
  FacebookConnectionInput,
  LineConnectionInput,
} from "@/types/channel";

export const channelService = {
  async list(): Promise<ChannelConnectionDTO[]> {
    return unwrap(
      await api.get<ApiEnvelope<ChannelConnectionDTO[]>>("/channels"),
    );
  },
  async connectWebChat() {
    return unwrap(
      await api.post<ApiEnvelope<ChannelConnectionDTO>>(
        "/channels/webchat",
      ),
    );
  },
  async connectLine(input: LineConnectionInput) {
    return unwrap(
      await api.post<ApiEnvelope<ChannelConnectionDTO>>(
        "/channels/line",
        input,
      ),
    );
  },
  async connectFacebook(input: FacebookConnectionInput) {
    return unwrap(
      await api.post<ApiEnvelope<ChannelConnectionDTO>>(
        "/channels/facebook",
        input,
      ),
    );
  },
  async disconnect(id: string) {
    return unwrap(
      await api.delete<ApiEnvelope<ChannelConnectionDTO>>(
        `/channels/connections/${encodeURIComponent(id)}`,
      ),
    );
  },
};
