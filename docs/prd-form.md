# Dedicated PRD Form: Course Generation MCP

Use this form before implementation or before giving Codex a large task.

## A. Project identity

| Field | Answer |
|---|---|
| Project name | Samrat Course MCP |
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
| Course project workflow | Project, source, blueprint, modules, lessons, activities, assessment, export | P0 | In progress |
| Source ingestion | Controlled upload ID, no arbitrary path access | P0 | In progress |
| Instructional quality validator | Alignment, source grounding, accessibility, compliance checks | P0 | In progress |
| Role-play simulation | Practical scenario training | P1 | In progress |
| SCORM export | Export-ready course package | P1 | In progress |
| Secure MCP gateway | Allowlisted tools only | P0 | In progress |
| Docker deployment | Separate container with secret files | P0 | In progress |
| Codex config | Attach MCP to Codex | P0 | In progress |

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
| create_course_project | title, audience, language | project JSON | Low | No |
| ingest_course_source | project ID, upload ID, source type | source metadata | Medium | No |
| generate_course_blueprint | project ID, duration, difficulty | blueprint JSON | Low | No |
| generate_module_pack | project ID, count | module JSON | Low | No |
| generate_lesson_pack | project ID, module ID | lesson JSON | Low | No |
| generate_interactive_activity | project ID, activity type, objective | activity JSON | Low | No |
| generate_assessment_bank | project ID, question count/types | assessment JSON | Low | No |
| validate_instructional_quality | project ID | quality report | Low | No |
| build_export_package | project ID, export format | package metadata | Medium | No in dev, Yes before publishing |
| request_publish_approval | project ID, reviewer | review request | High | Yes |

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
