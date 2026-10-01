# PR history

Archive of the pull requests of the original repository (`TuringCollegeSubmissions/msmacc-AE.AFA.3.5`), exported before the move to this repo. PR numbers refer to that repository. One JSON file per PR: metadata, body, comments, reviews and commit list.

| #                 | Title                                                                                             | State  | Branch                                         | Created    |
| ----------------- | ------------------------------------------------------------------------------------------------- | ------ | ---------------------------------------------- | ---------- |
| [1](pr-001.json)  | feat(api): connect to Postgres and add a users table                                              | MERGED | `feat/api-postgres-users`                      | 2026-09-15 |
| [2](pr-002.json)  | refactor(api): split app package into database and model                                          | MERGED | `refactor/split-app-package`                   | 2026-09-15 |
| [3](pr-003.json)  | Feat/UI chat shell                                                                                | MERGED | `feat/ui-chat-shell`                           | 2026-09-15 |
| [4](pr-004.json)  | feat(api): POST /messages endpoint and RAG chunking/embedding pipeline                            | MERGED | `feat/rag-pipeline-and-messages-endpoint`      | 2026-09-16 |
| [5](pr-005.json)  | feat: persist chunks in Chroma, and set the UI metadata                                           | MERGED | `feat/ui-branding-and-empty-chat`              | 2026-09-16 |
| [6](pr-006.json)  | Feat/rag pipeline and messages endpoint                                                           | MERGED | `feat/rag-pipeline-and-messages-endpoint`      | 2026-09-16 |
| [7](pr-007.json)  | fix(ui): chat messages fill the column, and roles get distinct avatars                            | MERGED | `fix/ui-chat-message-layout`                   | 2026-09-16 |
| [8](pr-008.json)  | refactor(rag): split the pipeline entrypoint out of embeddings                                    | MERGED | `refactor/rag-pipeline-entrypoint`             | 2026-09-17 |
| [9](pr-009.json)  | test(api): add the backend unit suite and CI                                                      | MERGED | `test/backend-unit-suite`                      | 2026-09-17 |
| [10](pr-010.json) | feat(chat): seed the conversation from a GET /init endpoint                                       | MERGED | `feat/chat-init-endpoint`                      | 2026-09-17 |
| [11](pr-011.json) | feat(chat): persist conversations and their messages                                              | MERGED | `feat/chat-init-endpoint`                      | 2026-09-17 |
| [12](pr-012.json) | docs: add a repo README                                                                           | MERGED | `docs/readme`                                  | 2026-09-17 |
| [13](pr-013.json) | feat(chat): send messages from the UI                                                             | MERGED | `feat/chat-send`                               | 2026-09-17 |
| [14](pr-014.json) | style(ui): give the chat a clinical visual language                                               | MERGED | `style/clinical-ui`                            | 2026-09-18 |
| [15](pr-015.json) | test(ui): add a unit suite for the API client and the composer                                    | MERGED | `test/frontend-unit-suite`                     | 2026-09-18 |
| [16](pr-016.json) | docs: bring the README up to date with the app                                                    | MERGED | `docs/readme-refresh`                          | 2026-09-18 |
| [17](pr-017.json) | feat(ui): surface failed sends, and add prettier                                                  | MERGED | `feat/surface-send-errors`                     | 2026-09-18 |
| [18](pr-018.json) | fix: call medas-api from the server, and render / per request                                     | MERGED | `fix/server-side-api-calls`                    | 2026-09-18 |
| [19](pr-019.json) | feat(api): answer the first message with the model                                                | MERGED | `refactor/schema-module-rename`                | 2026-09-18 |
| [20](pr-020.json) | feat(api): let the assistant search the record itself                                             | MERGED | `feat/record-search-tool`                      | 2026-09-18 |
| [21](pr-021.json) | docs: describe the record search as a tool call                                                   | MERGED | `docs/readme-record-search`                    | 2026-09-18 |
| [22](pr-022.json) | feat(ui): restyle the chat as Vitals, light-first                                                 | MERGED | `feat/ui-vitals-theme`                         | 2026-09-18 |
| [23](pr-023.json) | feat(ui): light the ECG trace, and go dark by default                                             | MERGED | `feat/ui-ecg-sweep`                            | 2026-09-18 |
| [24](pr-024.json) | fix(api): stop blocking the event loop, and bound what a request can cost                         | MERGED | `fix/api-async-clients-and-limits`             | 2026-09-21 |
| [25](pr-025.json) | feat: sign in with Google, and make the API trust the session                                     | CLOSED | `feat/auth-sign-in-and-conversation-ownership` | 2026-09-21 |
| [26](pr-026.json) | feat(api): give messages their own table, and stop rewriting a row to add one                     | MERGED | `feat/api-messages-table`                      | 2026-09-21 |
| [27](pr-027.json) | feat(api): answer every turn with a LangChain agent, behind one endpoint                          | MERGED | `feature/add-langchain-agent`                  | 2026-09-23 |
| [28](pr-028.json) | docs: audit the app and rewrite the README against it                                             | MERGED | `docs/readme-audit`                            | 2026-09-23 |
| [29](pr-029.json) | docs: audit the app and rewrite the README against it                                             | MERGED | `docs/readme-audit`                            | 2026-09-23 |
| [30](pr-030.json) | feat(ui): follow the conversation, and show a message before its reply                            | MERGED | `feat/ui-chat-follow-and-typing`               | 2026-09-23 |
| [31](pr-031.json) | feat(ui): require a Clerk login for the chat                                                      | MERGED | `feat/clerk-auth`                              | 2026-09-23 |
| [32](pr-032.json) | feat(api): require the Clerk session token, and scope conversations to the user                   | MERGED | `feat/api-clerk-auth`                          | 2026-09-23 |
| [33](pr-033.json) | feat(api): require the Clerk session token, and scope conversations to the user                   | MERGED | `feat/clerk-auth`                              | 2026-09-23 |
| [34](pr-034.json) | feat(api): give a new Clerk account a users row on its first sign-in                              | MERGED | `feat/api-provision-users`                     | 2026-09-23 |
| [35](pr-035.json) | refactor: simplify the Clerk auth code without changing behaviour                                 | MERGED | `refactor/simplify-clerk-auth`                 | 2026-09-23 |
| [36](pr-036.json) | feat(api): search the signed-in user's record, not a hardcoded one                                | MERGED | `feat/agent-user-record`                       | 2026-09-23 |
| [37](pr-037.json) | docs: add CLAUDE.md                                                                               | MERGED | `docs/claude-md`                               | 2026-09-24 |
| [38](pr-038.json) | Greet the patient by their Clerk first name                                                       | MERGED | `feat/greeting-first-name`                     | 2026-09-25 |
| [39](pr-039.json) | docs: bring the README back in line with the code                                                 | MERGED | `docs/readme-sync`                             | 2026-09-25 |
| [40](pr-040.json) | refactor(api): remove dead code in agent/patient.py and schema                                    | MERGED | `refactor/remove-dead-code`                    | 2026-09-25 |
| [41](pr-041.json) | feat: take the greeting name from the session token                                               | MERGED | `feat/greeting-name-from-session`              | 2026-09-28 |
| [42](pr-042.json) | refactor(api): move the /ask flow into a controller, shared helpers into utils                    | MERGED | `refactor/api-utils`                           | 2026-09-28 |
| [43](pr-043.json) | feat(api): move the retrieval index from Chroma to pgvector                                       | MERGED | `feat/pgvector-store`                          | 2026-09-28 |
| [44](pr-044.json) | feat(api): ingest patient PDFs, and an eval pipeline over a synthetic dataset                     | MERGED | `feat/pdf-ingest-eval`                         | 2026-09-28 |
| [45](pr-045.json) | feat(api): RAG metrics in the eval — faithfulness, answer relevancy, context precision and recall | MERGED | `feat/rag-eval-metrics`                        | 2026-09-28 |
| [46](pr-046.json) | feat(ui): upload a PDF from the composer                                                          | MERGED | `feat/ui-pdf-upload`                           | 2026-09-28 |
| [47](pr-047.json) | feat(api): accept PDF uploads at POST /documents                                                  | MERGED | `feat/api-documents-upload`                    | 2026-09-28 |
| [48](pr-048.json) | feat(api): embed uploaded PDFs into the patient's record                                          | MERGED | `feat/api-embed-uploads`                       | 2026-09-28 |
| [49](pr-049.json) | feat(api): verify an uploaded document is medical and the patient's                               | MERGED | `feat/api-verify-documents`                    | 2026-09-28 |
| [50](pr-050.json) | feat(api): let the agent add an attached PDF to the record                                        | MERGED | `feat/api-add-document-tool`                   | 2026-09-28 |
| [51](pr-051.json) | refactor(api): split the agent and the RAG pipeline into one-way packages                         | MERGED | `refactor/api-package-layout`                  | 2026-09-28 |
| [52](pr-052.json) | fix(dataset): remove D05, the naproxen prescription, and re-run the eval                          | MERGED | `fix/dataset-remove-d05`                       | 2026-09-28 |
| [53](pr-053.json) | feat(ui): show upload progress and a status snackbar                                              | MERGED | `feat/ui-upload-feedback`                      | 2026-09-28 |
| [54](pr-054.json) | refactor(api): trim the prompt's tool sections to search guidance                                 | MERGED | `chore/api-prompt-without-tools`               | 2026-09-28 |
| [55](pr-055.json) | feat: answer PDF uploads as turns in the conversation                                             | MERGED | `feat/api-upload-conversation-turns`           | 2026-09-28 |
| [56](pr-056.json) | fix(ui): disable the send button while a PDF uploads                                              | MERGED | `fix/ui-disable-send-while-uploading`          | 2026-09-28 |
| [57](pr-057.json) | feat: name the uploaded file in the chat, shown before the API answers                            | MERGED | `feat/upload-file-name-in-chat`                | 2026-09-28 |
| [58](pr-058.json) | feat(ui): add a sidebar listing past conversations                                                | MERGED | `feat/ui-conversation-sidebar`                 | 2026-09-28 |
| [59](pr-059.json) | feat: list the user's conversations from GET / in the sidebar                                     | MERGED | `feat/conversations-from-init`                 | 2026-09-28 |
| [60](pr-060.json) | feat(ui): open a past conversation from the sidebar                                               | MERGED | `feat/ui-open-conversation`                    | 2026-09-28 |
| [61](pr-061.json) | feat(ui): restyle the sidebar and its conversation list                                           | MERGED | `feat/ui-sidebar-style`                        | 2026-09-28 |
| [62](pr-062.json) | feat: render structured assistant replies with json-render                                        | MERGED | `feat/json-render-ui`                          | 2026-09-29 |
| [63](pr-063.json) | feat: show the reply table under the text, and table test results                                 | MERGED | `feat/json-render-ui`                          | 2026-09-29 |
| [64](pr-064.json) | fix(ui): render Clerk UserButton after hydration                                                  | MERGED | `fix/ui-userbutton-hydration`                  | 2026-09-30 |
| [65](pr-065.json) | feat(eval): score the agent's tool calling                                                        | MERGED | `feat/tool-calling-eval`                       | 2026-09-30 |
| [66](pr-066.json) | feat(agent): export the conversation as a PDF                                                     | MERGED | `feat/export-conversation-pdf`                 | 2026-09-30 |
| [67](pr-067.json) | feat: download the exported conversation as a PDF                                                 | CLOSED | `feat/export-download`                         | 2026-09-30 |
| [68](pr-068.json) | feat(rag): mask PII in PDFs before chunking                                                       | MERGED | `feat/pdf-pii-masking`                         | 2026-09-30 |
| [69](pr-069.json) | feat: let the assistant pick ui components from the message                                       | MERGED | `fix/prompt-ui-table`                          | 2026-09-30 |
| [70](pr-070.json) | feat: let the assistant pick ui components from the message                                       | MERGED | `fix/prompt-ui-table`                          | 2026-10-01 |
| [71](pr-071.json) | refactor: move exceptions and plain data types into schema.py                                     | MERGED | `fix/prompt-ui-table`                          | 2026-10-01 |
| [72](pr-072.json) | feat: rate limit the API routes per user                                                          | MERGED | `feat/rate-limit`                              | 2026-10-01 |
| [73](pr-073.json) | docs: add json-render screenshots to the README                                                   | MERGED | `docs/json-render-screenshots`                 | 2026-10-01 |
| [74](pr-074.json) | fix: answer 503 and keep a reply when the agent fails                                             | MERGED | `fix/agent-unavailable`                        | 2026-10-01 |
| [75](pr-075.json) | fix: give the read routes a looser rate limit                                                     | MERGED | `fix/read-rate-limit`                          | 2026-10-01 |
| [76](pr-076.json) | feat: greet a new conversation with three welcome messages                                        | MERGED | `feat/welcome-messages`                        | 2026-10-01 |
| [77](pr-077.json) | feat: welcome messages and a Medas mark                                                           | MERGED | `feat/welcome-messages`                        | 2026-10-01 |
| [78](pr-078.json) | docs: bring the README and CLAUDE.md in line with main                                            | MERGED | `docs/audit-readme`                            | 2026-10-01 |
| [79](pr-079.json) | feat: export a conversation as csv, json or pdf                                                   | MERGED | `feat/export-formats`                          | 2026-10-01 |
| [80](pr-080.json) | fix: validate roles, uploads and agent replies at the edge                                        | MERGED | `fix/audit-input-validation`                   | 2026-10-01 |
| [81](pr-081.json) | fix: verify the whole upload and refuse text aimed at the assistant                               | MERGED | `fix/audit-input-validation`                   | 2026-10-01 |
| [82](pr-082.json) | feat: reject over-long and injection-style messages on /ask                                       | MERGED | `fix/audit-input-validation`                   | 2026-10-01 |
| [83](pr-083.json) | fix: drop the undocumented <patient> block from the prompt                                        | MERGED | `fix/audit-input-validation`                   | 2026-10-01 |
