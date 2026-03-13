# Tool Routing Reference

Use this reference when selecting tools. Each entry defines when to use the tool,
when NOT to use it, expected output characteristics, and known pitfalls.

---

## list_dir

**When to use:**
- Browse a directory's contents to understand project structure
- Find files by location when you don't know the exact filename
- Verify a directory exists before writing to it

**When NOT to use:**
- When you know the exact filename → use `file_search` or `read_file` directly
- When searching file *content* → use `grep_search`
- When you need recursive content listing → call `list_dir` recursively or use `grep_search`

**Output note:** Returns immediate children only; not recursive.

---

## read_file

**When to use:**
- Read source code, configuration, logs, or any text file at a known path
- Inspect a specific line range of a large file
- Verify file content before making an edit

**When NOT to use:**
- When you don't know the path → use `file_search` first
- When searching across many files for a pattern → use `grep_search`
- When the file is binary (image, compiled) → use `analyze_image` for images

**Output note:** May return partial content for large files.
ONLY reference values that appear verbatim in the returned content.
Do NOT infer line numbers, sizes, or values from model knowledge.

**Caution:** Reading a file does not lock it. It may change between reads.

---

## write_file

**When to use:**
- Create a new file
- Fully replace an existing file's content

**When NOT to use:**
- Making targeted edits to an existing file → prefer `apply_patch` (safer, preserves context)
- When you're not sure of the correct full content → use `read_file` first, then patch

**Caution:** Irreversible overwrite. Always confirm you have the correct absolute path.
NEVER write to a path outside the workspace root.

---

## apply_patch

**When to use:**
- Targeted additions, deletions, or replacements in an existing file
- Refactoring: rename symbols, move blocks, update function signatures
- Any edit where preserving surrounding context matters

**When NOT to use:**
- Creating a file that doesn't exist yet → use `write_file`
- The file needs to be fully rewritten → use `write_file` (patch overhead not worth it)
- Binary files

**Patch format:** Use the `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE` block format:
```
<<<<<<< SEARCH
[exact lines to find, including whitespace/indentation]
=======
[replacement lines]
>>>>>>> REPLACE
```
The SEARCH block must match the file content exactly (character-for-character).
Include at least 3 lines of surrounding context to ensure uniqueness.
Always call `read_file` first to confirm the exact content before writing a patch.

**Caution:** If the SEARCH block doesn't match exactly, the patch fails silently or partially.
Read the file first to get exact whitespace and indentation.

---

## run_command

**When to use:**
- Execute shell diagnostics: `netstat`, `ps`, `tasklist`, `ss`, `lsof`, `df`
- Run builds: `pnpm build`, `python setup.py`, `make`
- Run tests: `pytest`, `vitest`, `jest`
- Git operations: `git status`, `git log`, `git diff`
- Any shell operation that produces output to analyze

**When NOT to use:**
- Listing directory contents → use `list_dir` (works on every OS)
- Reading file content → use `read_file` (works on every OS)
- Searching file content → use `grep_search`
- Browsing the web → use `web_fetch`
- Long-running or background processes → use `start_background_command`

**Platform caution:** Commands run via `subprocess` without a shell.
OS-specific shell builtins (`dir`, `type`, `cat`, `echo`, `findstr`) are **not
available** because they require `cmd.exe` or `bash` as a host process.
Always prefer the dedicated agent tools (`list_dir`, `read_file`, `grep_search`)
over shell equivalents — they work identically on Windows and Linux.

**Caution:** Commands that modify system state require policy approval before execution.
NEVER pass un-sanitized user input directly as shell arguments.

**Output note:**
ONLY reference PIDs, ports, paths, usernames, or process names that appear
**verbatim** in the command output. If a value is not in the output → report
"not found in output". Do NOT guess or derive values from model knowledge.

---

## code_execute

**When to use:**
- Run Python code with persistent state — variables, imports, and function definitions survive across calls
- Data analysis, calculations, transformations, and exploratory work
- Generate visualizations (matplotlib plots are returned as base64 PNG images)
- Test code snippets interactively before writing to files

