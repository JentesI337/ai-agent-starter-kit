When writing or modifying code, apply these reasoning patterns:

**Edge Case Reasoning**
Before implementing any function, enumerate its edge cases systematically: What happens with empty input? Null/None/undefined? Maximum-size input? Negative numbers? Unicode and special characters? Concurrent access? For collection operations: empty collection, single element, duplicate elements, very large collections. For string operations: empty string, whitespace-only, multi-byte characters. Write the edge case list before writing the implementation, then verify each one is handled.

**API Contract Thinking**
Every function has a contract — preconditions (what callers must guarantee), postconditions (what the function guarantees), and invariants (what remains true throughout). Make contracts explicit: What types are accepted? What ranges are valid? What exceptions can be thrown and under what conditions? When modifying existing code, first determine the existing contract by reading all call sites, then preserve it. Breaking an implicit contract is the most common source of regression bugs.

**Error Propagation Analysis**
Trace error paths as carefully as success paths. For every operation that can fail: What error type is produced? Is it caught, propagated, or silently swallowed? Does the caller receive enough context to handle it meaningfully? Avoid these anti-patterns: catching and re-raising without added context, logging an error and also throwing it (double reporting), catching broad exception types that mask specific failures, returning None/null to signal failure when the caller doesn't check.

**Testability Assessment**
Before writing code, ask: How will this be tested? If the answer requires complex setup, the design needs improvement. Testable code has: explicit dependencies (injected, not imported globally), pure functions where possible (same input → same output), seams for test doubles (interfaces, callbacks, dependency injection), and observable outcomes (return values or state changes, not just side effects). If you find yourself needing to mock private methods or patch module-level imports, the code has a design problem.

**Complexity Budget**
Every conditional branch, loop, and early return adds cognitive complexity. For any function, if you need more than 3 levels of nesting or more than 5 conditional branches, extract a helper or restructure the logic. Prefer guard clauses (early returns for invalid states) over deeply nested if-else chains. Prefer data-driven dispatch (dictionaries, maps) over switch statements when the number of cases exceeds 4. The goal is that any developer can understand the function in a single reading pass.