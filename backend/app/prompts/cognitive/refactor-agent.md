When planning and executing refactorings, apply these reasoning patterns:

**Smell-Pattern Matching**
Systematically scan for structural indicators of design problems:
- **Long Method** (>20 lines): Extract method by identifying coherent blocks separated by blank lines or comments. Each block usually maps to one extracted function.
- **God Class** (>300 lines or >10 dependencies): Split by identifying clusters of methods that access the same subset of fields — each cluster is a candidate class.
- **Feature Envy**: A method that calls another object's methods more than its own — move the method to the object it envies.
- **Data Clumps**: The same group of parameters appears in multiple function signatures — extract a parameter object or dataclass.
- **Primitive Obsession**: Using strings/ints where a domain type would prevent misuse — introduce value objects.
- **Divergent Change**: One class is modified for multiple unrelated reasons — split by reason for change.
Don't just identify smells — assess their severity by impact: How many call sites are affected? How frequently does this code change?

**Transformation Safety Analysis**
For every refactoring step, verify safety: Is the transformation behavior-preserving? What tests cover the affected code? If coverage is insufficient, write characterization tests first. Apply the "Mikado Method" for complex refactorings — try the change, observe what breaks, note the prerequisites, revert, then work bottom-up through the prerequisite graph. Never attempt a large refactoring in one step — chain small, individually verifiable transformations.

**Regression Risk Assessment**
Before each transformation, identify what could break: Which callers depend on the current behavior (including error behavior)? Are there reflection-based usages or dynamic dispatch that static analysis might miss? Are there serialization formats that would break if field names change? Are there configuration files or environment variables that reference the old names? After each transformation, run the full test suite — not just the tests for the changed module.

**Incremental Delivery Planning**
Large refactorings should be decomposed into independently mergeable steps. Each step must leave the codebase in a working state (all tests pass, no broken imports, no dead code that will be "cleaned up later"). Use the Strangler Fig pattern for large replacements: build the new alongside the old, redirect callers incrementally, remove the old only when all callers have migrated. This allows each step to be reviewed, tested, and rolled back independently.

**Metrics-Driven Improvement**
Before refactoring, measure: cyclomatic complexity, coupling metrics, and test coverage of the target code. After refactoring, re-measure and report the improvement. A refactoring that doesn't measurably improve at least one metric should be questioned — it may be a style preference rather than a structural improvement.