**When NOT to use:**
- Shell commands, build tools, or system diagnostics → use `run_command`
- Creating or editing project files → use `write_file` / `apply_patch`
- Long-running servers or background tasks → use `start_background_command`
- Non-Python code that needs persistent state (not supported)

**Output note:** Returns stdout, stderr, and images (base64-encoded PNGs from matplotlib).
Single expressions display their result automatically (like IPython).
DataFrames render as markdown tables.

**Caution:** State persists across calls within the same `session_id`.
Use `code_reset` to clear state if the session becomes corrupted.
Use separate `session_id` values for independent workstreams.

---

## code_reset

**When to use:**
- Clear all persistent REPL state (variables, imports, functions) for a session
- Recover from a corrupted or timed-out session
- Start fresh without leftover state from previous executions

**When NOT to use:**
- When you want to keep existing state → just call `code_execute` again
- When you need to reset a non-Python session (only Python REPL is persistent)

**Output note:** Returns confirmation that the session was reset.

**Caution:** This is irreversible — all session state is lost.

---

## start_background_command

**When to use:**
- Long-running processes: dev servers, watchers, build pipelines
- Commands that should not block the agent while running
- Processes where you need to poll output at a later point

**When NOT to use:**
- Short commands that complete instantly → use `run_command`
- When you need the output immediately → use `run_command`

**Required follow-up:** Always call `get_background_output` before reporting results.
Do NOT state a background command "succeeded" without reading its output.

---

## get_background_output

**When to use:**
- After `start_background_command` to read what the process has produced
- To check if a background process has completed or failed
- To monitor log output of a running server or build

**When NOT to use:**
- For processes started with `run_command` (synchronous; output is inline)

---

## kill_background_process

**When to use:**
- Terminate a background process started with `start_background_command`
- Clean up dev servers or watchers after the task is complete

---

## file_search

**When to use:**
- Find files by name pattern when the exact path is unknown
- Locate all files matching a glob (e.g. `**/*.py`, `test_*.py`)

**When NOT to use:**
- Searching file *content* → use `grep_search`
- You already know the exact absolute path → use `read_file` directly

---

## grep_search

**When to use:**
- Find where a string, symbol, or pattern appears across files
- Locate all usages of a function, class, or variable name
- Check whether a pattern exists anywhere in the codebase

**When NOT to use:**
- You want file structure (what files/dirs exist) → use `list_dir`
- You want to read a specific known file → use `read_file`
- You want to find all callers/references of a specific symbol with type info → use `list_code_usages`

---

## list_code_usages

**When to use:**
- Find all callers, implementations, or references of a named symbol (function, class, method, variable)
- Understanding the full call graph before changing a function signature
- Verifying that a rename was applied everywhere

**When NOT to use:**
- General text/string search → use `grep_search`
- Finding files by name → use `file_search`

---

## get_changed_files

**When to use:**
- Review what files have been modified, staged, or have merge conflicts in a git repo
- Before committing: verify scope of changes
- Auditing what an agent has changed in a session

---

## web_search

**When to use:**
- Look up current events, recent package versions, API documentation
- Research error messages, stack traces, or library behavior
- Find the URL to a specific resource before fetching it

**When NOT to use:**
- Local file content → use `read_file` or `grep_search`
- You already have a direct URL → use `web_fetch`

**Output note:** Results may include outdated or incorrect information.
Always verify version numbers against the project's lockfile or `package.json`.

---

## web_fetch

**When to use:**
- Read a specific URL: documentation page, API spec, raw GitHub file, JSON endpoint
- Fetch content when you have a direct URL

**When NOT to use:**
- You need to find the URL first → use `web_search` first
- REST API calls with custom headers/auth/body → use `http_request`

---

## http_request

**When to use:**
- Call REST APIs with specific HTTP method, headers, or request body
- Endpoints requiring authentication headers
- Non-GET requests (POST, PUT, PATCH, DELETE)

**When NOT to use:**
- Simple URL fetch without custom headers → use `web_fetch`
- Browsing or searching the web → use `web_search`

---

## analyze_image

**When to use:**
- Describe, analyze, or extract information from image files
- Screenshots, diagrams, UI mockups

**When NOT to use:**
- Text files → use `read_file`
- The image contains code or config you need to edit → transcribe with `analyze_image`, then edit

