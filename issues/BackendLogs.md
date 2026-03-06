STATE_ENCRYPTION_KEY not set or invalid — using ephemeral key. Encrypted state will NOT survive restart. Set STATE_ENCRYPTION_KEY to a 64-char hex string in .env
SESSION_SIGNING_KEY not set — using ephemeral key. Sessions will be invalidated on restart. Set SESSION_SIGNING_KEY in .env for persistent sessions.
2026-03-06 18:20:43,774 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,009 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,016 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,023 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,032 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,040 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,047 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,056 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,063 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,072 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,079 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,088 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,101 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,110 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,120 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:20:44,134 WARNING [app.services.policy_approval_service] SEC: Policy file loaded without valid HMAC signature: C:\Users\wisni\code\git\ai-agent-starter-kit\backend\state_store\policy_allow_always_rules.json
←[32mINFO←[0m:     Started server process [←[36m15192←[0m]
←[32mINFO←[0m:     Waiting for application startup.
2026-03-06 18:20:44,327 INFO [app.main] startup_paths workspace_root=C:\Users\wisni\code\git\ai-agent-starter-kit\backend memory_dir=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\memory_store orchestrator_state_dir=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\state_store runtime_state_file=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\runtime_state.json
2026-03-06 18:20:44,342 INFO [app.main] startup_memory_reset enabled=True removed_files=58
2026-03-06 18:20:44,559 INFO [app.main] startup_state_reset enabled=True removed_runs=268 removed_snapshots=224
←[32mINFO←[0m:     Application startup complete.
←[32mINFO←[0m:     Uvicorn running on ←[1mhttp://0.0.0.0:8000←[0m (Press CTRL+C to quit)
←[32mINFO←[0m:     ('127.0.0.1', 61863) - "WebSocket /ws/agent" [accepted]
2026-03-06 18:25:38,158 INFO [app.main] ws_connected session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 runtime=api model=qwen3-coder:480b-cloud
2026-03-06 18:25:38,163 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=1 type=status request_id=None
←[32mINFO←[0m:     connection open
2026-03-06 18:25:38,828 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=12 socket_options=None
←[32mINFO←[0m:     127.0.0.1:64535 - "←[1mGET /api/runtime/features HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:63793 - "←[1mGET /api/agents HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:51771 - "←[1mGET /api/presets HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:54083 - "←[1mGET /api/monitoring/schema HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:62792 - "←[1mGET /api/custom-agents HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:64535 - "←[1mOPTIONS /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:64535 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 18:25:39,132 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCFA27ECC0>
2026-03-06 18:25:39,133 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'GET']>
2026-03-06 18:25:39,134 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:25:39,134 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'GET']>
2026-03-06 18:25:39,134 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:25:39,134 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'GET']>
2026-03-06 18:25:39,184 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:25:39 GMT'), (b'Content-Length', b'1223')])
2026-03-06 18:25:39,185 INFO [httpx] HTTP Request: GET http://localhost:11434/api/tags "HTTP/1.1 200 OK"
2026-03-06 18:25:39,187 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'GET']>
2026-03-06 18:25:39,187 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:25:39,188 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:25:39,188 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:25:39,189 DEBUG [httpcore.connection] close.started
2026-03-06 18:25:39,190 DEBUG [httpcore.connection] close.complete
←[32mINFO←[0m:     127.0.0.1:60933 - "←[1mGET /api/runtime/status HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 18:32:22,345 INFO [app.main] ws_message_received request_id=e2739815-8883-40fc-be10-e91a098d6513 session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 type=user_message agent_id=head-agent content_len=120 requested_model=qwen3-coder:480b-cloud
2026-03-06 18:32:22,490 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=2 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,599 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=3 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,691 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=4 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,712 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=5 type=status request_id=None
2026-03-06 18:32:22,752 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=6 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,755 INFO [app.main] ws_request_dispatch request_id=e2739815-8883-40fc-be10-e91a098d6513 session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 runtime=api active_model=qwen3-coder:480b-cloud
2026-03-06 18:32:22,759 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:32:22,760 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:32:22,761 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 18:32:22,761 INFO [app.main] ws_agent_run_start request_id=e2739815-8883-40fc-be10-e91a098d6513 session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 selected_model=qwen3-coder:480b-cloud
2026-03-06 18:32:22,797 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=7 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,831 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=8 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,863 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=9 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,897 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=10 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,912 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=11 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,967 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=12 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:22,997 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=13 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,032 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=14 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,047 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=15 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,076 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=16 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,098 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=17 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,130 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=18 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,153 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=19 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,172 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=20 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,172 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=21 type=status request_id=None
2026-03-06 18:32:23,204 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=22 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:23,534 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:32:23,809 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCFAC4A540>
2026-03-06 18:32:23,810 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:32:23,811 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:32:23,812 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:32:23,812 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:32:23,812 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:32:29,012 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:32:29 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:32:29,012 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:32:29,012 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:32:29,013 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:32:29,013 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:32:29,014 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:32:29,014 DEBUG [httpcore.connection] close.started
2026-03-06 18:32:29,015 DEBUG [httpcore.connection] close.complete
2026-03-06 18:32:29,061 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=23 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,096 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=24 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,122 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=25 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,134 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=26 type=agent_step request_id=None
2026-03-06 18:32:29,175 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=27 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,197 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=28 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,232 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=29 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,271 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=30 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,315 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=31 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,330 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=32 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:29,564 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:32:29,805 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCFA6664B0>
2026-03-06 18:32:29,806 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:32:29,807 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:32:29,808 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:32:29,808 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:32:29,813 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:32:33,065 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:32:33 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:32:33,066 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:32:33,066 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:32:33,066 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:32:33,066 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:32:33,067 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:32:33,067 DEBUG [httpcore.connection] close.started
2026-03-06 18:32:33,068 DEBUG [httpcore.connection] close.complete
2026-03-06 18:32:33,112 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=33 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:33,171 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=34 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:33,177 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=35 type=agent_step request_id=None
2026-03-06 18:32:33,218 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=36 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:33,223 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=37 type=policy_approval_required request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:33,257 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=38 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
←[32mINFO←[0m:     127.0.0.1:52278 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:52278 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:52278 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 18:32:46,278 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=39 type=policy_approval_updated request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:46,328 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=40 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:46,360 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=41 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:46,389 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=42 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:46,408 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=43 type=error request_id=None
2026-03-06 18:32:46,471 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=44 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:46,474 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 13187.0ms)
2026-03-06 18:32:46,474 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=45 type=agent_step request_id=None
2026-03-06 18:32:46,511 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=46 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:46,511 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=47 type=policy_approval_required request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:46,546 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=48 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
←[32mINFO←[0m:     127.0.0.1:52278 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:52278 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 18:32:55,358 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=49 type=policy_approval_updated request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:55,414 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=50 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:55,454 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=51 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:55,478 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=52 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:55,484 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=53 type=error request_id=None
2026-03-06 18:32:55,544 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=54 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:55,546 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 8969.0ms)
2026-03-06 18:32:55,547 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=55 type=agent_step request_id=None
2026-03-06 18:32:55,599 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=56 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:55,600 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=57 type=policy_approval_required request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:55,644 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=58 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
←[32mINFO←[0m:     127.0.0.1:52278 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 18:32:57,383 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=59 type=policy_approval_updated request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:57,436 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=60 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:57,468 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=61 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:57,493 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=62 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:57,497 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=63 type=error request_id=None
2026-03-06 18:32:57,571 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=64 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:57,572 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 1905.0ms)
2026-03-06 18:32:57,634 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=65 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:57,682 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=66 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:32:57,967 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:32:58,236 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCFAC493A0>
2026-03-06 18:32:58,237 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:32:58,238 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:32:58,238 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:32:58,238 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:32:58,242 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:33:24,264 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:33:24 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:33:24,264 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:33:24,264 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:33:24,264 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:33:24,266 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:33:24,266 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:33:24,268 DEBUG [httpcore.connection] close.started
2026-03-06 18:33:24,268 DEBUG [httpcore.connection] close.complete
2026-03-06 18:33:24,335 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=67 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:24,373 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=68 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:24,425 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=69 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:24,462 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=70 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:24,506 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=71 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:24,537 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=72 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:24,862 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:33:25,121 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCFAC4A060>
2026-03-06 18:33:25,123 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:33:25,123 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:33:25,124 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:33:25,124 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:33:25,129 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:33:25,857 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:33:25 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:33:25,858 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:33:25,858 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:33:25,858 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:33:25,859 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:33:25,859 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:33:25,860 DEBUG [httpcore.connection] close.started
2026-03-06 18:33:25,860 DEBUG [httpcore.connection] close.complete
2026-03-06 18:33:25,909 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=73 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:25,958 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=74 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:26,040 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=75 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:26,254 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:33:26,507 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCFA6671D0>
2026-03-06 18:33:26,509 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:33:26,509 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:33:26,509 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:33:26,509 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:33:26,511 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:33:35,616 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:33:35 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:33:35,617 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:33:35,617 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:33:35,618 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:33:35,618 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:33:35,620 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:33:35,621 DEBUG [httpcore.connection] close.started
2026-03-06 18:33:35,621 DEBUG [httpcore.connection] close.complete
2026-03-06 18:33:35,671 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=76 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:35,716 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=77 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:35,762 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=78 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:35,809 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=79 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:35,855 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=80 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:35,877 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=81 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:36,105 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:33:36,375 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCFAC49220>
2026-03-06 18:33:36,385 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:33:36,385 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:33:36,386 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:33:36,386 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:33:36,391 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:33:42,484 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:33:42 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:33:42,485 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:33:42,486 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:33:42,486 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:33:42,487 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:33:42,488 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:33:42,489 DEBUG [httpcore.connection] close.started
2026-03-06 18:33:42,489 DEBUG [httpcore.connection] close.complete
2026-03-06 18:33:42,538 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=82 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:42,599 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=83 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:42,644 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=84 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:42,984 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:33:43,241 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCF5086DB0>
2026-03-06 18:33:43,242 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:33:43,243 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:33:43,244 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:33:43,244 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:33:43,249 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:33:46,777 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:33:46 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:33:46,778 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:33:46,778 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:33:46,779 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:33:46,779 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:33:46,780 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:33:46,781 DEBUG [httpcore.connection] close.started
2026-03-06 18:33:46,781 DEBUG [httpcore.connection] close.complete
2026-03-06 18:33:46,836 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=85 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:46,895 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=86 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:46,918 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=87 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:46,918 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=88 type=agent_step request_id=None
2026-03-06 18:33:46,940 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=89 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:46,986 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=90 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:46,987 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=3970
2026-03-06 18:33:47,278 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:33:47,541 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCFAC4B920>
2026-03-06 18:33:47,543 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:33:47,543 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:33:47,544 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:33:47,544 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:33:47,549 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:33:47,942 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Fri, 06 Mar 2026 17:33:47 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:33:47,942 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:33:47,946 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:33:47,946 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=91 type=token request_id=None
2026-03-06 18:33:47,995 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=92 type=token request_id=None
2026-03-06 18:33:48,050 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=93 type=token request_id=None
2026-03-06 18:33:48,103 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=94 type=token request_id=None
2026-03-06 18:33:48,159 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=95 type=token request_id=None
2026-03-06 18:33:48,212 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=96 type=token request_id=None
2026-03-06 18:33:48,267 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=97 type=token request_id=None
2026-03-06 18:33:48,321 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=98 type=token request_id=None
2026-03-06 18:33:48,376 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=99 type=token request_id=None
2026-03-06 18:33:48,430 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=100 type=token request_id=None
2026-03-06 18:33:48,485 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=101 type=token request_id=None
2026-03-06 18:33:48,541 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=102 type=token request_id=None
2026-03-06 18:33:48,597 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=103 type=token request_id=None
2026-03-06 18:33:48,650 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=104 type=token request_id=None
2026-03-06 18:33:48,706 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=105 type=token request_id=None
2026-03-06 18:33:48,760 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=106 type=token request_id=None
2026-03-06 18:33:48,815 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=107 type=token request_id=None
2026-03-06 18:33:48,869 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=108 type=token request_id=None
2026-03-06 18:33:48,923 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=109 type=token request_id=None
2026-03-06 18:33:48,976 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=110 type=token request_id=None
2026-03-06 18:33:49,136 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=111 type=token request_id=None
2026-03-06 18:33:49,189 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=112 type=token request_id=None
2026-03-06 18:33:49,245 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=113 type=token request_id=None
2026-03-06 18:33:49,299 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=114 type=token request_id=None
2026-03-06 18:33:49,354 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=115 type=token request_id=None
2026-03-06 18:33:49,407 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=116 type=token request_id=None
2026-03-06 18:33:49,462 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=117 type=token request_id=None
2026-03-06 18:33:49,571 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=118 type=token request_id=None
2026-03-06 18:33:49,626 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=119 type=token request_id=None
2026-03-06 18:33:49,681 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=120 type=token request_id=None
2026-03-06 18:33:49,734 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=121 type=token request_id=None
2026-03-06 18:33:49,789 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=122 type=token request_id=None
2026-03-06 18:33:49,843 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=123 type=token request_id=None
2026-03-06 18:33:49,906 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=124 type=token request_id=None
2026-03-06 18:33:49,952 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=125 type=token request_id=None
2026-03-06 18:33:50,007 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=126 type=token request_id=None
2026-03-06 18:33:50,059 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=127 type=token request_id=None
2026-03-06 18:33:50,114 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=128 type=token request_id=None
2026-03-06 18:33:50,167 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=129 type=token request_id=None
2026-03-06 18:33:50,220 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=130 type=token request_id=None
2026-03-06 18:33:50,275 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=131 type=token request_id=None
2026-03-06 18:33:50,328 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=132 type=token request_id=None
2026-03-06 18:33:50,382 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=133 type=token request_id=None
2026-03-06 18:33:50,548 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=134 type=token request_id=None
2026-03-06 18:33:50,602 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=135 type=token request_id=None
2026-03-06 18:33:50,658 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=136 type=token request_id=None
2026-03-06 18:33:50,711 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=137 type=token request_id=None
2026-03-06 18:33:50,764 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=138 type=token request_id=None
2026-03-06 18:33:50,828 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=139 type=token request_id=None
2026-03-06 18:33:50,872 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=140 type=token request_id=None
2026-03-06 18:33:50,926 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=141 type=token request_id=None
2026-03-06 18:33:50,981 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=142 type=token request_id=None
2026-03-06 18:33:51,036 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=143 type=token request_id=None
2026-03-06 18:33:51,090 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=144 type=token request_id=None
2026-03-06 18:33:51,160 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=145 type=token request_id=None
2026-03-06 18:33:51,200 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=146 type=token request_id=None
2026-03-06 18:33:51,256 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=147 type=token request_id=None
2026-03-06 18:33:51,307 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=148 type=token request_id=None
2026-03-06 18:33:51,362 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=149 type=token request_id=None
2026-03-06 18:33:51,418 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=150 type=token request_id=None
2026-03-06 18:33:51,472 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=151 type=token request_id=None
2026-03-06 18:33:51,528 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=152 type=token request_id=None
2026-03-06 18:33:51,581 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=153 type=token request_id=None
2026-03-06 18:33:51,638 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=154 type=token request_id=None
2026-03-06 18:33:51,693 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=155 type=token request_id=None
2026-03-06 18:33:51,747 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=156 type=token request_id=None
2026-03-06 18:33:51,822 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=157 type=token request_id=None
2026-03-06 18:33:51,856 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=158 type=token request_id=None
2026-03-06 18:33:51,911 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=159 type=token request_id=None
2026-03-06 18:33:51,968 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=160 type=token request_id=None
2026-03-06 18:33:52,022 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=161 type=token request_id=None
2026-03-06 18:33:52,076 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=162 type=token request_id=None
2026-03-06 18:33:52,130 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=163 type=token request_id=None
2026-03-06 18:33:52,183 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=164 type=token request_id=None
2026-03-06 18:33:52,239 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=165 type=token request_id=None
2026-03-06 18:33:52,291 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=166 type=token request_id=None
2026-03-06 18:33:52,343 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=167 type=token request_id=None
2026-03-06 18:33:52,399 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=168 type=token request_id=None
2026-03-06 18:33:52,456 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=169 type=token request_id=None
2026-03-06 18:33:52,504 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=170 type=token request_id=None
2026-03-06 18:33:52,558 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=171 type=token request_id=None
2026-03-06 18:33:52,612 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=172 type=token request_id=None
2026-03-06 18:33:52,679 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=173 type=token request_id=None
2026-03-06 18:33:52,729 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=174 type=token request_id=None
2026-03-06 18:33:52,783 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=175 type=token request_id=None
2026-03-06 18:33:52,842 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=176 type=token request_id=None
2026-03-06 18:33:52,899 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=177 type=token request_id=None
2026-03-06 18:33:52,962 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=178 type=token request_id=None
2026-03-06 18:33:53,002 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=179 type=token request_id=None
2026-03-06 18:33:53,057 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=180 type=token request_id=None
2026-03-06 18:33:53,110 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=181 type=token request_id=None
2026-03-06 18:33:53,165 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=182 type=token request_id=None
2026-03-06 18:33:53,222 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=183 type=token request_id=None
2026-03-06 18:33:53,277 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=184 type=token request_id=None
2026-03-06 18:33:53,331 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=185 type=token request_id=None
2026-03-06 18:33:53,385 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=186 type=token request_id=None
2026-03-06 18:33:53,441 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=187 type=token request_id=None
2026-03-06 18:33:53,498 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=188 type=token request_id=None
2026-03-06 18:33:53,549 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=189 type=token request_id=None
2026-03-06 18:33:53,606 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=190 type=token request_id=None
2026-03-06 18:33:53,660 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=191 type=token request_id=None
2026-03-06 18:33:53,730 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=192 type=token request_id=None
2026-03-06 18:33:53,773 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=193 type=token request_id=None
2026-03-06 18:33:53,825 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=194 type=token request_id=None
2026-03-06 18:33:53,880 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=195 type=token request_id=None
2026-03-06 18:33:53,934 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=196 type=token request_id=None
2026-03-06 18:33:53,991 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=197 type=token request_id=None
2026-03-06 18:33:54,043 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=198 type=token request_id=None
2026-03-06 18:33:54,099 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=199 type=token request_id=None
2026-03-06 18:33:54,153 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=200 type=token request_id=None
2026-03-06 18:33:54,209 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=201 type=token request_id=None
2026-03-06 18:33:54,264 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=202 type=token request_id=None
2026-03-06 18:33:54,318 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=203 type=token request_id=None
2026-03-06 18:33:54,373 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=204 type=token request_id=None
2026-03-06 18:33:54,429 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=205 type=token request_id=None
2026-03-06 18:33:54,483 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=206 type=token request_id=None
2026-03-06 18:33:54,537 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=207 type=token request_id=None
2026-03-06 18:33:54,593 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=208 type=token request_id=None
2026-03-06 18:33:54,648 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=209 type=token request_id=None
2026-03-06 18:33:54,703 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=210 type=token request_id=None
2026-03-06 18:33:54,758 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=211 type=token request_id=None
2026-03-06 18:33:54,812 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=212 type=token request_id=None
2026-03-06 18:33:55,145 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=213 type=token request_id=None
2026-03-06 18:33:55,507 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=214 type=token request_id=None
2026-03-06 18:33:55,902 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=215 type=token request_id=None
2026-03-06 18:33:56,058 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=216 type=token request_id=None
2026-03-06 18:33:56,113 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=217 type=token request_id=None
2026-03-06 18:33:56,167 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=218 type=token request_id=None
2026-03-06 18:33:56,222 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=219 type=token request_id=None
2026-03-06 18:33:56,276 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=220 type=token request_id=None
2026-03-06 18:33:56,330 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=221 type=token request_id=None
2026-03-06 18:33:56,384 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=222 type=token request_id=None
2026-03-06 18:33:56,493 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=223 type=token request_id=None
2026-03-06 18:33:56,547 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=224 type=token request_id=None
2026-03-06 18:33:56,606 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=225 type=token request_id=None
2026-03-06 18:33:56,661 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=226 type=token request_id=None
2026-03-06 18:33:56,863 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:33:56,864 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:33:56,905 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=227 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:56,969 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=228 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:57,028 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=229 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:33:57,355 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 18:33:57,361 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
2026-03-06 18:33:57,627 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000002BCF9E44680>
2026-03-06 18:33:57,630 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 18:33:57,631 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 18:33:57,632 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 18:33:57,632 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 18:33:57,633 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 18:34:18,450 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 17:34:18 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 18:34:18,451 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 18:34:18,451 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 18:34:18,451 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 18:34:18,452 DEBUG [httpcore.http11] response_closed.started
2026-03-06 18:34:18,452 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 18:34:18,454 DEBUG [httpcore.connection] close.started
2026-03-06 18:34:18,455 DEBUG [httpcore.connection] close.complete
2026-03-06 18:34:18,479 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=230 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:34:18,557 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=231 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:34:18,621 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=232 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:34:18,663 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=233 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:34:18,674 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=234 type=final request_id=None
2026-03-06 18:34:18,721 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=235 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:34:18,773 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=236 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:34:18,856 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=237 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
2026-03-06 18:34:18,858 INFO [app.main] ws_agent_run_done request_id=e2739815-8883-40fc-be10-e91a098d6513 session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 selected_model=qwen3-coder:480b-cloud
2026-03-06 18:34:18,928 DEBUG [app.main] ws_send_event session_id=b48eb2c9-d240-4926-9dbc-1c8e464f0293 seq=238 type=lifecycle request_id=e2739815-8883-40fc-be10-e91a098d6513
←[32mINFO←[0m:     127.0.0.1:60871 - "←[1mOPTIONS /api/control/runs.audit HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:60871 - "←[1mPOST /api/control/runs.audit HTTP/1.1←[0m" ←[32m200 OK←[0m
