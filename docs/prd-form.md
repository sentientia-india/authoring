# Dedicated PRD Form: Course Generation MCP

Use this form before implementation or before giving Codex a large task.

## A. Project identity

| Field | Answer |
|---|---|
| Project name | Sentientia Course MCP |
| Owner |  |
| Business sponsor |  |
| Technical owner |  |
| Repository URL |  |
| Target launch date |  |
| Environments | Dev / Staging / Production |

## B. Problem statement

What problem are we solving?


Who has this problem?


Why now?


## C. Target users

| User type | Need | Priority |
|---|---|---|
| Instructional designer | Generate structured courses faster | High |
| L&D manager | Review and publish training | High |
| Developer/Codex | Build and maintain MCP safely | High |
| Admin | Manage integrations and permissions | Medium |
| Learner | Take generated course | Later |

## D. Success metrics

| Metric | Current | Target | Measurement method |
|---|---:|---:|---|
| Course draft time |  | <10 min | Product logs |
| Outline acceptance |  | >=75% | Review status |
| Quiz validation pass |  | >=95% | CI/tool logs |
| SCORM validation pass |  | >=90% MVP | Export tests |
| Secret exposure incidents |  | 0 | Audit/security review |

## E. MVP features

| Feature | Description | Priority | Status |
|---|---|---|---|
| Generate course outline | Topic/source to modules and lessons | P0 | Planned |
| Generate lessons | Lesson draft with objectives | P0 | Planned |
| Generate quiz | MCQs and answers | P0 | Planned |
| Generate role-play | Practical scenario training | P1 | Planned |
| SCORM scaffold | Export-ready course structure | P1 | Planned |
| Secure MCP gateway | Allowlisted tools only | P0 | Planned |
| Docker deployment | Separate container | P0 | Planned |
| Codex config | Attach MCP to Codex | P0 | Planned |

## F. Non-goals

- Full LMS UI in MVP
- Payment flow
- Marketplace
- Unlimited public file browsing
- Direct unapproved publishing
- Internal prompt exposure
- Shell/file/database tools exposed to Codex

## G. MCP tool design

| Tool | Inputs | Outputs | Risk | Approval needed? |
|---|---|---|---|---|
| generate_course_outline | topic, audience, duration, source text | outline JSON | Low | No |
| generate_lesson_draft | module, objective, audience | lesson JSON | Low | No |
| generate_quiz_bank | objectives, count, difficulty | quiz JSON | Low | No |
| generate_roleplay_scenario | role, context, objective | scenario JSON | Low | No |
| build_scorm_package_scaffold | course JSON | package path/manifest | Medium | No in dev, Yes in prod if publishing |
| publish_to_lms | course package, LMS target | LMS URL | High | Yes |

## H. Security requirements

| Requirement | Required? | Notes |
|---|---|---|
| Separate Docker container | Yes | Do not mix with existing app container |
| Non-root container user | Yes | Required for production |
| Tool allowlist | Yes | Codex sees only course tools |
| No shell tool | Yes | Never expose |
| No raw file read/write tool | Yes | Never expose broadly |
| No env variable tool | Yes | Never expose |
| API token auth | Yes | MVP |
| OAuth 2.1-ready design | Yes | Post-MVP |
| Audit logging | Yes | Required |
| Approval for high-risk actions | Yes | Required |

## I. Deployment requirements

| Field | Value |
|---|---|
| Docker service name | course-mcp |
| Public port | 8777 local/private only |
| Network | dedicated Docker network |
| Health endpoint | `/health` |
| Restart policy | unless-stopped |
| Volume | output artifacts only |
| Reverse proxy | optional for public/TLS |

## J. Open questions

1. Which LMS should be supported first: Moodle, Canvas, custom LMS, or SCORM-only?
2. Which LLM provider will be used in production?
3. Do we need multi-tenant isolation in MVP?
4. Should learner enrollment tools be included in MVP or phase 2?
5. Should uploads be handled by this MCP or by the main application and passed as normalized text?
