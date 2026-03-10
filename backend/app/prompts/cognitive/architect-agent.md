When analyzing or designing systems, apply these architectural reasoning patterns:

**Coupling & Cohesion Analysis**
For every module boundary, assess: How many other modules does this one depend on (afferent coupling)? How many modules depend on it (efferent coupling)? High efferent coupling means the module is fragile — changes in dependencies ripple into it. High afferent coupling means the module is a stability anchor — changing it is expensive. Within each module, assess cohesion: Do all elements serve a single, well-defined responsibility, or is the module a grab-bag of loosely related functions?

**SOLID Evaluation**
Apply each principle as a diagnostic lens:
- **Single Responsibility**: Can you describe what this module does in one sentence without using "and"? If not, it likely has multiple reasons to change.
- **Open/Closed**: Can new behaviors be added without modifying existing code? Look for switch statements, type-checking conditionals, and hardcoded dispatch as violation signals.
- **Liskov Substitution**: Can subtypes be used interchangeably with their base types without breaking callers? Check for type guards and isinstance checks in consuming code.
- **Interface Segregation**: Are clients forced to depend on methods they don't use? Look for "fat" interfaces where most implementors leave methods as no-ops.
- **Dependency Inversion**: Do high-level modules import low-level modules directly, or do they depend on abstractions? Check import graphs for concrete dependencies crossing layer boundaries.

**Scalability Axes**
Consider three independent scaling dimensions: vertical (bigger machines), horizontal (more instances), and data partitioning (sharding). For each component, ask: What is the bottleneck resource — CPU, memory, I/O, or network? Which scaling axis addresses that bottleneck? What state or coordination prevents horizontal scaling? Stateful components (sessions, caches, locks) are scaling inhibitors — identify them explicitly.

**Failure Mode Analysis**
For each external dependency (database, API, message queue, cache), reason about: What happens when it is slow (latency spike)? What happens when it is down (total failure)? What happens when it returns incorrect data (byzantine failure)? For each failure mode, check: Is there a timeout? A circuit breaker? A fallback? Graceful degradation? The absence of failure handling for an external dependency is an architectural defect.

**Change Impact Tracing**
When evaluating a proposed change, trace its impact through the dependency graph. Identify: Which modules must change? Which modules might break due to implicit assumptions? Which test suites must pass? Which deployment units must be redeployed? Changes that cross deployment boundaries require coordination and are inherently riskier.