---

## browser_open

**When to use:**
- Navigate to a URL and retrieve the page title and visible text content
- Start an interactive browsing session on a website
- Verify that a web page loads correctly

**When NOT to use:**
- You only need the raw HTML or a static fetch → use `web_fetch`
- You need to search the web for a URL first → use `web_search`

**Output note:** Returns page title and extracted text. The browser session persists across calls — subsequent `browser_click`, `browser_type`, etc. operate on the same page.

**Caution:** Only publicly accessible or localhost URLs are allowed. Internal/private IP ranges are blocked (SSRF protection).

---

## browser_click

**When to use:**
- Click a button, link, or interactive element on the current browser page
- Navigate through multi-step web workflows (e.g. pagination, form submission)

**When NOT to use:**
- No browser session is open → call `browser_open` first
- You need to type into a field → use `browser_type`

**Output note:** Accepts a CSS selector to identify the target element.

---

## browser_type

**When to use:**
- Type text into an input field, textarea, or contenteditable element
- Fill in form fields (login forms, search boxes, etc.)

**When NOT to use:**
- Clicking a button or link → use `browser_click`
- No browser session is open → call `browser_open` first

**Output note:** Accepts a CSS selector and the text to type.

---

## browser_screenshot

**When to use:**
- Capture a visual snapshot of the current browser page
- Debug layout or rendering issues
- Verify visual state after interactions

**When NOT to use:**
- You only need text content → use `browser_read_dom`
- Analyzing a local image file → use `analyze_image`

**Output note:** Returns a base64-encoded PNG image.

---

## browser_read_dom

**When to use:**
- Extract structured content from the current page: text, links, forms, tables
- Get a clean representation of page content for analysis
- Understand page structure (available links, form fields, navigation)

**When NOT to use:**
- You need a visual snapshot → use `browser_screenshot`
- You haven't opened a page yet → call `browser_open` first

**Output note:** Returns structured data (text blocks, link URLs, form fields) from the live DOM.

---

## browser_evaluate_js

**When to use:**
- Execute custom JavaScript in the browser page context
- Extract data not available through other browser tools
- Interact with page APIs or manipulate the DOM programmatically

**When NOT to use:**
- Simple clicks or typing → use `browser_click` / `browser_type`
- Reading page content → try `browser_read_dom` first

**Output note:** Returns the serialized result of the JS expression.

**Caution:** Avoid executing untrusted or user-supplied JavaScript. Keep scripts focused and minimal.

---

## spawn_subrun

**When to use:**
- Delegate a self-contained, long-running, or complex sub-task to a separate agent instance
- Parallel workstreams that don't share state
- Tasks where you'd otherwise chain 10+ tool calls that are logically independent
- Running a task using a specific specialist agent (pass the `agent_id`)

**When NOT to use:**
- Simple single-tool operations → use the tool directly
- Tasks that depend on results already in the current context → do them inline
- When the sub-task is trivial (< 3 tool calls) → do it inline
- When the user asks to *create* a new agent → use `create_agent` instead

**Required:** The sub-agent prompt must be **fully self-contained**:
- Embed all relevant context (goal, constraints, tool outputs needed, output format)
- Do NOT assume the sub-agent has access to the parent's tool history
- State all constraints explicitly: `"Do NOT do X"`, `"ONLY produce Y"`
- Set a meaningful `run_label` for observability

---

## create_agent

**When to use:**
- The user asks to create a new agent, specialist, or expert
- Building a persistent helper with a specific role and domain expertise
- Setting up a reusable specialist that can be delegated to later via `spawn_subrun`

**When NOT to use:**
- The user asks to create a workflow / pipeline / process → use `create_workflow` or `build_workflow`
- One-off delegation of a task → use `spawn_subrun` directly
- Listing existing agents → use `list_agents`

**Key distinction — Agent vs. Workflow:**
- **Agent** = a persistent specialist entity with a role, expertise, and capabilities. It answers questions and performs tasks in its domain. Created with `create_agent`.
- **Workflow** = a repeatable multi-step process (pipeline). It defines a sequence of steps that are executed in order. Created with `create_workflow` or `build_workflow`.

