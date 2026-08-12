export interface DemoChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: DemoCitation[];
}

export interface DemoCitation {
  label: string;
  source: string;
}

export interface DemoChatResponse {
  answer: string;
  citations: DemoCitation[];
}
