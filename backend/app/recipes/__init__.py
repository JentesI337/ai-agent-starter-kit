"""recipes — Recipe Domain.

Recipes are the primary automation primitive. Each recipe defines a sequence
of steps (agent prompts, tool calls, checkpoints) that can be executed,
paused, and resumed.

Transport layer (HTTP routes) lives in app.transport.routers.recipes.
"""
