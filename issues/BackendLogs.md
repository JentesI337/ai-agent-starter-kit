STATE_ENCRYPTION_KEY not set or invalid — using ephemeral key. Encrypted state will NOT survive restart. Set STATE_ENCRYPTION_KEY to a 64-char hex string in .env
SESSION_SIGNING_KEY not set — using ephemeral key. Sessions will be invalidated on restart. Set SESSION_SIGNING_KEY in .env for persistent sessions.
2026-03-07 07:52:43,317 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,571 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,573 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,575 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,576 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,578 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,579 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,581 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,584 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,585 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,587 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,588 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,590 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,592 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,593 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:52:43,598 WARNING [app.services.policy_approval_service] SEC: Policy file loaded without valid HMAC signature: C:\Users\wisni\code\git\ai-agent-starter-kit\backend\state_store\policy_allow_always_rules.json
←[32mINFO←[0m:     Started server process [←[36m7780←[0m]
←[32mINFO←[0m:     Waiting for application startup.
2026-03-07 07:52:43,889 INFO [app.main] startup_paths workspace_root=C:\Users\wisni\code\git\ai-agent-starter-kit\backend memory_dir=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\memory_store orchestrator_state_dir=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\state_store runtime_state_file=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\runtime_state.json
2026-03-07 07:52:43,891 INFO [app.main] startup_memory_reset enabled=True removed_files=2
2026-03-07 07:52:43,894 INFO [app.main] startup_state_reset enabled=True removed_runs=2 removed_snapshots=2
←[32mINFO←[0m:     Application startup complete.
←[32mINFO←[0m:     Uvicorn running on ←[1mhttp://0.0.0.0:8000←[0m (Press CTRL+C to quit)
←[32mINFO←[0m:     127.0.0.1:58949 - "←[1mOPTIONS /api/control/memory.overview HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:58949 - "←[1mPOST /api/control/memory.overview HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-07 07:53:44,589 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=12 socket_options=None
←[32mINFO←[0m:     127.0.0.1:63328 - "←[1mGET /api/runtime/features HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:50799 - "←[1mGET /api/agents HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:55510 - "←[1mGET /api/presets HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:63360 - "←[1mOPTIONS /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:65038 - "←[1mGET /api/monitoring/schema HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:63328 - "←[1mGET /api/custom-agents HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:65038 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-07 07:53:44,887 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0EC3C6990>
2026-03-07 07:53:44,888 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'GET']>
2026-03-07 07:53:44,889 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 07:53:44,889 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'GET']>
2026-03-07 07:53:44,890 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 07:53:44,890 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'GET']>
2026-03-07 07:53:45,044 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 06:53:45 GMT'), (b'Content-Length', b'1223')])
2026-03-07 07:53:45,048 INFO [httpx] HTTP Request: GET http://localhost:11434/api/tags "HTTP/1.1 200 OK"
2026-03-07 07:53:45,048 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'GET']>
2026-03-07 07:53:45,050 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 07:53:45,051 DEBUG [httpcore.http11] response_closed.started
2026-03-07 07:53:45,051 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 07:53:45,054 DEBUG [httpcore.connection] close.started
2026-03-07 07:53:45,055 DEBUG [httpcore.connection] close.complete
←[32mINFO←[0m:     127.0.0.1:58949 - "←[1mGET /api/runtime/status HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     ('127.0.0.1', 62379) - "WebSocket /ws/agent" [accepted]
2026-03-07 07:54:44,322 INFO [app.main] ws_connected session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df runtime=api model=qwen3-coder:480b-cloud
2026-03-07 07:54:44,345 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=1 type=status request_id=None
←[32mINFO←[0m:     connection open
2026-03-07 07:54:45,110 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=12 socket_options=None
←[32mINFO←[0m:     127.0.0.1:63452 - "←[1mGET /api/runtime/features HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:51192 - "←[1mGET /api/agents HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:49666 - "←[1mGET /api/presets HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:53104 - "←[1mGET /api/monitoring/schema HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61636 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:63452 - "←[1mGET /api/custom-agents HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-07 07:54:45,433 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0EC0D3410>
2026-03-07 07:54:45,436 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'GET']>
2026-03-07 07:54:45,438 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 07:54:45,438 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'GET']>
2026-03-07 07:54:45,438 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 07:54:45,439 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'GET']>
2026-03-07 07:54:45,620 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 06:54:45 GMT'), (b'Content-Length', b'1223')])
2026-03-07 07:54:45,623 INFO [httpx] HTTP Request: GET http://localhost:11434/api/tags "HTTP/1.1 200 OK"
2026-03-07 07:54:45,625 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'GET']>
2026-03-07 07:54:45,625 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 07:54:45,627 DEBUG [httpcore.http11] response_closed.started
2026-03-07 07:54:45,628 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 07:54:45,635 DEBUG [httpcore.connection] close.started
2026-03-07 07:54:45,637 DEBUG [httpcore.connection] close.complete
←[32mINFO←[0m:     127.0.0.1:64493 - "←[1mGET /api/runtime/status HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-07 07:55:33,469 INFO [app.main] ws_message_received request_id=f424c322-ce98-4528-b776-43d85436670d session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df type=user_message agent_id=head-agent content_len=2 requested_model=None
2026-03-07 07:55:33,645 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=2 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:33,722 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=3 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:33,782 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=4 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:33,861 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=5 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:33,862 INFO [app.main] ws_request_dispatch request_id=f424c322-ce98-4528-b776-43d85436670d session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df runtime=api active_model=qwen3-coder:480b-cloud
2026-03-07 07:55:33,864 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:55:33,869 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:55:33,870 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 07:55:33,870 INFO [app.main] ws_agent_run_start request_id=f424c322-ce98-4528-b776-43d85436670d session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df selected_model=qwen3-coder:480b-cloud
2026-03-07 07:55:33,930 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=6 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:33,982 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=7 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,055 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=8 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,134 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=9 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,175 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=10 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,271 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=11 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,333 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=12 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,396 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=13 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,432 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=14 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,476 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=15 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,508 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=16 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,547 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=17 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,568 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=18 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,593 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=19 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,594 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=20 type=status request_id=None
2026-03-07 07:55:34,644 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=21 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:55:34,922 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 07:55:35,176 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0ECD94740>
2026-03-07 07:55:35,177 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 07:55:35,177 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 07:55:35,178 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 07:55:35,179 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 07:55:35,180 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 07:57:35,209 DEBUG [httpcore.http11] receive_response_headers.failed exception=ReadTimeout(TimeoutError())
2026-03-07 07:57:35,214 DEBUG [httpcore.http11] response_closed.started
2026-03-07 07:57:35,215 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 07:57:35,234 WARNING [app.llm_client] llm_native_complete_timeout base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud error=
2026-03-07 07:57:35,353 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=22 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:35,396 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=23 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:35,435 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=24 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:35,470 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=25 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,002 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=26 type=status request_id=None
2026-03-07 07:57:36,048 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=27 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,126 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=28 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,171 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=29 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,318 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=30 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,371 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=31 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,428 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=32 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,489 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=33 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,537 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=34 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,580 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=35 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:36,580 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=36 type=status request_id=None
2026-03-07 07:57:36,666 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=37 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:37,055 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 07:57:37,317 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0EC864BF0>
2026-03-07 07:57:37,321 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 07:57:37,323 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 07:57:37,323 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 07:57:37,324 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 07:57:37,324 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 07:57:37,343 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 404, b'Not Found', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 06:57:37 GMT'), (b'Content-Length', b'58')])
2026-03-07 07:57:37,344 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 404 Not Found"
2026-03-07 07:57:37,344 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 07:57:37,345 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 07:57:37,346 DEBUG [httpcore.http11] response_closed.started
2026-03-07 07:57:37,346 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 07:57:37,358 WARNING [app.llm_client] llm_native_complete_http_error url=http://localhost:11434/api/chat model=llama3.3:70b-instruct-q4_K_M status=404 attempt=1 body={"error":"model 'llama3.3:70b-instruct-q4_K_M' not found"}
2026-03-07 07:57:37,359 DEBUG [httpcore.connection] close.started
2026-03-07 07:57:37,360 DEBUG [httpcore.connection] close.complete
2026-03-07 07:57:37,403 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=38 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:37,444 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=39 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:37,490 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=40 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:37,528 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=41 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:37,565 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=42 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:37,673 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=43 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 07:57:37,700 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=44 type=error request_id=None
2026-03-07 07:57:37,729 DEBUG [app.main] ws_send_event session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df seq=45 type=lifecycle request_id=f424c322-ce98-4528-b776-43d85436670d
2026-03-07 08:01:39,799 INFO [app.main] ws_disconnected session_id=2d45a09c-a6fb-45a8-a437-f95d7b24e7df
←[32mINFO←[0m:     connection closed
←[32mINFO←[0m:     ('127.0.0.1', 59581) - "WebSocket /ws/agent" [accepted]
2026-03-07 08:01:40,472 INFO [app.main] ws_connected session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af runtime=api model=qwen3-coder:480b-cloud
2026-03-07 08:01:40,473 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=1 type=status request_id=None
←[32mINFO←[0m:     connection open
2026-03-07 08:01:44,058 INFO [app.main] ws_message_received request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af type=user_message agent_id=head-agent content_len=2 requested_model=None
2026-03-07 08:01:44,218 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=2 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:44,413 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=3 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:44,587 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=4 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:44,754 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=5 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:44,756 INFO [app.main] ws_request_dispatch request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af runtime=api active_model=qwen3-coder:480b-cloud
2026-03-07 08:01:44,760 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 08:01:44,761 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 08:01:44,761 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-07 08:01:44,765 INFO [app.main] ws_agent_run_start request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af selected_model=qwen3-coder:480b-cloud
2026-03-07 08:01:44,824 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=6 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:44,910 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=7 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:44,967 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=8 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,027 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=9 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,061 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=10 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,169 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=11 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,233 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=12 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,284 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=13 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,309 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=14 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,368 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=15 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,391 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=16 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,431 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=17 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,460 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=18 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,482 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=19 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,483 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=20 type=status request_id=None
2026-03-07 08:01:45,525 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=21 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:45,967 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 08:01:46,254 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0E7316C00>
2026-03-07 08:01:46,258 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 08:01:46,260 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 08:01:46,260 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 08:01:46,260 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 08:01:46,261 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 08:01:48,387 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 07:01:48 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-07 08:01:48,392 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-07 08:01:48,394 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 08:01:48,398 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 08:01:48,399 DEBUG [httpcore.http11] response_closed.started
2026-03-07 08:01:48,401 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 08:01:48,405 DEBUG [httpcore.connection] close.started
2026-03-07 08:01:48,405 DEBUG [httpcore.connection] close.complete
2026-03-07 08:01:48,482 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=22 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:48,513 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=23 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:48,549 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=24 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:48,561 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=25 type=agent_step request_id=None
2026-03-07 08:01:48,626 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=26 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:48,672 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=27 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:48,740 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=28 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:48,813 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=29 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:48,864 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=30 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:48,896 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=31 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:49,178 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 08:01:49,449 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0E7316AE0>
2026-03-07 08:01:49,451 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 08:01:49,451 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 08:01:49,452 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 08:01:49,452 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 08:01:49,452 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 08:01:50,366 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 07:01:50 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-07 08:01:50,366 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-07 08:01:50,367 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 08:01:50,367 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 08:01:50,368 DEBUG [httpcore.http11] response_closed.started
2026-03-07 08:01:50,368 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 08:01:50,370 DEBUG [httpcore.connection] close.started
2026-03-07 08:01:50,370 DEBUG [httpcore.connection] close.complete
2026-03-07 08:01:50,458 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=32 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:50,538 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=33 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:50,608 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=34 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:50,867 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 08:01:51,136 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0EC91EF90>
2026-03-07 08:01:51,137 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 08:01:51,137 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 08:01:51,138 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 08:01:51,138 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 08:01:51,138 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 08:01:56,345 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 07:01:56 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-07 08:01:56,345 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-07 08:01:56,345 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 08:01:56,346 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 08:01:56,347 DEBUG [httpcore.http11] response_closed.started
2026-03-07 08:01:56,347 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 08:01:56,348 DEBUG [httpcore.connection] close.started
2026-03-07 08:01:56,350 DEBUG [httpcore.connection] close.complete
2026-03-07 08:01:56,430 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=35 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:56,485 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=36 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:56,564 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=37 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:56,661 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=38 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:56,769 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=39 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:56,829 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=40 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:01:57,351 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 08:01:57,619 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0ECD94B60>
2026-03-07 08:01:57,623 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 08:01:57,625 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 08:01:57,625 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 08:01:57,626 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 08:01:57,626 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 08:02:08,345 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 07:02:08 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-07 08:02:08,345 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-07 08:02:08,345 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 08:02:08,345 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 08:02:08,346 DEBUG [httpcore.http11] response_closed.started
2026-03-07 08:02:08,346 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 08:02:08,347 DEBUG [httpcore.connection] close.started
2026-03-07 08:02:08,348 DEBUG [httpcore.connection] close.complete
2026-03-07 08:02:08,410 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=41 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:08,466 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=42 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:08,523 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=43 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:08,724 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 08:02:08,993 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0EBE2A300>
2026-03-07 08:02:08,994 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 08:02:08,995 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 08:02:08,995 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 08:02:08,996 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 08:02:08,996 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 08:02:12,106 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 07:02:12 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-07 08:02:12,108 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-07 08:02:12,108 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 08:02:12,108 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 08:02:12,109 DEBUG [httpcore.http11] response_closed.started
2026-03-07 08:02:12,110 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 08:02:12,111 DEBUG [httpcore.connection] close.started
2026-03-07 08:02:12,111 DEBUG [httpcore.connection] close.complete
2026-03-07 08:02:12,183 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=44 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:12,208 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=45 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:12,260 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=46 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:12,307 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=47 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:12,360 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=48 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:12,387 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=49 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:12,582 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 08:02:12,831 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0EC91E4E0>
2026-03-07 08:02:12,832 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 08:02:12,832 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 08:02:12,832 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 08:02:12,832 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 08:02:12,833 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 08:02:13,516 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 07:02:13 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-07 08:02:13,517 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-07 08:02:13,517 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 08:02:13,520 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 08:02:13,520 DEBUG [httpcore.http11] response_closed.started
2026-03-07 08:02:13,521 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 08:02:13,522 DEBUG [httpcore.connection] close.started
2026-03-07 08:02:13,523 DEBUG [httpcore.connection] close.complete
2026-03-07 08:02:13,575 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=50 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:13,639 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=51 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:13,694 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=52 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:13,751 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=53 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:13,782 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=54 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:13,783 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=55 type=agent_step request_id=None
2026-03-07 08:02:13,813 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=56 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:13,885 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=57 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:13,888 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=2411
2026-03-07 08:02:14,080 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 08:02:14,358 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0ECD96000>
2026-03-07 08:02:14,359 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 08:02:14,359 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 08:02:14,359 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 08:02:14,360 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 08:02:14,360 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 08:02:14,790 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Sat, 07 Mar 2026 07:02:14 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-07 08:02:14,790 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-07 08:02:14,794 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 08:02:14,796 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=58 type=token request_id=None
2026-03-07 08:02:14,874 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=59 type=token request_id=None
2026-03-07 08:02:14,953 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=60 type=token request_id=None
2026-03-07 08:02:15,036 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=61 type=token request_id=None
2026-03-07 08:02:15,119 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=62 type=token request_id=None
2026-03-07 08:02:15,203 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=63 type=token request_id=None
2026-03-07 08:02:15,286 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=64 type=token request_id=None
2026-03-07 08:02:15,371 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=65 type=token request_id=None
2026-03-07 08:02:15,453 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=66 type=token request_id=None
2026-03-07 08:02:15,537 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=67 type=token request_id=None
2026-03-07 08:02:15,819 DEBUG [httpcore.http11] response_closed.started
2026-03-07 08:02:15,821 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 08:02:15,874 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=68 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:15,921 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=69 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:15,967 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=70 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:16,169 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-07 08:02:16,172 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
2026-03-07 08:02:16,434 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001A0ECE1A9C0>
2026-03-07 08:02:16,435 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-07 08:02:16,435 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-07 08:02:16,436 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-07 08:02:16,436 DEBUG [httpcore.http11] send_request_body.complete
2026-03-07 08:02:16,436 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-07 08:02:18,225 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Sat, 07 Mar 2026 07:02:18 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-07 08:02:18,226 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-07 08:02:18,227 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-07 08:02:18,227 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-07 08:02:18,228 DEBUG [httpcore.http11] response_closed.started
2026-03-07 08:02:18,229 DEBUG [httpcore.http11] response_closed.complete
2026-03-07 08:02:18,229 DEBUG [httpcore.connection] close.started
2026-03-07 08:02:18,231 DEBUG [httpcore.connection] close.complete
2026-03-07 08:02:18,269 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=71 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:18,322 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=72 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:18,382 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=73 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:18,418 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=74 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:18,435 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=75 type=final request_id=None
2026-03-07 08:02:18,509 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=76 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:18,629 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=77 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:18,785 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=78 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
2026-03-07 08:02:18,785 INFO [app.main] ws_agent_run_done request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af selected_model=qwen3-coder:480b-cloud
2026-03-07 08:02:18,868 DEBUG [app.main] ws_send_event session_id=ac7cc9f4-7fb1-4dcd-a98d-f3578bb893af seq=79 type=lifecycle request_id=943a5f19-9e16-4535-b2b0-b159498d3e2b
