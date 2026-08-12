# OneInFlow public product knowledge

Source: README.md

OneInFlow is a multi-tenant AI customer conversation platform. It unifies
WebChat, LINE Official Account, and Facebook Page Messenger text conversations.
AI answers are grounded in a workspace knowledge base, and staff can take over
conversations through Human Handoff.

OneInFlow คือแพลตฟอร์ม AI สำหรับรวมแชทลูกค้าหลายช่องทาง โดย AI ตอบจาก
คลังความรู้ของ Workspace และเจ้าหน้าที่สามารถรับช่วงตอบผ่าน Human Handoff ได้

Source: docs/01_PRODUCT_SPEC.md

The MVP operational areas are Overview, Inbox, Actions, Knowledge, Payments,
Channels, Notifications, and Workspace settings. Workspaces isolate customer,
conversation, knowledge, action, payment, and channel data from other tenants.

Source: docs/10_CHANNEL_INTEGRATIONS.md

Implemented external channels are LINE OA text messaging and Facebook Page
Messenger text messaging. Instagram, Facebook comments, Lead Ads, broadcast,
media messages, read receipts, and automatic outbound retry are planned rather
than implemented.

ช่องทางที่รองรับแล้วคือ WebChat, LINE OA และ Facebook Page Messenger แบบข้อความ
ส่วน Instagram, คอมเมนต์ Facebook, Lead Ads และ broadcast ยังเป็นแผนในอนาคต

Source: docs/11_MVP_OPERATIONS.md

Action Types define the structured information that AI collects. The server
validates collected fields, asks the customer for confirmation, and then creates
an Action Request in the operational queue. Knowledge documents are uploaded,
extracted, chunked, indexed, and used for grounded answers with citations.
Payment records represent customer payments and slip verification; they are not
the SaaS subscription billing system.

Source: docs/06_ROADMAP.md

OneInFlow is being delivered incrementally. Public product answers must describe
only implemented capabilities as available and identify roadmap capabilities as
planned.
