←[32mINFO←[0m:     Started server process [←[36m25676←[0m]
←[32mINFO←[0m:     Waiting for application startup.
2026-03-05 12:24:45,767 INFO [app.main] startup_paths workspace_root=C:\Users\wisni\code\git\ai-agent-starter-kit\backend memory_dir=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\memory_store orchestrator_state_dir=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\state_store runtime_state_file=C:\Users\wisni\code\git\ai-agent-starter-kit\backend\runtime_state.json
2026-03-05 12:24:45,777 INFO [app.main] startup_memory_reset enabled=True removed_files=71
2026-03-05 12:24:45,873 INFO [app.main] startup_state_reset enabled=True removed_runs=330 removed_snapshots=280
←[32mINFO←[0m:     Application startup complete.
←[32mINFO←[0m:     Uvicorn running on ←[1mhttp://0.0.0.0:8000←[0m (Press CTRL+C to quit)
←[32mINFO←[0m:     ('127.0.0.1', 54594) - "WebSocket /ws/agent" [accepted]
2026-03-05 12:24:46,382 INFO [app.main] ws_connected session_id=c22a3941-6d6a-4655-a9c0-6e3bcf2dda24 runtime=api model=qwen3-coder:480b-cloud
2026-03-05 12:24:46,382 DEBUG [app.main] ws_send_event session_id=c22a3941-6d6a-4655-a9c0-6e3bcf2dda24 seq=1 type=status request_id=None
←[32mINFO←[0m:     connection open
2026-03-05 12:29:59,900 INFO [app.main] ws_disconnected session_id=c22a3941-6d6a-4655-a9c0-6e3bcf2dda24
←[32mINFO←[0m:     connection closed
←[32mINFO←[0m:     ('127.0.0.1', 55223) - "WebSocket /ws/agent" [accepted]
2026-03-05 12:30:00,730 INFO [app.main] ws_connected session_id=ec140545-83c2-48cb-8576-b8390fbee78b runtime=api model=qwen3-coder:480b-cloud
2026-03-05 12:30:00,730 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=1 type=status request_id=None
←[32mINFO←[0m:     127.0.0.1:62018 - "←[1mOPTIONS /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     connection open
2026-03-05 12:30:02,288 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=12 socket_options=None
←[32mINFO←[0m:     127.0.0.1:49234 - "←[1mGET /api/agents HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:59267 - "←[1mGET /api/monitoring/schema HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:64213 - "←[1mGET /api/runtime/features HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:49667 - "←[1mGET /api/presets HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:49234 - "←[1mPOST /api/control/policy-approvals.pending HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:62433 - "←[1mGET /api/custom-agents HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-05 12:30:02,609 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D754D40>
2026-03-05 12:30:02,614 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'GET']>
2026-03-05 12:30:02,615 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:30:02,616 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'GET']>
2026-03-05 12:30:02,616 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:30:02,617 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'GET']>
2026-03-05 12:30:02,701 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:30:02 GMT'), (b'Content-Length', b'1223')])
2026-03-05 12:30:02,706 INFO [httpx] HTTP Request: GET http://localhost:11434/api/tags "HTTP/1.1 200 OK"
2026-03-05 12:30:02,707 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'GET']>
2026-03-05 12:30:02,708 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:30:02,709 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:30:02,710 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:30:02,714 DEBUG [httpcore.connection] close.started
2026-03-05 12:30:02,715 DEBUG [httpcore.connection] close.complete
←[32mINFO←[0m:     127.0.0.1:49817 - "←[1mGET /api/runtime/status HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-05 12:31:00,425 INFO [app.main] ws_message_received request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5 session_id=ec140545-83c2-48cb-8576-b8390fbee78b type=user_message agent_id=head-agent content_len=110 requested_model=qwen3-coder:480b-cloud
2026-03-05 12:31:00,595 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=2 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:00,657 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=3 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:00,712 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=4 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:00,767 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=5 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:00,768 INFO [app.main] ws_request_dispatch request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5 session_id=ec140545-83c2-48cb-8576-b8390fbee78b runtime=api active_model=qwen3-coder:480b-cloud
2026-03-05 12:31:00,769 INFO [app.main] ws_agent_run_start request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5 session_id=ec140545-83c2-48cb-8576-b8390fbee78b selected_model=qwen3-coder:480b-cloud
2026-03-05 12:31:00,800 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=6 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:00,836 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=7 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:00,881 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=8 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:00,937 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=9 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:00,955 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=10 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,026 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=11 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,079 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=12 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,129 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=13 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,157 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=14 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,202 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=15 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,233 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=16 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,301 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=17 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,320 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=18 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,356 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=19 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,358 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=20 type=status request_id=None
2026-03-05 12:31:01,397 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=21 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:01,650 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:01,897 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D210410>
2026-03-05 12:31:01,899 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:01,900 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:01,901 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:01,901 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:01,902 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:03,999 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:03 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:04,000 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:04,001 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:04,001 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:04,002 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:04,002 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:04,003 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:04,004 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:04,045 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=22 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,086 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=23 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,116 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=24 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,131 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=25 type=agent_step request_id=None
2026-03-05 12:31:04,169 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=26 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,199 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=27 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,255 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=28 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,321 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=29 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,365 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=30 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,388 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=31 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:04,683 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:04,965 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D757E60>
2026-03-05 12:31:04,966 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:04,966 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:04,967 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:04,967 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:04,968 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:06,738 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:06 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:06,742 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:06,743 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:06,743 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:06,745 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:06,745 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:06,747 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:06,748 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:06,782 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=32 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:06,843 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=33 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:06,893 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=34 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:06,895 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=35 type=agent_step request_id=None
2026-03-05 12:31:06,933 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=36 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:06,965 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=37 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,027 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=38 type=subrun_status request_id=None
2026-03-05 12:31:07,115 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=39 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,188 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=40 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,229 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=41 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,281 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=42 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,319 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=43 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,336 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=44 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,336 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=45 type=agent_step request_id=None
2026-03-05 12:31:07,370 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=46 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,406 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=47 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:07,406 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=3007
2026-03-05 12:31:07,820 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=48 type=subrun_status request_id=None
2026-03-05 12:31:07,872 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=49 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:07,908 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=50 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:07,952 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=51 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:07,995 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=52 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,032 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=53 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,105 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=54 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,162 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=55 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,219 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=56 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,250 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=57 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,301 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=58 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,333 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=59 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,368 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=60 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,393 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=61 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,427 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=62 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,427 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=63 type=status request_id=None
2026-03-05 12:31:08,478 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=64 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:08,830 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:08,832 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:09,098 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D7AEAE0>
2026-03-05 12:31:09,099 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D4C9730>
2026-03-05 12:31:09,100 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:09,101 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:09,101 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:09,101 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:09,102 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:09,102 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:09,102 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:09,103 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:09,103 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:09,104 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:10,055 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:10 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:10,056 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:10,056 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:10,057 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:10,057 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:10,058 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:10,060 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:10,062 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:10,124 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=65 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,161 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=66 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,209 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=67 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,237 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=68 type=agent_step request_id=None
2026-03-05 12:31:10,300 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=69 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,330 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=70 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,376 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=71 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,429 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=72 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,482 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=73 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,515 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=74 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:10,859 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:11,126 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D7ADF40>
2026-03-05 12:31:11,127 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:11,129 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:11,129 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:11,130 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:11,137 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:19,056 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Thu, 05 Mar 2026 11:31:19 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:19,057 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:19,060 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:19,060 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=75 type=token request_id=None
2026-03-05 12:31:19,414 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=76 type=token request_id=None
2026-03-05 12:31:19,817 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=77 type=token request_id=None
2026-03-05 12:31:20,004 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=78 type=token request_id=None
2026-03-05 12:31:20,093 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=79 type=token request_id=None
2026-03-05 12:31:20,184 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=80 type=token request_id=None
2026-03-05 12:31:20,268 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=81 type=token request_id=None
2026-03-05 12:31:20,355 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=82 type=token request_id=None
2026-03-05 12:31:20,440 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=83 type=token request_id=None
2026-03-05 12:31:20,526 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=84 type=token request_id=None
2026-03-05 12:31:20,613 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=85 type=token request_id=None
2026-03-05 12:31:20,701 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=86 type=token request_id=None
2026-03-05 12:31:20,788 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=87 type=token request_id=None
2026-03-05 12:31:20,875 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=88 type=token request_id=None
2026-03-05 12:31:20,960 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=89 type=token request_id=None
2026-03-05 12:31:21,047 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=90 type=token request_id=None
2026-03-05 12:31:21,134 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=91 type=token request_id=None
2026-03-05 12:31:21,221 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=92 type=token request_id=None
2026-03-05 12:31:21,309 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=93 type=token request_id=None
2026-03-05 12:31:21,394 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=94 type=token request_id=None
2026-03-05 12:31:21,480 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=95 type=token request_id=None
2026-03-05 12:31:21,566 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=96 type=token request_id=None
2026-03-05 12:31:21,655 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=97 type=token request_id=None
2026-03-05 12:31:21,774 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=98 type=token request_id=None
2026-03-05 12:31:22,100 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=99 type=token request_id=None
2026-03-05 12:31:22,491 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=100 type=token request_id=None
2026-03-05 12:31:22,914 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=101 type=token request_id=None
2026-03-05 12:31:23,319 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=102 type=token request_id=None
2026-03-05 12:31:23,410 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=103 type=token request_id=None
2026-03-05 12:31:23,499 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=104 type=token request_id=None
2026-03-05 12:31:23,590 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=105 type=token request_id=None
2026-03-05 12:31:23,688 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=106 type=token request_id=None
2026-03-05 12:31:23,798 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=107 type=token request_id=None
2026-03-05 12:31:23,853 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=108 type=token request_id=None
2026-03-05 12:31:23,934 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=109 type=token request_id=None
2026-03-05 12:31:24,006 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:24 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:24,007 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:24,007 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:24,007 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:24,007 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:24,008 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:24,008 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:24,009 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:24,077 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=110 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:24,149 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=111 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:24,149 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=112 type=agent_step request_id=None
2026-03-05 12:31:24,217 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=113 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:24,252 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=114 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:24,294 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=115 type=subrun_status request_id=None
2026-03-05 12:31:24,401 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=116 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:24,493 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=117 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:24,553 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=118 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:24,558 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=119 type=agent_step request_id=None
2026-03-05 12:31:24,616 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=120 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:24,670 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=121 type=subrun_status request_id=None
2026-03-05 12:31:24,729 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=122 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:24,789 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=123 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:24,866 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=124 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:24,936 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=125 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:24,983 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=126 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,099 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=127 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,181 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=128 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,264 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=129 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,307 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=130 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,373 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=131 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,429 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=132 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,503 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=133 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,561 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=134 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,597 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=135 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:25,598 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=136 type=status request_id=None
2026-03-05 12:31:25,664 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=137 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:26,012 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:26,015 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=138 type=token request_id=None
2026-03-05 12:31:26,120 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=139 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:26,246 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=140 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:26,306 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=141 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:26,307 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=142 type=agent_step request_id=None
2026-03-05 12:31:26,362 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=143 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:26,363 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=144 type=token request_id=None
2026-03-05 12:31:26,365 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=145 type=token request_id=None
2026-03-05 12:31:26,365 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=146 type=token request_id=None
2026-03-05 12:31:26,366 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=147 type=token request_id=None
2026-03-05 12:31:26,366 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=148 type=token request_id=None
2026-03-05 12:31:26,366 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=149 type=token request_id=None
2026-03-05 12:31:26,367 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=150 type=token request_id=None
2026-03-05 12:31:26,367 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=151 type=token request_id=None
2026-03-05 12:31:26,367 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=152 type=token request_id=None
2026-03-05 12:31:26,368 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=153 type=token request_id=None
2026-03-05 12:31:26,368 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=154 type=token request_id=None
2026-03-05 12:31:26,368 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=155 type=token request_id=None
2026-03-05 12:31:26,371 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=156 type=token request_id=None
2026-03-05 12:31:26,372 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=157 type=token request_id=None
2026-03-05 12:31:26,372 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=158 type=token request_id=None
2026-03-05 12:31:26,374 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=159 type=token request_id=None
2026-03-05 12:31:26,374 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=160 type=token request_id=None
2026-03-05 12:31:26,374 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=161 type=token request_id=None
2026-03-05 12:31:26,374 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=162 type=token request_id=None
2026-03-05 12:31:26,374 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=163 type=token request_id=None
2026-03-05 12:31:26,374 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=164 type=token request_id=None
2026-03-05 12:31:26,376 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=165 type=token request_id=None
2026-03-05 12:31:26,376 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=166 type=token request_id=None
2026-03-05 12:31:26,377 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=167 type=token request_id=None
2026-03-05 12:31:26,377 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=168 type=token request_id=None
2026-03-05 12:31:26,378 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=169 type=token request_id=None
2026-03-05 12:31:26,381 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=170 type=token request_id=None
2026-03-05 12:31:26,382 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=171 type=token request_id=None
2026-03-05 12:31:26,383 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=172 type=token request_id=None
2026-03-05 12:31:26,396 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=173 type=token request_id=None
2026-03-05 12:31:26,476 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=174 type=token request_id=None
2026-03-05 12:31:26,633 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=175 type=token request_id=None
2026-03-05 12:31:26,635 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D7AF5F0>
2026-03-05 12:31:26,636 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:26,637 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:26,637 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:26,637 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:26,638 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:26,821 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=176 type=token request_id=None
2026-03-05 12:31:26,901 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=177 type=token request_id=None
2026-03-05 12:31:26,982 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=178 type=token request_id=None
2026-03-05 12:31:27,062 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=179 type=token request_id=None
2026-03-05 12:31:27,148 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=180 type=token request_id=None
2026-03-05 12:31:27,247 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=181 type=token request_id=None
2026-03-05 12:31:27,385 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=182 type=token request_id=None
2026-03-05 12:31:27,474 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=183 type=token request_id=None
2026-03-05 12:31:27,552 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=184 type=token request_id=None
2026-03-05 12:31:27,624 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=185 type=token request_id=None
2026-03-05 12:31:27,729 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=186 type=token request_id=None
2026-03-05 12:31:27,767 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:27 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:27,768 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:27,768 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:27,768 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:27,769 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:27,769 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:27,770 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:27,771 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:27,837 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=187 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:27,895 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=188 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:27,941 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=189 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:27,962 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=190 type=agent_step request_id=None
2026-03-05 12:31:28,029 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=191 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:28,086 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=192 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:28,179 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=193 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:28,260 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=194 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:28,356 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=195 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:28,419 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=196 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:28,797 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:28,799 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=197 type=token request_id=None
2026-03-05 12:31:28,800 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=198 type=token request_id=None
2026-03-05 12:31:28,800 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=199 type=token request_id=None
2026-03-05 12:31:28,800 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=200 type=token request_id=None
2026-03-05 12:31:28,801 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=201 type=token request_id=None
2026-03-05 12:31:28,801 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=202 type=token request_id=None
2026-03-05 12:31:28,802 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=203 type=token request_id=None
2026-03-05 12:31:28,802 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=204 type=token request_id=None
2026-03-05 12:31:28,802 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=205 type=token request_id=None
2026-03-05 12:31:28,803 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=206 type=token request_id=None
2026-03-05 12:31:28,803 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=207 type=token request_id=None
2026-03-05 12:31:28,803 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=208 type=token request_id=None
2026-03-05 12:31:28,803 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=209 type=token request_id=None
2026-03-05 12:31:28,828 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=210 type=token request_id=None
2026-03-05 12:31:28,910 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=211 type=token request_id=None
2026-03-05 12:31:28,988 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=212 type=token request_id=None
2026-03-05 12:31:29,059 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D7AFBF0>
2026-03-05 12:31:29,059 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:29,060 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:29,061 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:29,062 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:29,062 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:29,068 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=213 type=token request_id=None
2026-03-05 12:31:29,148 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=214 type=token request_id=None
2026-03-05 12:31:29,228 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=215 type=token request_id=None
2026-03-05 12:31:29,308 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=216 type=token request_id=None
2026-03-05 12:31:29,513 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=217 type=token request_id=None
2026-03-05 12:31:29,686 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:29,687 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:29,752 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=218 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:30,150 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:30,237 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=219 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:30,334 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=220 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:30,423 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=221 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:30,505 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=222 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:30,590 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=223 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:30,630 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=224 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:30,632 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=225 type=agent_step request_id=None
2026-03-05 12:31:30,686 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=226 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:30,765 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=227 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:30,766 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=3440
2026-03-05 12:31:31,190 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:31,191 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:30 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:31,192 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:31,192 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:31,193 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:31,195 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:31,195 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:31,197 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:31,199 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:31,300 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=228 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:31,406 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=229 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:31,409 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=230 type=agent_step request_id=None
2026-03-05 12:31:31,535 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=231 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:31:31,539 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
2026-03-05 12:31:31,541 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D51C2F0>
2026-03-05 12:31:31,542 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D51D880>
2026-03-05 12:31:31,545 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:31,548 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:31,550 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:31,551 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:31,552 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:31,553 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:31,555 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:31,555 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:31,556 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:31,556 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:32,879 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Thu, 05 Mar 2026 11:31:32 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:32,888 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:32,891 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:32,892 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=232 type=token request_id=None
2026-03-05 12:31:32,907 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=233 type=token request_id=None
2026-03-05 12:31:32,943 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=234 type=token request_id=None
2026-03-05 12:31:32,979 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=235 type=token request_id=None
2026-03-05 12:31:33,014 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=236 type=token request_id=None
2026-03-05 12:31:33,050 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=237 type=token request_id=None
2026-03-05 12:31:33,086 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=238 type=token request_id=None
2026-03-05 12:31:33,122 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=239 type=token request_id=None
2026-03-05 12:31:33,159 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=240 type=token request_id=None
2026-03-05 12:31:33,195 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=241 type=token request_id=None
2026-03-05 12:31:33,231 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=242 type=token request_id=None
2026-03-05 12:31:33,267 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=243 type=token request_id=None
2026-03-05 12:31:33,431 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=244 type=token request_id=None
2026-03-05 12:31:33,474 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=245 type=token request_id=None
2026-03-05 12:31:33,519 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=246 type=token request_id=None
2026-03-05 12:31:33,564 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=247 type=token request_id=None
2026-03-05 12:31:33,601 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=248 type=token request_id=None
2026-03-05 12:31:33,638 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=249 type=token request_id=None
2026-03-05 12:31:33,675 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=250 type=token request_id=None
2026-03-05 12:31:33,740 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=251 type=token request_id=None
2026-03-05 12:31:33,779 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=252 type=token request_id=None
2026-03-05 12:31:33,783 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=253 type=token request_id=None
2026-03-05 12:31:33,820 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=254 type=token request_id=None
2026-03-05 12:31:33,859 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=255 type=token request_id=None
2026-03-05 12:31:33,896 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=256 type=token request_id=None
2026-03-05 12:31:33,931 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=257 type=token request_id=None
2026-03-05 12:31:33,969 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=258 type=token request_id=None
2026-03-05 12:31:34,004 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=259 type=token request_id=None
2026-03-05 12:31:34,040 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=260 type=token request_id=None
2026-03-05 12:31:34,077 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=261 type=token request_id=None
2026-03-05 12:31:34,113 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=262 type=token request_id=None
2026-03-05 12:31:34,150 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=263 type=token request_id=None
2026-03-05 12:31:34,185 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=264 type=token request_id=None
2026-03-05 12:31:34,224 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=265 type=token request_id=None
2026-03-05 12:31:34,259 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=266 type=token request_id=None
2026-03-05 12:31:34,295 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=267 type=token request_id=None
2026-03-05 12:31:34,331 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=268 type=token request_id=None
2026-03-05 12:31:34,367 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=269 type=token request_id=None
2026-03-05 12:31:34,405 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=270 type=token request_id=None
2026-03-05 12:31:34,440 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=271 type=token request_id=None
2026-03-05 12:31:34,475 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=272 type=token request_id=None
2026-03-05 12:31:34,510 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=273 type=token request_id=None
2026-03-05 12:31:34,546 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=274 type=token request_id=None
2026-03-05 12:31:34,581 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=275 type=token request_id=None
2026-03-05 12:31:34,616 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=276 type=token request_id=None
2026-03-05 12:31:34,652 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=277 type=token request_id=None
2026-03-05 12:31:34,689 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=278 type=token request_id=None
2026-03-05 12:31:34,723 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=279 type=token request_id=None
2026-03-05 12:31:34,758 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=280 type=token request_id=None
2026-03-05 12:31:34,802 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=281 type=token request_id=None
2026-03-05 12:31:34,833 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=282 type=token request_id=None
2026-03-05 12:31:34,868 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=283 type=token request_id=None
2026-03-05 12:31:34,903 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=284 type=token request_id=None
2026-03-05 12:31:34,940 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=285 type=token request_id=None
2026-03-05 12:31:34,976 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=286 type=token request_id=None
2026-03-05 12:31:35,012 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=287 type=token request_id=None
2026-03-05 12:31:35,048 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=288 type=token request_id=None
2026-03-05 12:31:35,084 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=289 type=token request_id=None
2026-03-05 12:31:35,120 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=290 type=token request_id=None
2026-03-05 12:31:35,156 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=291 type=token request_id=None
2026-03-05 12:31:35,195 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=292 type=token request_id=None
2026-03-05 12:31:35,228 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=293 type=token request_id=None
2026-03-05 12:31:35,263 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=294 type=token request_id=None
2026-03-05 12:31:35,301 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=295 type=token request_id=None
2026-03-05 12:31:35,337 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=296 type=token request_id=None
2026-03-05 12:31:35,510 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:35,514 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:35,608 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=297 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:36,061 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:36,065 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
2026-03-05 12:31:36,334 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D7AE900>
2026-03-05 12:31:36,335 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:36,336 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:36,336 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:36,337 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:36,337 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:36,350 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:36 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:36,350 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:36,350 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:36,351 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:36,352 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:36,352 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:36,354 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:36,355 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:36,426 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=298 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:36,501 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=299 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:31:36,945 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:37,208 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D5980B0>
2026-03-05 12:31:37,209 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:37,210 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:37,211 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:37,214 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:37,215 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:40,199 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:40 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:40,199 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:40,200 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:40,202 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:40,203 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:40,203 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:40,204 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:40,204 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:40,307 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=300 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:40,392 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=301 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:40,705 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:40,955 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D59A120>
2026-03-05 12:31:40,957 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:40,958 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:40,958 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:40,958 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:40,963 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:44,902 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:44 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:44,903 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:44,903 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:44,903 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:44,904 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:44,904 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:44,906 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:44,906 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:44,952 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=302 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:45,053 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=303 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:45,053 INFO [app.llm_client] llm_stream_start base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud native_api=True prompt_len=3441
2026-03-05 12:31:45,300 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:45,567 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D51F950>
2026-03-05 12:31:45,568 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:45,569 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:45,569 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:45,569 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:45,570 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:45,963 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/x-ndjson'), (b'Date', b'Thu, 05 Mar 2026 11:31:45 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:45,964 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:45,965 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:45,965 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=304 type=token request_id=None
2026-03-05 12:31:45,990 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=305 type=token request_id=None
2026-03-05 12:31:46,009 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=306 type=token request_id=None
2026-03-05 12:31:46,044 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=307 type=token request_id=None
2026-03-05 12:31:46,063 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=308 type=token request_id=None
2026-03-05 12:31:46,088 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=309 type=token request_id=None
2026-03-05 12:31:46,116 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=310 type=token request_id=None
2026-03-05 12:31:46,141 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=311 type=token request_id=None
2026-03-05 12:31:46,170 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=312 type=token request_id=None
2026-03-05 12:31:46,196 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=313 type=token request_id=None
2026-03-05 12:31:46,223 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=314 type=token request_id=None
2026-03-05 12:31:46,250 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=315 type=token request_id=None
2026-03-05 12:31:46,276 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=316 type=token request_id=None
2026-03-05 12:31:46,303 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=317 type=token request_id=None
2026-03-05 12:31:46,330 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=318 type=token request_id=None
2026-03-05 12:31:46,356 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=319 type=token request_id=None
2026-03-05 12:31:46,385 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=320 type=token request_id=None
2026-03-05 12:31:46,409 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=321 type=token request_id=None
2026-03-05 12:31:46,437 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=322 type=token request_id=None
2026-03-05 12:31:46,465 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=323 type=token request_id=None
2026-03-05 12:31:46,492 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=324 type=token request_id=None
2026-03-05 12:31:46,520 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=325 type=token request_id=None
2026-03-05 12:31:46,546 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=326 type=token request_id=None
2026-03-05 12:31:46,573 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=327 type=token request_id=None
2026-03-05 12:31:46,602 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=328 type=token request_id=None
2026-03-05 12:31:46,635 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=329 type=token request_id=None
2026-03-05 12:31:46,657 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=330 type=token request_id=None
2026-03-05 12:31:46,687 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=331 type=token request_id=None
2026-03-05 12:31:46,714 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=332 type=token request_id=None
2026-03-05 12:31:46,740 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=333 type=token request_id=None
2026-03-05 12:31:46,796 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=334 type=token request_id=None
2026-03-05 12:31:46,820 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=335 type=token request_id=None
2026-03-05 12:31:46,847 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=336 type=token request_id=None
2026-03-05 12:31:46,877 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=337 type=token request_id=None
2026-03-05 12:31:46,903 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=338 type=token request_id=None
2026-03-05 12:31:46,927 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=339 type=token request_id=None
2026-03-05 12:31:46,953 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=340 type=token request_id=None
2026-03-05 12:31:46,979 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=341 type=token request_id=None
2026-03-05 12:31:47,004 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=342 type=token request_id=None
2026-03-05 12:31:47,031 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=343 type=token request_id=None
2026-03-05 12:31:47,057 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=344 type=token request_id=None
2026-03-05 12:31:47,085 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=345 type=token request_id=None
2026-03-05 12:31:47,112 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=346 type=token request_id=None
2026-03-05 12:31:47,138 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=347 type=token request_id=None
2026-03-05 12:31:47,166 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=348 type=token request_id=None
2026-03-05 12:31:47,192 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=349 type=token request_id=None
2026-03-05 12:31:47,219 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=350 type=token request_id=None
2026-03-05 12:31:47,247 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=351 type=token request_id=None
2026-03-05 12:31:47,274 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=352 type=token request_id=None
2026-03-05 12:31:47,300 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=353 type=token request_id=None
2026-03-05 12:31:47,327 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=354 type=token request_id=None
2026-03-05 12:31:47,353 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=355 type=token request_id=None
2026-03-05 12:31:47,381 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=356 type=token request_id=None
2026-03-05 12:31:47,711 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=357 type=token request_id=None
2026-03-05 12:31:48,071 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=358 type=token request_id=None
2026-03-05 12:31:48,403 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=359 type=token request_id=None
2026-03-05 12:31:48,447 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=360 type=token request_id=None
2026-03-05 12:31:48,479 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=361 type=token request_id=None
2026-03-05 12:31:48,508 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=362 type=token request_id=None
2026-03-05 12:31:48,539 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=363 type=token request_id=None
2026-03-05 12:31:48,570 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=364 type=token request_id=None
2026-03-05 12:31:48,601 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=365 type=token request_id=None
2026-03-05 12:31:48,631 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=366 type=token request_id=None
2026-03-05 12:31:48,661 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=367 type=token request_id=None
2026-03-05 12:31:48,692 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=368 type=token request_id=None
2026-03-05 12:31:48,723 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=369 type=token request_id=None
2026-03-05 12:31:48,754 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=370 type=token request_id=None
2026-03-05 12:31:48,784 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=371 type=token request_id=None
2026-03-05 12:31:48,815 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=372 type=token request_id=None
2026-03-05 12:31:48,846 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=373 type=token request_id=None
2026-03-05 12:31:48,878 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=374 type=token request_id=None
2026-03-05 12:31:49,098 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:49,100 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:49,172 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=375 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:49,535 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:31:49,538 DEBUG [httpcore.http11] receive_response_body.failed exception=GeneratorExit()
2026-03-05 12:31:49,805 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D599310>
2026-03-05 12:31:49,807 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:31:49,807 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:31:49,808 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:31:49,808 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:31:49,809 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:31:52,977 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:31:52 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:31:52,978 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:31:52,978 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:31:52,978 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:31:52,979 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:31:52,979 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:31:52,980 DEBUG [httpcore.connection] close.started
2026-03-05 12:31:52,980 DEBUG [httpcore.connection] close.complete
2026-03-05 12:31:53,070 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=376 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:53,497 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=377 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:53,591 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=378 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:53,679 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=379 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:53,728 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=380 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:53,750 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=381 type=final request_id=None
2026-03-05 12:31:53,818 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=382 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:53,883 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=383 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:53,976 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8 seq=384 type=lifecycle request_id=18abb2e8-c094-456c-8367-6e279d103736
2026-03-05 12:31:54,028 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=385 type=subrun_status request_id=None
2026-03-05 12:31:54,029 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=386 type=subrun_announce request_id=None
2026-03-05 12:33:32,579 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=387 type=error request_id=None
2026-03-05 12:33:39,252 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=388 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:40,337 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=389 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:40,415 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=390 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:40,496 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=391 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:40,693 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:33:40,695 DEBUG [httpcore.http11] receive_response_headers.failed exception=ReadTimeout(TimeoutError())
2026-03-05 12:33:40,695 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:33:40,697 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:33:40,699 WARNING [app.llm_client] llm_native_complete_timeout base_url=http://localhost:11434/api model=qwen3-coder:480b-cloud error=
2026-03-05 12:33:40,770 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=392 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:33:40,842 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=393 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:33:40,927 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=394 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:33:40,966 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=395 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:33:40,985 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=396 type=final request_id=None
2026-03-05 12:33:41,041 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=397 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:33:41,093 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=398 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:33:41,170 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=399 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:33:41,172 INFO [app.main] ws_agent_run_done request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5 session_id=ec140545-83c2-48cb-8576-b8390fbee78b selected_model=qwen3-coder:480b-cloud
2026-03-05 12:33:41,223 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=400 type=lifecycle request_id=1f508a9d-30ec-4cd1-9930-b511e5ca7ca5
2026-03-05 12:33:41,241 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D1269F0>
2026-03-05 12:33:41,243 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:33:41,243 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:33:41,244 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:33:41,244 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:33:41,244 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
←[32mINFO←[0m:     127.0.0.1:62201 - "←[1mOPTIONS /api/control/runs.audit HTTP/1.1←[0m" ←[32m200 OK←[0m
←[32mINFO←[0m:     127.0.0.1:62201 - "←[1mPOST /api/control/runs.audit HTTP/1.1←[0m" ←[32m200 OK←[0m
2026-03-05 12:33:45,162 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:33:45 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:33:45,165 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:33:45,166 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:33:45,167 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:33:45,167 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:33:45,168 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:33:45,168 DEBUG [httpcore.connection] close.started
2026-03-05 12:33:45,169 DEBUG [httpcore.connection] close.complete
2026-03-05 12:33:45,249 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=401 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:45,306 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=402 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:45,370 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=403 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:45,443 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=404 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:45,507 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=405 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:45,551 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=406 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:45,732 DEBUG [httpcore.connection] connect_tcp.started host='localhost' port=11434 local_address=None timeout=120 socket_options=None
2026-03-05 12:33:46,003 DEBUG [httpcore.connection] connect_tcp.complete return_value=<httpcore._backends.anyio.AnyIOStream object at 0x000001940D7845C0>
2026-03-05 12:33:46,004 DEBUG [httpcore.http11] send_request_headers.started request=<Request [b'POST']>
2026-03-05 12:33:46,004 DEBUG [httpcore.http11] send_request_headers.complete
2026-03-05 12:33:46,005 DEBUG [httpcore.http11] send_request_body.started request=<Request [b'POST']>
2026-03-05 12:33:46,005 DEBUG [httpcore.http11] send_request_body.complete
2026-03-05 12:33:46,005 DEBUG [httpcore.http11] receive_response_headers.started request=<Request [b'POST']>
2026-03-05 12:33:47,297 DEBUG [httpcore.http11] receive_response_headers.complete return_value=(b'HTTP/1.1', 200, b'OK', [(b'Content-Type', b'application/json; charset=utf-8'), (b'Date', b'Thu, 05 Mar 2026 11:33:47 GMT'), (b'Transfer-Encoding', b'chunked')])
2026-03-05 12:33:47,297 INFO [httpx] HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
2026-03-05 12:33:47,297 DEBUG [httpcore.http11] receive_response_body.started request=<Request [b'POST']>
2026-03-05 12:33:47,298 DEBUG [httpcore.http11] receive_response_body.complete
2026-03-05 12:33:47,299 DEBUG [httpcore.http11] response_closed.started
2026-03-05 12:33:47,299 DEBUG [httpcore.http11] response_closed.complete
2026-03-05 12:33:47,300 DEBUG [httpcore.connection] close.started
2026-03-05 12:33:47,300 DEBUG [httpcore.connection] close.complete
2026-03-05 12:33:47,363 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=407 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:47,437 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=408 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
2026-03-05 12:33:47,438 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b seq=409 type=agent_step request_id=None
2026-03-05 12:33:47,506 DEBUG [app.main] ws_send_event session_id=ec140545-83c2-48cb-8576-b8390fbee78b-subrun-18abb2e8-subrun-ac1c3405 seq=410 type=lifecycle request_id=ac1c3405-0323-499d-87ba-bb32fd6b2bf0
