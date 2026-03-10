When designing and executing tests, apply these analytical frameworks:

**Equivalence Partitioning**
Divide the input space into equivalence classes — groups of inputs that should produce the same behavior. For a function that accepts an age parameter: negative values, zero, valid range (1-150), boundary values (1, 150), and above-range values are distinct partitions. Write at least one test per partition. The goal is maximum fault detection with minimum test count. Don't write 10 tests for the same partition — each test should cover a distinct behavioral region.

**Boundary Value Analysis**
Bugs cluster at boundaries. For every boundary in the specification (min value, max value, empty/non-empty, zero/positive, null/present), test: the value exactly at the boundary, one step below, and one step above. For string length limits: test at limit-1, limit, and limit+1. For collections: test with 0, 1, and 2 elements (the transition from empty to non-empty and from single to multiple often reveals bugs). For date ranges: test start date, end date, one day before start, one day after end.

**State Transition Coverage**
For stateful components, model the valid states and transitions. Test each valid transition, but more importantly test invalid transitions — what happens when you call `close()` on an already-closed connection? What happens when you `resume()` a task that was never paused? State transition bugs are common and often lead to data corruption or security issues. Draw the state machine, then ensure every edge (transition) has a test.

**Mutation Testing Mindset**
For each assertion you write, ask: If I removed this assertion, would any other test fail? If not, this assertion is the only thing detecting this class of bug — make sure it is precise. Then ask: What small code change (mutation) would make this test still pass but break the real behavior? Common weak assertions: checking only that no exception was thrown (but not checking the return value), checking list length (but not list contents), checking that a function was called (but not with what arguments).

**Test Independence & Isolation**
Every test must be independently runnable and produce the same result regardless of execution order. Shared mutable state between tests is the most common source of flaky tests. For each test, verify: Does it set up its own fixtures? Does it clean up after itself? Could running it 100 times in a row produce a different result? If a test depends on database state, external services, or file system contents, those dependencies must be explicitly controlled within the test.