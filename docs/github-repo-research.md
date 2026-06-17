# GitHub Research: Repos to Use or Adapt

This list is organized by how useful each repo is for building a stronger MiniCourseGenerator-style MCP product.

## 1. MCP foundations

| Repo | Use | Notes |
|---|---|---|
| https://github.com/modelcontextprotocol/python-sdk | MCP Python SDK | Base for Python MCP server implementation. |
| https://github.com/modelcontextprotocol/typescript-sdk | MCP TypeScript SDK | Alternative if we move to Node/TS. |
| https://github.com/modelcontextprotocol/servers | Reference MCP servers | Learn registration, tool structure, and deployment patterns. |
| https://github.com/microsoft/mcp-for-beginners | Learning and examples | Good training material for the engineering team. |
| https://github.com/PrefectHQ/fastmcp | FastMCP framework | Strong option for Pythonic MCP server development. |
| https://github.com/punkpeye/awesome-mcp-servers | MCP server directory | Discovery of existing MCP tools and patterns. |

## 2. MiniCourseGenerator public repos

| Repo | Use | Notes |
|---|---|---|
| https://github.com/minicoursegenerator | Official org | Public org currently shows limited source availability. |
| https://github.com/minicoursegenerator/edu-role-play | Role-play training asset | Useful idea reference for interactive scenario courses. |
| https://github.com/minicoursegenerator/skills-for-course-creators | Course creator skills | Useful for prompts/skills concept, not backend MCP clone. |

## 3. AI course generators

| Repo | Use | Notes |
|---|---|---|
| https://github.com/bhataasim1/ai-course-generator | Topic-to-course generation | Useful UI/product idea reference. |
| https://github.com/pramodkoujalagi/Automated-Course-Content-Generator | Outline/content/quizzes/PDF/PPT | Useful for generation pipeline ideas. |
| https://github.com/klausners/course-builder | Course builder | Research/learning-design reference. |
| https://github.com/dgcruzing/H5P-Material-Generator- | PDF to H5P prototype | Useful for H5P generation concept. |

## 4. SCORM/H5P/LMS

| Repo | Use | Notes |
|---|---|---|
| https://github.com/fracabu/scorm-course-generator | AI multi-agent SCORM course generator | Very relevant for SCORM package workflow ideas. |
| https://github.com/LiaScript/LiaScript-Exporter | SCORM/PDF/export generation | Can be used as export path or reference. |
| https://github.com/jcputney/scorm-again | SCORM runtime/player | Useful for testing SCORM behavior. |
| https://github.com/sr258/scorm-h5p-wrapper | Wrap H5P as SCORM | Useful for H5P-to-SCORM packaging. |
| https://github.com/h5p | H5P ecosystem | Source ecosystem for interactive learning blocks. |
| https://github.com/adaptlearning/adapt-contrib-spoor | SCORM tracking extension | Reference for tracking logic. |
| https://github.com/EscolaLMS/Scorm | LMS SCORM plugin | Reference for upload/play/tracking patterns. |

## 5. Recommended build combination

Use this combination first:

1. `modelcontextprotocol/python-sdk` or `PrefectHQ/fastmcp` for MCP server.
2. `fracabu/scorm-course-generator` for SCORM course generation inspiration.
3. `LiaScript/LiaScript-Exporter` for practical export flow.
4. `sr258/scorm-h5p-wrapper` and `h5p` for interactive H5P packaging.
5. `minicoursegenerator/edu-role-play` for scenario/role-play learning ideas.
6. `jcputney/scorm-again` for SCORM runtime testing.

## 6. What not to copy blindly

- Do not expose filesystem tools from generic MCP examples.
- Do not copy prototype auth patterns into production.
- Do not trust AI-generated course packages without validation.
- Do not make Codex aware of internal prompt templates or secrets.
- Do not run this inside the existing app container.