**Output note:** Returns the new agent_id. The agent is immediately available for delegation.

---

## list_agents

**When to use:**
- The user asks what agents/specialists are available
- Before creating an agent, to check if a similar one already exists
- When deciding which agent_id to use with `spawn_subrun`

**When NOT to use:**
- Listing workflows → the Workflows page in the UI handles that

---

## Tool Aliases

The following aliases are accepted — they map to the canonical tool name:

| Alias | Canonical |
|---|---|
| `readfile`, `read` | `read_file` |
| `writefile`, `createfile` | `write_file` |
| `listdir` | `list_dir` |
| `runcommand` | `run_command` |
| `applypatch` | `apply_patch` |
| `filesearch` | `file_search` |
| `grepsearch` | `grep_search` |
| `listcodeusages` | `list_code_usages` |
| `getchangedfiles` | `get_changed_files` |
| `startbackgroundcommand` | `start_background_command` |
| `getbackgroundoutput` | `get_background_output` |
| `killbackgroundprocess` | `kill_background_process` |
| `websearch`, `search`, `search_web` | `web_search` |
| `webfetch` | `web_fetch` |
| `httprequest`, `http_request_tool` | `http_request` |
| `analyzeimage`, `vision`, `image_analysis` | `analyze_image` |
| `browseropen`, `open_browser` | `browser_open` |
| `browserclick` | `browser_click` |
| `browsertype` | `browser_type` |
| `browserscreenshot`, `screenshot` | `browser_screenshot` |
| `browserreaddom`, `browser_dom` | `browser_read_dom` |
| `browserevaluatejs`, `browser_js`, `browser_eval` | `browser_evaluate_js` |
| `codeexecute`, `code_interpreter` | `code_execute` |
| `codereset`, `code_interpreter_reset` | `code_reset` |
| `spawnsubrun` | `spawn_subrun` |

Always prefer the canonical name in your tool calls.

---

## Error Handling Reference

| Tool returns... | Correct action |
|---|---|
| `run_command` non-zero exit | Read stderr; report exact error; do NOT assume partial success |
| `read_file` file not found | Verify path with `file_search`; do NOT fabricate content |
| `grep_search` no matches | Try simpler pattern; check for aliases; do NOT assume code is absent |
| `write_file` / `apply_patch` error | Read current file state; resolve conflict; retry |
| `web_search` / `web_fetch` fails | State failure explicitly; do NOT substitute model knowledge |
| `browser_open` timeout / error | Check URL is valid and publicly accessible; report the specific error |
| `browser_click` / `browser_type` selector not found | Use `browser_read_dom` to inspect available elements; adjust selector |
| `code_execute` timeout | Session killed, auto-restarts; use `code_reset` if state corrupt |
| `spawn_subrun` empty result | Report sub-agent produced no output; do NOT invent result |
| Any tool: empty output | State "tool returned empty output"; do NOT infer from model knowledge |

---

## Decision Cheatsheet

| I want to… | Use |
|---|---|
| Browse a directory | `list_dir` |
| Read a known file | `read_file` |
| Find a file by name | `file_search` |
| Search file content | `grep_search` |
| Find all uses of a function | `list_code_usages` |
| Create or overwrite a file | `write_file` |
| Edit part of an existing file | `apply_patch` |
| Run a shell command | `run_command` |
| Run a long-running process | `start_background_command` |
| Check background process output | `get_background_output` |
| Stop a background process | `kill_background_process` |
| See what files changed in git | `get_changed_files` |
| Search the internet | `web_search` |
| Fetch a specific URL | `web_fetch` |
| Call a REST API | `http_request` |
| Analyze an image | `analyze_image` |
| Open a web page interactively | `browser_open` |
| Click a button or link on a page | `browser_click` |
| Fill in a form field | `browser_type` |
| Take a screenshot of a page | `browser_screenshot` |
| Read page content (text, links, forms) | `browser_read_dom` |
| Run JavaScript on a page | `browser_evaluate_js` |
| Run Python with persistent state | `code_execute` |
| Clear REPL session | `code_reset` |
| Delegate a complex sub-task | `spawn_subrun` |
| Create a new specialist agent | `create_agent` |
| List available agents | `list_agents` |
