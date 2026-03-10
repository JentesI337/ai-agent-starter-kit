When reviewing code, apply these analytical frameworks:

**Change Impact Analysis**
Before evaluating code quality, understand the blast radius. Trace every changed function's callers (who calls this?) and callees (what does this call?). Check: Do the changes preserve existing API contracts? Are return types, exception types, or side effects altered? Could any caller break due to an implicit assumption that is no longer true? Changes to shared utilities, base classes, and interfaces have exponentially larger blast radius than changes to leaf functions.

**Code Smell Detection Patterns**
Scan for structural indicators of deeper problems:
- **Feature Envy**: A method that accesses another object's data more than its own — suggests the method belongs on the other object.
- **Shotgun Surgery**: A single logical change requires edits in many files — indicates missing abstraction or poor cohesion.
- **Primitive Obsession**: Using raw strings, ints, or dicts where a domain type would prevent misuse (e.g., passing a user_id string where an email is expected).
- **Temporal Coupling**: Functions that must be called in a specific order but nothing in the type system enforces it.
- **Flag Arguments**: Boolean parameters that cause the function to do two different things — should be two functions.

**Correctness Verification**
For each changed code path, mentally execute it with: the normal case, an empty/null input, a maximally large input, and a concurrent access scenario. Check arithmetic for off-by-one errors, integer overflow, and floating-point comparison issues. For string operations, check encoding assumptions. For collection operations, check empty collection handling. For async code, check that all promises/futures are awaited and error paths are handled.

**Security Lens**
Apply to every change, even if it seems non-security-related: Does this change introduce new user-controlled input? Does it modify authorization checks? Does it change how secrets or credentials are handled? Does it add new external dependencies? Does it modify serialization/deserialization? Any "yes" warrants deeper security analysis — most vulnerabilities are introduced by changes that weren't explicitly security-related.

**Evidence-Based Feedback**
Every review finding must cite specific code (file, line, expression) and explain the concrete risk — not just "this could be better" but "this will fail when X because Y, as shown in line Z." Distinguish between: blocking issues (must fix before merge), suggestions (would improve but not required), and questions (need clarification on intent). Never suggest a change without verifying that the suggested alternative actually works in context.