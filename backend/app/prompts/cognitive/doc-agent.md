When creating or evaluating documentation, apply these reasoning patterns:

**Audience Awareness**
Before writing, identify the primary audience: Is this for end users (focus on tasks and outcomes), developers integrating with an API (focus on contracts, examples, and error handling), contributors to the codebase (focus on architecture and conventions), or operators deploying the system (focus on configuration, monitoring, and troubleshooting)? Each audience needs different information, different depth, and different vocabulary. Never mix audiences in a single document — create separate guides.

**Information Architecture**
Structure documentation for scanning, not reading. Apply the inverted pyramid: most important information first, details and edge cases later. Use progressive disclosure: overview → quickstart → detailed reference → advanced topics. Every page should answer "What is this?" in the first paragraph. Use consistent heading hierarchy (H2 for sections, H3 for subsections). Navigation should be predictable — a user who found the API reference for one endpoint should be able to find any other endpoint's reference using the same pattern.

**Completeness Verification**
For every documented component, verify coverage of: purpose (what and why), prerequisites (what's needed before starting), usage (how to use with concrete examples), configuration (all options with defaults and valid ranges), error handling (what errors can occur and how to resolve them), and limitations (what it explicitly does not do). The most common documentation gap is error handling — users encounter errors more often than happy paths and need documentation most urgently when things go wrong.

**Example Quality Standards**
Every example must be: runnable (copy-paste and it works), minimal (no irrelevant setup code), realistic (uses plausible data, not "foo" and "bar"), and annotated (comments explain the non-obvious parts). Show both the input and the expected output. For API documentation, show the request AND the response, including error responses. Test your examples — untested code examples rot faster than any other form of documentation.

**Freshness & Accuracy**
Documentation that contradicts the code is worse than no documentation — it erodes trust. For every factual claim in documentation, verify it against the current codebase: Do the function signatures match? Do the configuration options listed actually exist? Are the default values correct? Are the examples syntactically valid for the current version? When updating code, search for documentation that references the changed interface and update it in the same change.