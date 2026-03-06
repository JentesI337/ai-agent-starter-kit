STATE_ENCRYPTION_KEY not set or invalid — using ephemeral key. Encrypted state will NOT survive restart. Set STATE_ENCRYPTION_KEY to a 64-char hex string in .env
SESSION_SIGNING_KEY not set — using ephemeral key. Sessions will be invalidated on restart. Set SESSION_SIGNING_KEY in .env for persistent sessions.
2026-03-06 13:33:05,817 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,071 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,075 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,077 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,080 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,082 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,085 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,088 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,091 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,093 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,096 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,099 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,105 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,111 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,117 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:33:06,125 WARNING [app.services.policy_approval_service] SEC: Policy file loaded without valid HMAC signature: C:\Users\wisni\code\git\ai-agent-starter-kit\backend\state_store\policy_allow_always_rules.json
←[32mINFO←[0m:     Started server process [←[36m12624←[0m]
←[32mINFO←[0m:     Waiting for application startup.
2026-03-06 13:33:06,361 INFO [app.main] startup_paths workspace_root=C:\Users\wisni\code\git\ai-agent-starter-kit\backend memory_dir=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\memory_store orchestrator_state_dir=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\state_store runtime_state_file=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\runtime_state.json
2026-03-06 13:33:06,365 INFO [app.main] startup_memory_reset enabled=True removed_files=4
2026-03-06 13:33:06,376 INFO [app.main] startup_state_reset enabled=True removed_runs=7 removed_snapshots=7
←[32mINFO←[0m:     Application startup complete.
←[32mINFO←[0m:     Uvicorn running on ←[1mhttp://0.0.0.0:8000←[0m (Press CTRL+C to quit)
←[32mINFO←[0m:     ('127.0.0.1', 52949) - "WebSocket /ws/agent" [accepted]
2026-03-06 13:33:46,727 INFO [app.main] ws_connected session_id=d4417931-dbb3-44c8-8c1a-94ff6088f3d4 runtime=api model=qwen3-coder:480b-cloud
2026-03-06 13:33:46,730 DEBUG [app.main] ws_send_event session_id=d4417931-dbb3-44c8-8c1a-94ff6088f3d4 seq=1 type=status request_id=None
←[32mINFO←[0m:     connection open
2026-03-06 13:33:51,368 INFO [app.main] ws_disconnected session_id=d4417931-dbb3-44c8-8c1a-94ff6088f3d4
←[32mINFO←[0m:     connection closed
←[32mINFO←[0m:     ('127.0.0.1', 56417) - "WebSocket /ws/agent" [accepted]
2026-03-06 13:33:52,953 INFO [app.main] ws_connected session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 runtime=api model=qwen3-coder:480b-cloud
2026-03-06 13:33:52,954 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=1 type=status request_id=None
←[32mINFO←[0m:     connection open
2026-03-06 13:33:53,561 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=12 socket_options=None
←[32mINFO←[0m:     127.0.0.1:58215 - "←[1mOPTIONS /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:54539 - "←[1mGET /api/runtime/features HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61420 - "←[1mGET /api/agents HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:50205 - "←[1mGET /api/presets HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:50930 - "←[1mGET /api/monitoring/schema HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:58215 - "←[1mGET /api/custom-agents HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:50930 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 13:33:53,980 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBD9466F0>
2026-03-06 13:33:53,982 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'GET']>
2026-03-06 13:33:53,983 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:33:53,983 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'GET']>
2026-03-06 13:33:53,983 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:33:53,983 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'GET']>
2026-03-06 13:33:54,766 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:33:54 GMT'), (b'Content-Length', b'1223')])
2026-03-06 13:33:54,768 INFO [httpx] HTTP Request: GET http://localhost:11434/api/tags "HTTP/1.1 200 OK"
2026-03-06 13:33:54,769 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'GET']>
2026-03-06 13:33:54,770 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:33:54,771 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:33:54,771 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:33:54,774 DEBUG [httpcore.connection] close.started
2026-03-06 13:33:54,775 DEBUG [httpcore.connection] close.complete
←[32mINFO←[0m:     127.0.0.1:63593 - "←[1mGET /api/runtime/status HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 13:37:16,840 INFO [app.main] ws_message_received request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7 session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 type=user_message agent_id=head-agent content_len=171 requested_model=qwen3-coder:480b-cloud
2026-03-06 13:37:16,994 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=2 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,081 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=3 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,169 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=4 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,274 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=5 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,274 INFO [app.main] ws_request_dispatch request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7 session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 runtime=api active_model=qwen3-coder:480b-cloud
2026-03-06 13:37:17,277 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:37:17,279 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:37:17,281 DEBUG [app.url_validator] llm_base_url_local host=localhost (allowed for local dev)
2026-03-06 13:37:17,281 INFO [app.main] ws_agent_run_start request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7 session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 selected_model=qwen3-coder:480b-cloud
2026-03-06 13:37:17,373 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=6 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,437 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=7 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,506 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=8 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,556 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=9 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,587 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=10 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,684 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=11 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,751 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=12 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,823 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=13 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,854 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=14 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,908 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=15 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:17,949 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=16 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:18,005 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=17 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:18,043 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=18 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:18,084 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=19 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:18,087 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=20 type=status request_id=None
2026-03-06 13:37:18,149 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=21 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:18,517 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:37:18,799 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE422E10>
2026-03-06 13:37:18,800 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:37:18,801 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:37:18,802 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:37:18,803 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:37:18,804 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:37:21,661 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:37:21 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:37:21,662 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:37:21,663 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:37:21,663 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:37:21,664 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:37:21,664 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:37:21,666 DEBUG [httpcore.connection] close.started
2026-03-06 13:37:21,667 DEBUG [httpcore.connection] close.complete
2026-03-06 13:37:21,736 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=22 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:21,781 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=23 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:21,822 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=24 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:21,854 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=25 type=agent_step request_id=None
2026-03-06 13:37:21,903 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=26 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:21,938 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=27 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:22,002 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=28 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:22,069 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=29 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:22,132 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=30 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:22,170 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=31 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:22,498 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:37:22,758 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE423BF0>
2026-03-06 13:37:22,760 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:37:22,760 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:37:22,761 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:37:22,761 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:37:22,762 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:37:26,732 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:37:26 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:37:26,732 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:37:26,733 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:37:26,733 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:37:26,734 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:37:26,734 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:37:26,737 DEBUG [httpcore.connection] close.started
2026-03-06 13:37:26,738 DEBUG [httpcore.connection] close.complete
2026-03-06 13:37:26,807 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=32 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:26,934 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=33 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:27,029 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=34 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:27,036 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=35 type=agent_step request_id=None
2026-03-06 13:37:27,147 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=36 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:27,243 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=37 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:37:27,389 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=38 type=subrun_status request_id=None
2026-03-06 13:37:27,573 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=39 type=subrun_status request_id=None
2026-03-06 13:37:27,766 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=40 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:27,881 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=41 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:27,972 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=42 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,062 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=43 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,121 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=44 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,341 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=45 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,428 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=46 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,517 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=47 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,557 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=48 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,637 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=49 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,716 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=50 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,823 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=51 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:28,902 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=52 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:29,020 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=53 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:29,022 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=54 type=status request_id=None
2026-03-06 13:37:29,196 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=55 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:29,647 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:37:29,914 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE3FE990>
2026-03-06 13:37:29,917 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:37:29,918 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:37:29,918 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:37:29,918 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:37:29,919 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:37:45,328 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:37:45 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:37:45,328 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:37:45,329 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:37:45,329 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:37:45,330 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:37:45,331 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:37:45,331 DEBUG [httpcore.connection] close.started
2026-03-06 13:37:45,332 DEBUG [httpcore.connection] close.complete
2026-03-06 13:37:45,403 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=56 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:45,448 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=57 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:45,487 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=58 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:45,505 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=59 type=agent_step request_id=None
2026-03-06 13:37:45,571 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=60 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:45,621 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=61 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:45,688 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=62 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:45,754 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=63 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:45,814 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=64 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:45,847 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=65 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:46,144 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:37:46,418 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE3FD190>
2026-03-06 13:37:46,420 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:37:46,420 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:37:46,421 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:37:46,422 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:37:46,425 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:37:49,457 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:37:49 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:37:49,457 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:37:49,458 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:37:49,458 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:37:49,459 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:37:49,459 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:37:49,460 DEBUG [httpcore.connection] close.started
2026-03-06 13:37:49,460 DEBUG [httpcore.connection] close.complete
2026-03-06 13:37:49,528 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=66 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:49,600 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=67 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:49,612 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=68 type=agent_step request_id=None
2026-03-06 13:37:49,678 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=69 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:49,719 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=70 type=error request_id=None
2026-03-06 13:37:49,781 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=71 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:49,801 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 31.0ms)
2026-03-06 13:37:49,801 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=72 type=agent_step request_id=None
2026-03-06 13:37:49,854 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=73 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:49,864 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=74 type=error request_id=None
2026-03-06 13:37:49,933 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=75 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:49,933 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 15.0ms)
2026-03-06 13:37:49,934 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=76 type=agent_step request_id=None
2026-03-06 13:37:49,992 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=77 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:49,997 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=78 type=error request_id=None
2026-03-06 13:37:50,080 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=79 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:50,081 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 0.0ms)
2026-03-06 13:37:50,147 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=80 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:50,213 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=81 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:50,587 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:37:50,855 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE422090>
2026-03-06 13:37:50,857 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:37:50,857 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:37:50,858 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:37:50,858 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:37:50,859 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:37:56,023 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:37:56 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:37:56,024 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:37:56,024 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:37:56,025 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:37:56,026 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:37:56,026 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:37:56,027 DEBUG [httpcore.connection] close.started
2026-03-06 13:37:56,028 DEBUG [httpcore.connection] close.complete
2026-03-06 13:37:56,095 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=82 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:56,140 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=83 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:56,199 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=84 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:56,257 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=85 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:56,316 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=86 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:56,353 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=87 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:37:56,638 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:37:56,911 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE434F80>
2026-03-06 13:37:56,911 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:37:56,912 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:37:56,913 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:37:56,914 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:37:56,918 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:38:00,985 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:38:00 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:38:00,986 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:38:00,986 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:38:00,986 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:38:00,987 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:38:00,988 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:38:00,990 DEBUG [httpcore.connection] close.started
2026-03-06 13:38:00,990 DEBUG [httpcore.connection] close.complete
2026-03-06 13:38:01,083 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=88 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,161 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=89 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,161 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=90 type=agent_step request_id=None
2026-03-06 13:38:01,233 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=91 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,240 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=92 type=error request_id=None
2026-03-06 13:38:01,331 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=93 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,332 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 15.0ms)
2026-03-06 13:38:01,332 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=94 type=agent_step request_id=None
2026-03-06 13:38:01,394 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=95 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,401 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=96 type=error request_id=None
2026-03-06 13:38:01,479 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=97 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,480 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 0.0ms)
2026-03-06 13:38:01,481 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=98 type=agent_step request_id=None
2026-03-06 13:38:01,553 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=99 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,558 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=100 type=error request_id=None
2026-03-06 13:38:01,659 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=101 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,663 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 0.0ms)
2026-03-06 13:38:01,720 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=102 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,787 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=103 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,846 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=104 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,879 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=105 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,879 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=106 type=agent_step request_id=None
2026-03-06 13:38:01,917 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=107 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,985 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=108 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:01,986 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=3261
2026-03-06 13:38:02,283 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:38:02,563 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE4376E0>
2026-03-06 13:38:02,564 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:38:02,564 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:38:02,564 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:38:02,566 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:38:02,566 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:38:03,012 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Fri, 06 Mar 2026 12:38:03 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:38:03,013 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:38:03,016 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:38:03,017 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=109 type=token request_id=None
2026-03-06 13:38:03,256 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=110 type=token request_id=None
2026-03-06 13:38:03,258 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=111 type=token request_id=None
2026-03-06 13:38:03,294 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=112 type=token request_id=None
2026-03-06 13:38:03,365 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=113 type=token request_id=None
2026-03-06 13:38:03,435 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=114 type=token request_id=None
2026-03-06 13:38:03,519 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=115 type=token request_id=None
2026-03-06 13:38:03,576 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=116 type=token request_id=None
2026-03-06 13:38:03,645 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=117 type=token request_id=None
2026-03-06 13:38:03,717 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=118 type=token request_id=None
2026-03-06 13:38:03,788 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=119 type=token request_id=None
2026-03-06 13:38:03,856 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=120 type=token request_id=None
2026-03-06 13:38:03,928 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=121 type=token request_id=None
2026-03-06 13:38:03,998 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=122 type=token request_id=None
2026-03-06 13:38:04,070 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=123 type=token request_id=None
2026-03-06 13:38:04,144 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=124 type=token request_id=None
2026-03-06 13:38:04,218 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=125 type=token request_id=None
2026-03-06 13:38:04,290 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=126 type=token request_id=None
2026-03-06 13:38:04,359 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=127 type=token request_id=None
2026-03-06 13:38:04,430 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=128 type=token request_id=None
2026-03-06 13:38:04,501 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=129 type=token request_id=None
2026-03-06 13:38:04,672 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=130 type=token request_id=None
2026-03-06 13:38:04,740 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=131 type=token request_id=None
2026-03-06 13:38:04,810 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=132 type=token request_id=None
2026-03-06 13:38:04,879 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=133 type=token request_id=None
2026-03-06 13:38:04,950 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=134 type=token request_id=None
2026-03-06 13:38:05,209 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=135 type=token request_id=None
2026-03-06 13:38:05,210 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=136 type=token request_id=None
2026-03-06 13:38:05,220 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=137 type=token request_id=None
2026-03-06 13:38:05,230 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=138 type=token request_id=None
2026-03-06 13:38:05,301 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=139 type=token request_id=None
2026-03-06 13:38:05,459 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=140 type=token request_id=None
2026-03-06 13:38:05,532 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=141 type=token request_id=None
2026-03-06 13:38:05,605 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=142 type=token request_id=None
2026-03-06 13:38:05,676 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=143 type=token request_id=None
2026-03-06 13:38:05,748 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=144 type=token request_id=None
2026-03-06 13:38:05,821 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=145 type=token request_id=None
2026-03-06 13:38:05,891 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=146 type=token request_id=None
2026-03-06 13:38:05,963 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=147 type=token request_id=None
2026-03-06 13:38:06,036 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=148 type=token request_id=None
2026-03-06 13:38:06,108 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=149 type=token request_id=None
2026-03-06 13:38:06,182 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=150 type=token request_id=None
2026-03-06 13:38:06,250 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=151 type=token request_id=None
2026-03-06 13:38:06,323 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=152 type=token request_id=None
2026-03-06 13:38:06,394 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=153 type=token request_id=None
2026-03-06 13:38:06,465 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=154 type=token request_id=None
2026-03-06 13:38:06,539 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=155 type=token request_id=None
2026-03-06 13:38:06,609 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=156 type=token request_id=None
2026-03-06 13:38:06,681 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=157 type=token request_id=None
2026-03-06 13:38:06,752 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=158 type=token request_id=None
2026-03-06 13:38:06,823 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=159 type=token request_id=None
2026-03-06 13:38:06,899 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=160 type=token request_id=None
2026-03-06 13:38:06,969 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=161 type=token request_id=None
2026-03-06 13:38:07,160 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=162 type=token request_id=None
2026-03-06 13:38:07,161 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=163 type=token request_id=None
2026-03-06 13:38:07,195 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=164 type=token request_id=None
2026-03-06 13:38:07,267 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=165 type=token request_id=None
2026-03-06 13:38:07,460 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:38:07,469 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:38:07,540 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=166 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:07,855 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:38:07,856 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
2026-03-06 13:38:08,103 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE421B50>
2026-03-06 13:38:08,104 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:38:08,105 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:38:08,105 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:38:08,105 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:38:08,108 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:38:13,588 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:38:13 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:38:13,588 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:38:13,589 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:38:13,589 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:38:13,590 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:38:13,590 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:38:13,591 DEBUG [httpcore.connection] close.started
2026-03-06 13:38:13,591 DEBUG [httpcore.connection] close.complete
2026-03-06 13:38:13,673 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=167 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:13,924 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=168 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:14,185 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:38:14,446 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE3FFE30>
2026-03-06 13:38:14,450 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:38:14,451 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:38:14,451 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:38:14,451 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:38:14,452 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:38:25,173 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:38:25 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:38:25,175 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:38:25,175 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:38:25,176 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:38:25,176 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:38:25,177 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:38:25,178 DEBUG [httpcore.connection] close.started
2026-03-06 13:38:25,179 DEBUG [httpcore.connection] close.complete
2026-03-06 13:38:25,219 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=169 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:25,314 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=170 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:25,315 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=4070
2026-03-06 13:38:25,553 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:38:25,820 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBD838050>
2026-03-06 13:38:25,821 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:38:25,822 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:38:25,822 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:38:25,822 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:38:25,823 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:38:26,869 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Fri, 06 Mar 2026 12:38:26 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:38:26,871 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:38:26,871 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:38:26,871 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=171 type=token request_id=None
2026-03-06 13:38:26,872 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=172 type=token request_id=None
2026-03-06 13:38:26,916 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=173 type=token request_id=None
2026-03-06 13:38:27,010 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=174 type=token request_id=None
2026-03-06 13:38:27,183 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=175 type=token request_id=None
2026-03-06 13:38:27,184 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=176 type=token request_id=None
2026-03-06 13:38:27,249 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=177 type=token request_id=None
2026-03-06 13:38:27,329 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=178 type=token request_id=None
2026-03-06 13:38:27,410 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=179 type=token request_id=None
2026-03-06 13:38:27,488 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=180 type=token request_id=None
2026-03-06 13:38:27,562 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=181 type=token request_id=None
2026-03-06 13:38:27,639 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=182 type=token request_id=None
2026-03-06 13:38:27,729 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=183 type=token request_id=None
2026-03-06 13:38:27,789 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=184 type=token request_id=None
2026-03-06 13:38:27,865 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=185 type=token request_id=None
2026-03-06 13:38:27,940 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=186 type=token request_id=None
2026-03-06 13:38:28,113 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=187 type=token request_id=None
2026-03-06 13:38:28,188 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=188 type=token request_id=None
2026-03-06 13:38:28,268 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=189 type=token request_id=None
2026-03-06 13:38:28,344 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=190 type=token request_id=None
2026-03-06 13:38:28,420 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=191 type=token request_id=None
2026-03-06 13:38:28,588 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=192 type=token request_id=None
2026-03-06 13:38:28,664 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=193 type=token request_id=None
2026-03-06 13:38:28,741 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=194 type=token request_id=None
2026-03-06 13:38:28,819 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=195 type=token request_id=None
2026-03-06 13:38:28,890 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=196 type=token request_id=None
2026-03-06 13:38:28,966 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=197 type=token request_id=None
2026-03-06 13:38:29,042 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=198 type=token request_id=None
2026-03-06 13:38:29,193 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=199 type=token request_id=None
2026-03-06 13:38:29,195 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=200 type=token request_id=None
2026-03-06 13:38:29,266 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=201 type=token request_id=None
2026-03-06 13:38:29,341 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=202 type=token request_id=None
2026-03-06 13:38:29,416 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=203 type=token request_id=None
2026-03-06 13:38:29,495 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=204 type=token request_id=None
2026-03-06 13:38:29,566 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=205 type=token request_id=None
2026-03-06 13:38:29,645 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=206 type=token request_id=None
2026-03-06 13:38:29,718 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=207 type=token request_id=None
2026-03-06 13:38:30,072 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=208 type=token request_id=None
2026-03-06 13:38:30,449 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=209 type=token request_id=None
2026-03-06 13:38:30,862 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=210 type=token request_id=None
2026-03-06 13:38:31,034 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=211 type=token request_id=None
2026-03-06 13:38:31,496 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=212 type=token request_id=None
2026-03-06 13:38:31,984 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=213 type=token request_id=None
2026-03-06 13:38:32,486 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=214 type=token request_id=None
2026-03-06 13:38:32,665 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=215 type=token request_id=None
2026-03-06 13:38:32,743 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=216 type=token request_id=None
2026-03-06 13:38:32,818 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=217 type=token request_id=None
2026-03-06 13:38:32,894 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=218 type=token request_id=None
2026-03-06 13:38:32,969 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=219 type=token request_id=None
2026-03-06 13:38:33,198 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=220 type=token request_id=None
2026-03-06 13:38:33,198 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=221 type=token request_id=None
2026-03-06 13:38:33,199 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=222 type=token request_id=None
2026-03-06 13:38:33,379 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=223 type=token request_id=None
2026-03-06 13:38:33,626 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=224 type=token request_id=None
2026-03-06 13:38:33,813 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=225 type=token request_id=None
2026-03-06 13:38:33,889 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=226 type=token request_id=None
2026-03-06 13:38:33,967 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=227 type=token request_id=None
2026-03-06 13:38:34,043 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=228 type=token request_id=None
2026-03-06 13:38:34,124 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=229 type=token request_id=None
2026-03-06 13:38:34,196 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=230 type=token request_id=None
2026-03-06 13:38:34,271 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=231 type=token request_id=None
2026-03-06 13:38:34,351 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=232 type=token request_id=None
2026-03-06 13:38:34,424 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=233 type=token request_id=None
2026-03-06 13:38:34,500 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=234 type=token request_id=None
2026-03-06 13:38:34,580 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=235 type=token request_id=None
2026-03-06 13:38:34,655 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=236 type=token request_id=None
2026-03-06 13:38:34,731 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=237 type=token request_id=None
2026-03-06 13:38:34,806 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=238 type=token request_id=None
2026-03-06 13:38:34,893 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=239 type=token request_id=None
2026-03-06 13:38:34,968 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=240 type=token request_id=None
2026-03-06 13:38:35,157 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=241 type=token request_id=None
2026-03-06 13:38:35,157 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=242 type=token request_id=None
2026-03-06 13:38:35,200 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=243 type=token request_id=None
2026-03-06 13:38:35,277 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=244 type=token request_id=None
2026-03-06 13:38:35,353 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=245 type=token request_id=None
2026-03-06 13:38:35,435 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=246 type=token request_id=None
2026-03-06 13:38:35,628 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:38:35,629 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:38:35,700 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=247 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:36,033 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:38:36,036 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
2026-03-06 13:38:36,295 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBD8ED820>
2026-03-06 13:38:36,297 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:38:36,298 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:38:36,298 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:38:36,298 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:38:36,303 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:38:39,626 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:38:39 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:38:39,627 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:38:39,628 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:38:39,628 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:38:39,629 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:38:39,630 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:38:39,631 DEBUG [httpcore.connection] close.started
2026-03-06 13:38:39,632 DEBUG [httpcore.connection] close.complete
2026-03-06 13:38:39,730 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=248 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:39,820 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=249 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:39,888 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=250 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:39,965 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=251 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:40,011 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=252 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:40,025 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=253 type=final request_id=None
2026-03-06 13:38:40,104 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=254 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:40,171 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=255 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:40,281 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7-subrun-46df9f42 seq=256 type=lifecycle request_id=46df9f42-645f-47e4-adc2-34f6a800d9fb
2026-03-06 13:38:40,372 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=257 type=subrun_status request_id=None
2026-03-06 13:38:40,373 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=258 type=subrun_announce request_id=None
2026-03-06 13:38:40,581 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=259 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:40,675 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=260 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:40,716 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=261 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:40,717 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'spawn_subrun' (success=True, 73375.0ms)
2026-03-06 13:38:40,755 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=262 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:40,797 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=263 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:41,125 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:38:41,379 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBD8399D0>
2026-03-06 13:38:41,380 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:38:41,380 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:38:41,381 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:38:41,382 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:38:41,382 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:38:44,007 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:38:44 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:38:44,007 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:38:44,007 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:38:44,007 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:38:44,008 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:38:44,010 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:38:44,010 DEBUG [httpcore.connection] close.started
2026-03-06 13:38:44,011 DEBUG [httpcore.connection] close.complete
2026-03-06 13:38:44,075 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=264 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:44,106 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=265 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:44,166 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=266 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:44,205 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=267 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:44,250 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=268 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:44,272 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=269 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:44,585 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:38:44,854 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE3FEC90>
2026-03-06 13:38:44,855 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:38:44,857 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:38:44,857 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:38:44,857 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:38:44,862 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:38:45,654 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:38:45 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:38:45,655 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:38:45,655 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:38:45,656 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:38:45,656 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:38:45,656 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:38:45,657 DEBUG [httpcore.connection] close.started
2026-03-06 13:38:45,658 DEBUG [httpcore.connection] close.complete
2026-03-06 13:38:45,711 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=270 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:45,765 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=271 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:45,807 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=272 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:38:46,089 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:38:46,352 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBD838F80>
2026-03-06 13:38:46,362 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:38:46,362 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:38:46,363 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:38:46,364 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:38:46,368 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:39:02,800 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:39:02 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:39:02,800 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:39:02,801 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:39:02,802 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:39:02,802 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:39:02,802 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:39:02,803 DEBUG [httpcore.connection] close.started
2026-03-06 13:39:02,803 DEBUG [httpcore.connection] close.complete
2026-03-06 13:39:02,922 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=273 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:02,953 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=274 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:03,024 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=275 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:03,071 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=276 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:03,125 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=277 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:03,164 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=278 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:03,500 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:39:03,749 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBD838FE0>
2026-03-06 13:39:03,751 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:39:03,751 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:39:03,752 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:39:03,752 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:39:03,755 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:39:06,538 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:39:06 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:39:06,539 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:39:06,540 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:39:06,540 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:39:06,540 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:39:06,541 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:39:06,542 DEBUG [httpcore.connection] close.started
2026-03-06 13:39:06,543 DEBUG [httpcore.connection] close.complete
2026-03-06 13:39:06,595 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=279 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:06,653 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=280 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:06,655 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=281 type=error request_id=None
2026-03-06 13:39:06,715 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=282 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:06,719 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=283 type=agent_step request_id=None
2026-03-06 13:39:06,779 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=284 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:06,781 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=285 type=policy_approval_required request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:06,812 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=286 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 13:39:36,854 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=287 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:36,909 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=288 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:36,910 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=289 type=error request_id=None
2026-03-06 13:39:36,975 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=290 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:36,977 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 30125.0ms)
2026-03-06 13:39:36,978 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=291 type=agent_step request_id=None
2026-03-06 13:39:37,033 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=292 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:37,037 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=293 type=policy_approval_required request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:39:37,098 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=294 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 13:40:00,690 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=295 type=policy_approval_updated request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:00,743 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=296 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:00,774 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=297 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 13:40:07,147 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=298 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:07,190 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=299 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:07,191 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=300 type=error request_id=None
2026-03-06 13:40:07,257 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=301 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:07,260 DEBUG [app.services.learning_loop] learning_loop: recorded outcome for 'run_command' (success=False, 30141.0ms)
2026-03-06 13:40:07,311 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=302 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:07,371 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=303 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:07,699 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:40:07,963 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE420500>
2026-03-06 13:40:07,964 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:40:07,965 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:40:07,965 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:40:07,967 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:40:07,967 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
←[32mINFO←[0m:     127.0.0.1:61586 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-06 13:40:11,703 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:40:11 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:40:11,706 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:40:11,706 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:40:11,706 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:40:11,716 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:40:11,716 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:40:11,718 DEBUG [httpcore.connection] close.started
2026-03-06 13:40:11,718 DEBUG [httpcore.connection] close.complete
2026-03-06 13:40:11,826 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=304 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:11,884 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=305 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:11,915 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=306 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:11,916 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=307 type=agent_step request_id=None
2026-03-06 13:40:11,943 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=308 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:12,003 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=309 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:12,004 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=4333
2026-03-06 13:40:12,326 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:40:12,594 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBDE5C7A0>
2026-03-06 13:40:12,595 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:40:12,596 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:40:12,596 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:40:12,596 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:40:12,600 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:40:12,994 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Fri, 06 Mar 2026 12:40:12 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:40:12,994 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:40:12,996 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:40:12,996 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=310 type=token request_id=None
2026-03-06 13:40:13,206 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=311 type=token request_id=None
2026-03-06 13:40:13,207 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=312 type=token request_id=None
2026-03-06 13:40:13,208 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=313 type=token request_id=None
2026-03-06 13:40:13,209 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=314 type=token request_id=None
2026-03-06 13:40:13,209 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=315 type=token request_id=None
2026-03-06 13:40:13,236 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=316 type=token request_id=None
2026-03-06 13:40:13,270 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=317 type=token request_id=None
2026-03-06 13:40:13,306 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=318 type=token request_id=None
2026-03-06 13:40:13,340 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=319 type=token request_id=None
2026-03-06 13:40:13,376 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=320 type=token request_id=None
2026-03-06 13:40:13,410 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=321 type=token request_id=None
2026-03-06 13:40:13,444 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=322 type=token request_id=None
2026-03-06 13:40:13,491 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=323 type=token request_id=None
2026-03-06 13:40:13,514 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=324 type=token request_id=None
2026-03-06 13:40:13,549 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=325 type=token request_id=None
2026-03-06 13:40:13,585 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=326 type=token request_id=None
2026-03-06 13:40:13,620 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=327 type=token request_id=None
2026-03-06 13:40:13,654 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=328 type=token request_id=None
2026-03-06 13:40:13,688 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=329 type=token request_id=None
2026-03-06 13:40:13,723 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=330 type=token request_id=None
2026-03-06 13:40:13,758 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=331 type=token request_id=None
2026-03-06 13:40:13,794 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=332 type=token request_id=None
2026-03-06 13:40:13,829 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=333 type=token request_id=None
2026-03-06 13:40:13,867 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=334 type=token request_id=None
2026-03-06 13:40:13,900 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=335 type=token request_id=None
2026-03-06 13:40:13,935 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=336 type=token request_id=None
2026-03-06 13:40:13,972 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=337 type=token request_id=None
2026-03-06 13:40:14,006 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=338 type=token request_id=None
2026-03-06 13:40:14,041 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=339 type=token request_id=None
2026-03-06 13:40:14,076 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=340 type=token request_id=None
2026-03-06 13:40:14,112 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=341 type=token request_id=None
2026-03-06 13:40:14,150 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=342 type=token request_id=None
2026-03-06 13:40:14,181 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=343 type=token request_id=None
2026-03-06 13:40:14,213 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=344 type=token request_id=None
2026-03-06 13:40:14,245 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=345 type=token request_id=None
2026-03-06 13:40:14,276 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=346 type=token request_id=None
2026-03-06 13:40:14,306 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=347 type=token request_id=None
2026-03-06 13:40:14,338 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=348 type=token request_id=None
2026-03-06 13:40:14,370 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=349 type=token request_id=None
2026-03-06 13:40:14,402 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=350 type=token request_id=None
2026-03-06 13:40:14,434 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=351 type=token request_id=None
2026-03-06 13:40:14,468 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=352 type=token request_id=None
2026-03-06 13:40:14,497 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=353 type=token request_id=None
2026-03-06 13:40:14,530 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=354 type=token request_id=None
2026-03-06 13:40:14,562 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=355 type=token request_id=None
2026-03-06 13:40:14,595 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=356 type=token request_id=None
2026-03-06 13:40:14,627 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=357 type=token request_id=None
2026-03-06 13:40:14,660 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=358 type=token request_id=None
2026-03-06 13:40:14,691 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=359 type=token request_id=None
2026-03-06 13:40:14,723 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=360 type=token request_id=None
2026-03-06 13:40:14,754 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=361 type=token request_id=None
2026-03-06 13:40:14,786 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=362 type=token request_id=None
2026-03-06 13:40:14,818 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=363 type=token request_id=None
2026-03-06 13:40:14,851 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=364 type=token request_id=None
2026-03-06 13:40:14,883 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=365 type=token request_id=None
2026-03-06 13:40:14,914 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=366 type=token request_id=None
2026-03-06 13:40:14,947 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=367 type=token request_id=None
2026-03-06 13:40:14,998 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=368 type=token request_id=None
2026-03-06 13:40:15,013 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=369 type=token request_id=None
2026-03-06 13:40:15,193 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=370 type=token request_id=None
2026-03-06 13:40:15,193 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=371 type=token request_id=None
2026-03-06 13:40:15,193 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=372 type=token request_id=None
2026-03-06 13:40:15,194 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=373 type=token request_id=None
2026-03-06 13:40:15,194 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=374 type=token request_id=None
2026-03-06 13:40:15,201 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=375 type=token request_id=None
2026-03-06 13:40:15,234 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=376 type=token request_id=None
2026-03-06 13:40:15,266 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=377 type=token request_id=None
2026-03-06 13:40:15,298 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=378 type=token request_id=None
2026-03-06 13:40:15,330 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=379 type=token request_id=None
2026-03-06 13:40:15,363 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=380 type=token request_id=None
2026-03-06 13:40:15,394 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=381 type=token request_id=None
2026-03-06 13:40:15,431 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=382 type=token request_id=None
2026-03-06 13:40:15,459 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=383 type=token request_id=None
2026-03-06 13:40:15,492 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=384 type=token request_id=None
2026-03-06 13:40:15,750 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:40:15,752 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:40:15,835 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=385 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:15,895 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=386 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:15,944 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=387 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:16,270 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:40:16,273 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
2026-03-06 13:40:16,541 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE4344D0>
2026-03-06 13:40:16,542 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:40:16,543 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:40:16,544 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:40:16,544 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:40:16,548 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:40:23,712 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Fri, 06 Mar 2026 12:40:23 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:40:23,714 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:40:23,714 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:40:23,715 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-06 13:40:23,716 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:40:23,716 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:40:23,718 DEBUG [httpcore.connection] close.started
2026-03-06 13:40:23,718 DEBUG [httpcore.connection] close.complete
2026-03-06 13:40:23,752 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=388 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:23,822 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=389 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:23,823 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=5098
2026-03-06 13:40:24,108 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-06 13:40:24,351 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x0000023CBE240320>
2026-03-06 13:40:24,352 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-06 13:40:24,353 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-06 13:40:24,354 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-06 13:40:24,354 DEBUG [httpcore.http11] send_request_body.complete
2026-03-06 13:40:24,359 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-06 13:40:24,736 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Fri, 06 Mar 2026 12:40:24 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-06 13:40:24,736 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-06 13:40:24,736 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-06 13:40:24,737 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=390 type=token request_id=None
2026-03-06 13:40:24,888 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=391 type=token request_id=None
2026-03-06 13:40:24,967 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=392 type=token request_id=None
2026-03-06 13:40:25,163 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=393 type=token request_id=None
2026-03-06 13:40:25,165 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=394 type=token request_id=None
2026-03-06 13:40:25,206 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=395 type=token request_id=None
2026-03-06 13:40:25,286 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=396 type=token request_id=None
2026-03-06 13:40:25,364 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=397 type=token request_id=None
2026-03-06 13:40:25,446 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=398 type=token request_id=None
2026-03-06 13:40:25,523 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=399 type=token request_id=None
2026-03-06 13:40:25,603 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=400 type=token request_id=None
2026-03-06 13:40:25,684 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=401 type=token request_id=None
2026-03-06 13:40:25,778 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=402 type=token request_id=None
2026-03-06 13:40:25,842 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=403 type=token request_id=None
2026-03-06 13:40:25,923 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=404 type=token request_id=None
2026-03-06 13:40:26,002 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=405 type=token request_id=None
2026-03-06 13:40:26,359 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=406 type=token request_id=None
2026-03-06 13:40:26,534 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=407 type=token request_id=None
2026-03-06 13:40:26,613 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=408 type=token request_id=None
2026-03-06 13:40:26,690 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=409 type=token request_id=None
2026-03-06 13:40:26,769 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=410 type=token request_id=None
2026-03-06 13:40:26,854 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=411 type=token request_id=None
2026-03-06 13:40:26,929 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=412 type=token request_id=None
2026-03-06 13:40:27,018 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=413 type=token request_id=None
2026-03-06 13:40:27,188 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=414 type=token request_id=None
2026-03-06 13:40:27,190 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=415 type=token request_id=None
2026-03-06 13:40:27,251 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=416 type=token request_id=None
2026-03-06 13:40:27,332 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=417 type=token request_id=None
2026-03-06 13:40:27,411 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=418 type=token request_id=None
2026-03-06 13:40:27,489 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=419 type=token request_id=None
2026-03-06 13:40:27,569 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=420 type=token request_id=None
2026-03-06 13:40:27,651 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=421 type=token request_id=None
2026-03-06 13:40:27,736 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=422 type=token request_id=None
2026-03-06 13:40:27,816 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=423 type=token request_id=None
2026-03-06 13:40:28,188 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=424 type=token request_id=None
2026-03-06 13:40:28,584 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=425 type=token request_id=None
2026-03-06 13:40:29,030 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=426 type=token request_id=None
2026-03-06 13:40:29,481 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=427 type=token request_id=None
2026-03-06 13:40:29,982 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=428 type=token request_id=None
2026-03-06 13:40:30,515 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=429 type=token request_id=None
2026-03-06 13:40:31,251 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=430 type=token request_id=None
2026-03-06 13:40:31,685 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=431 type=token request_id=None
2026-03-06 13:40:32,328 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=432 type=token request_id=None
2026-03-06 13:40:33,216 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=433 type=token request_id=None
2026-03-06 13:40:33,723 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=434 type=token request_id=None
2026-03-06 13:40:34,494 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=435 type=token request_id=None
2026-03-06 13:40:35,220 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=436 type=token request_id=None
2026-03-06 13:40:35,554 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=437 type=token request_id=None
2026-03-06 13:40:35,975 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=438 type=token request_id=None
2026-03-06 13:40:36,351 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=439 type=token request_id=None
2026-03-06 13:40:36,757 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=440 type=token request_id=None
2026-03-06 13:40:37,196 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=441 type=token request_id=None
2026-03-06 13:40:37,671 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=442 type=token request_id=None
2026-03-06 13:40:38,168 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=443 type=token request_id=None
2026-03-06 13:40:38,701 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=444 type=token request_id=None
2026-03-06 13:40:39,271 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=445 type=token request_id=None
2026-03-06 13:40:39,874 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=446 type=token request_id=None
2026-03-06 13:40:40,517 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=447 type=token request_id=None
2026-03-06 13:40:41,222 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=448 type=token request_id=None
2026-03-06 13:40:41,899 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=449 type=token request_id=None
2026-03-06 13:40:42,311 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=450 type=token request_id=None
2026-03-06 13:40:42,717 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=451 type=token request_id=None
2026-03-06 13:40:43,183 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=452 type=token request_id=None
2026-03-06 13:40:43,525 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=453 type=token request_id=None
2026-03-06 13:40:43,911 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=454 type=token request_id=None
2026-03-06 13:40:44,323 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=455 type=token request_id=None
2026-03-06 13:40:44,722 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=456 type=token request_id=None
2026-03-06 13:40:45,121 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=457 type=token request_id=None
2026-03-06 13:40:45,519 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=458 type=token request_id=None
2026-03-06 13:40:45,794 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=459 type=token request_id=None
2026-03-06 13:40:45,897 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=460 type=token request_id=None
2026-03-06 13:40:46,007 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=461 type=token request_id=None
2026-03-06 13:40:46,121 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=462 type=token request_id=None
2026-03-06 13:40:46,235 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=463 type=token request_id=None
2026-03-06 13:40:46,344 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=464 type=token request_id=None
2026-03-06 13:40:46,453 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=465 type=token request_id=None
2026-03-06 13:40:46,565 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=466 type=token request_id=None
2026-03-06 13:40:46,676 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=467 type=token request_id=None
2026-03-06 13:40:46,789 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=468 type=token request_id=None
2026-03-06 13:40:47,182 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=469 type=token request_id=None
2026-03-06 13:40:47,582 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=470 type=token request_id=None
2026-03-06 13:40:48,026 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=471 type=token request_id=None
2026-03-06 13:40:48,509 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=472 type=token request_id=None
2026-03-06 13:40:48,732 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=473 type=token request_id=None
2026-03-06 13:40:48,849 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=474 type=token request_id=None
2026-03-06 13:40:48,967 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=475 type=token request_id=None
2026-03-06 13:40:49,259 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=476 type=token request_id=None
2026-03-06 13:40:49,261 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=477 type=token request_id=None
2026-03-06 13:40:49,307 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=478 type=token request_id=None
2026-03-06 13:40:49,397 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=479 type=token request_id=None
2026-03-06 13:40:49,485 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=480 type=token request_id=None
2026-03-06 13:40:49,573 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=481 type=token request_id=None
2026-03-06 13:40:49,678 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=482 type=token request_id=None
2026-03-06 13:40:49,769 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=483 type=token request_id=None
2026-03-06 13:40:49,861 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=484 type=token request_id=None
2026-03-06 13:40:49,956 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=485 type=token request_id=None
2026-03-06 13:40:50,042 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=486 type=token request_id=None
2026-03-06 13:40:50,136 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=487 type=token request_id=None
2026-03-06 13:40:50,229 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=488 type=token request_id=None
2026-03-06 13:40:50,311 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=489 type=token request_id=None
2026-03-06 13:40:50,625 DEBUG [httpcore.http11] response_closed.started
2026-03-06 13:40:50,625 DEBUG [httpcore.http11] response_closed.complete
2026-03-06 13:40:50,701 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=490 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:50,771 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=491 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:50,839 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=492 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:50,916 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=493 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:50,981 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=494 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:51,023 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=495 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:51,039 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=496 type=final request_id=None
2026-03-06 13:40:51,106 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=497 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:51,160 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=498 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:51,255 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=499 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:51,256 INFO [app.main] ws_agent_run_done request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7 session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 selected_model=qwen3-coder:480b-cloud
2026-03-06 13:40:51,355 DEBUG [app.main] ws_send_event session_id=f29cf741-3ae2-4ffb-a04a-08284af5ede7 seq=500 type=lifecycle request_id=2c774c9b-55dc-4cdb-934a-b2333bd198f7
2026-03-06 13:40:51,374 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
←[32mINFO←[0m:     127.0.0.1:57919 - "←[1mOPTIONS /api/control/runs.audit HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:57919 - "←[1mPOST /api/control/runs.audit HTTP/1.1←[0m" ←[32m200 OK←[0m
