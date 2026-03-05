"""Agent Message Bus: Direct agent-to-agent communication.

This replaces the Hub-and-Spoke parent-memory pattern with:
- Direct point-to-point messaging between agents
- Broadcast messaging (one-to-many)
- Request/Reply pattern (ask an agent and wait for answer)
- Topic-based pub/sub (agents subscribe to topics)
- Priority queuing (urgent messages processed first)
- Message delivery guarantees (at-least-once within a session)
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable, Awaitable
from uuid import uuid4

logger = logging.getLogger(__name__)

MessageHandler = Callable[["AgentMessage"], Awaitable["AgentMessage | None"]]


class MessageType(StrEnum):
    DIRECT = "direct"           # point-to-point
    BROADCAST = "broadcast"     # one-to-many
    REQUEST = "request"         # requires reply
    REPLY = "reply"             # response to request
    TOPIC = "topic"             # pub/sub topic message
    COORDINATION = "coordination"  # supervisor/coordinator messages
    RESULT = "result"           # task result delivery
    HEARTBEAT = "heartbeat"     # agent liveness


class MessagePriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass(frozen=True)
class AgentMessage:
    """A message between agents."""
    message_id: str
    sender_agent_id: str
    recipient_agent_id: str        # "*" for broadcast, topic name for topic
    message_type: str              # MessageType value
    payload: dict[str, Any]
    timestamp: str
    priority: str = "normal"       # MessagePriority value
    correlation_id: str | None = None  # for request/reply correlation
    reply_to: str | None = None    # message_id being replied to
    ttl_seconds: int = 300         # time-to-live
    session_id: str = ""
    topic: str | None = None       # for topic-based messaging
    requires_ack: bool = False     # delivery acknowledgment required
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMailbox:
    """Per-agent message queue with priority ordering."""
    agent_id: str
    inbox: deque[AgentMessage] = field(default_factory=deque)
    max_size: int = 500
    _event: asyncio.Event = field(default_factory=asyncio.Event)

    def enqueue(self, message: AgentMessage) -> bool:
        """Add message to inbox, respecting priority. Returns False if full."""
        if len(self.inbox) >= self.max_size:
            return False

        # Priority insertion: URGENT goes to front, HIGH near front
        if message.priority == MessagePriority.URGENT:
            self.inbox.appendleft(message)
        elif message.priority == MessagePriority.HIGH:
            # Insert after any existing URGENT messages
            insert_pos = 0
            for i, existing in enumerate(self.inbox):
                if existing.priority != MessagePriority.URGENT:
                    insert_pos = i
                    break
                insert_pos = i + 1
            self.inbox.insert(insert_pos, message)
        else:
            self.inbox.append(message)

        self._event.set()
        return True

    def dequeue(self) -> AgentMessage | None:
        """Get next message from inbox."""
        if not self.inbox:
            return None
        msg = self.inbox.popleft()
        if not self.inbox:
            self._event.clear()
        return msg

    def peek(self) -> AgentMessage | None:
        """Look at next message without removing it."""
        return self.inbox[0] if self.inbox else None

    async def wait_for_message(self, timeout: float = 30.0) -> AgentMessage | None:
        """Wait for a message to arrive. Returns None on timeout."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return self.dequeue()
        except asyncio.TimeoutError:
            return None

    @property
    def pending_count(self) -> int:
        return len(self.inbox)


class AgentMessageBus:
    """Central message bus enabling direct agent-to-agent communication.
    
    Architecture:
    - Each agent gets a mailbox (AgentMailbox) when registered
    - Messages are routed based on recipient_agent_id
    - Broadcast messages go to all registered agents (except sender)
    - Topic subscriptions enable pub/sub pattern
    - Request/Reply with correlation IDs for synchronous-style communication
    - Dead letter queue for undeliverable messages
    """

    def __init__(self, *, session_id: str, max_mailbox_size: int = 500):
        self._session_id = session_id
        self._max_mailbox_size = max(10, max_mailbox_size)
        self._lock = asyncio.Lock()
        self._mailboxes: dict[str, AgentMailbox] = {}
        self._topic_subscribers: dict[str, set[str]] = defaultdict(set)
        self._message_handlers: dict[str, MessageHandler] = {}
        self._dead_letter_queue: deque[AgentMessage] = deque(maxlen=200)
        self._sent_count = 0
        self._delivered_count = 0
        self._failed_count = 0
        # For request/reply: correlation_id -> Future
        self._pending_replies: dict[str, asyncio.Future[AgentMessage]] = {}
        self._message_log: deque[AgentMessage] = deque(maxlen=1000)

    @property
    def session_id(self) -> str:
        return self._session_id

    async def register_agent(self, agent_id: str) -> None:
        """Register an agent on the message bus."""
        normalized = (agent_id or "").strip().lower()
        if not normalized:
            raise ValueError("agent_id must not be empty")
        async with self._lock:
            if normalized not in self._mailboxes:
                self._mailboxes[normalized] = AgentMailbox(
                    agent_id=normalized,
                    max_size=self._max_mailbox_size,
                )
                logger.info("Agent '%s' registered on message bus (session=%s)", normalized, self._session_id)

    async def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent from the message bus."""
        normalized = (agent_id or "").strip().lower()
        async with self._lock:
            self._mailboxes.pop(normalized, None)
            self._message_handlers.pop(normalized, None)
            for subscribers in self._topic_subscribers.values():
                subscribers.discard(normalized)

    def set_handler(self, agent_id: str, handler: MessageHandler) -> None:
        """Set a message handler for an agent (for auto-processing incoming messages)."""
        normalized = (agent_id or "").strip().lower()
        self._message_handlers[normalized] = handler

    async def send(
        self,
        *,
        sender: str,
        recipient: str,
        payload: dict[str, Any],
        message_type: str = MessageType.DIRECT,
        priority: str = MessagePriority.NORMAL,
        correlation_id: str | None = None,
        reply_to: str | None = None,
        topic: str | None = None,
        requires_ack: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        """Send a message from one agent to another."""
        message = AgentMessage(
            message_id=str(uuid4()),
            sender_agent_id=(sender or "").strip().lower(),
            recipient_agent_id=(recipient or "").strip().lower(),
            message_type=message_type,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
            priority=priority,
            correlation_id=correlation_id or str(uuid4()),
            reply_to=reply_to,
            session_id=self._session_id,
            topic=topic,
            requires_ack=requires_ack,
            metadata=dict(metadata or {}),
        )

        self._message_log.append(message)
        self._sent_count += 1

        if message_type == MessageType.BROADCAST:
            await self._broadcast(message)
        elif message_type == MessageType.TOPIC and topic:
            await self._publish_topic(message, topic)
        elif message_type == MessageType.REPLY:
            await self._deliver_reply(message)
        else:
            await self._deliver_direct(message)

        return message

    async def request(
        self,
        *,
        sender: str,
        recipient: str,
        payload: dict[str, Any],
        timeout: float = 60.0,
        priority: str = MessagePriority.NORMAL,
    ) -> AgentMessage | None:
        """Send a request and wait for a reply (synchronous-style RPC)."""
        correlation_id = str(uuid4())
        future: asyncio.Future[AgentMessage] = asyncio.get_running_loop().create_future()
        self._pending_replies[correlation_id] = future

        await self.send(
            sender=sender,
            recipient=recipient,
            payload=payload,
            message_type=MessageType.REQUEST,
            priority=priority,
            correlation_id=correlation_id,
        )

        try:
            reply = await asyncio.wait_for(future, timeout=timeout)
            return reply
        except asyncio.TimeoutError:
            logger.warning(
                "Request timeout: sender=%s recipient=%s correlation=%s",
                sender, recipient, correlation_id,
            )
            return None
        finally:
            self._pending_replies.pop(correlation_id, None)

    async def reply(
        self,
        *,
        original_message: AgentMessage,
        sender: str,
        payload: dict[str, Any],
    ) -> AgentMessage:
        """Reply to a request message."""
        return await self.send(
            sender=sender,
            recipient=original_message.sender_agent_id,
            payload=payload,
            message_type=MessageType.REPLY,
            correlation_id=original_message.correlation_id,
            reply_to=original_message.message_id,
        )

    async def subscribe(self, agent_id: str, topic: str) -> None:
        """Subscribe an agent to a topic."""
        normalized_agent = (agent_id or "").strip().lower()
        normalized_topic = (topic or "").strip().lower()
        if normalized_agent and normalized_topic:
            async with self._lock:
                self._topic_subscribers[normalized_topic].add(normalized_agent)

    async def unsubscribe(self, agent_id: str, topic: str) -> None:
        """Unsubscribe an agent from a topic."""
        normalized_agent = (agent_id or "").strip().lower()
        normalized_topic = (topic or "").strip().lower()
        async with self._lock:
            self._topic_subscribers.get(normalized_topic, set()).discard(normalized_agent)

    async def publish(
        self,
        *,
        sender: str,
        topic: str,
        payload: dict[str, Any],
        priority: str = MessagePriority.NORMAL,
    ) -> AgentMessage:
        """Publish a message to a topic."""
        return await self.send(
            sender=sender,
            recipient=f"topic:{topic}",
            payload=payload,
            message_type=MessageType.TOPIC,
            topic=topic,
            priority=priority,
        )

    async def receive(self, agent_id: str) -> AgentMessage | None:
        """Non-blocking receive: get next message for an agent."""
        normalized = (agent_id or "").strip().lower()
        async with self._lock:
            mailbox = self._mailboxes.get(normalized)
        if mailbox is None:
            return None
        return mailbox.dequeue()

    async def receive_wait(self, agent_id: str, timeout: float = 30.0) -> AgentMessage | None:
        """Blocking receive: wait for a message for an agent."""
        normalized = (agent_id or "").strip().lower()
        async with self._lock:
            mailbox = self._mailboxes.get(normalized)
        if mailbox is None:
            return None
        return await mailbox.wait_for_message(timeout=timeout)

    async def get_pending_count(self, agent_id: str) -> int:
        """Get number of pending messages for an agent."""
        normalized = (agent_id or "").strip().lower()
        async with self._lock:
            mailbox = self._mailboxes.get(normalized)
        return mailbox.pending_count if mailbox else 0

    # --- Internal delivery ---

    async def _deliver_direct(self, message: AgentMessage) -> None:
        """Deliver a message directly to a single recipient."""
        recipient = message.recipient_agent_id
        async with self._lock:
            mailbox = self._mailboxes.get(recipient)

        if mailbox is None:
            self._dead_letter_queue.append(message)
            self._failed_count += 1
            logger.warning("Dead letter: recipient '%s' not registered", recipient)
            return

        if not mailbox.enqueue(message):
            self._dead_letter_queue.append(message)
            self._failed_count += 1
            logger.warning("Dead letter: mailbox full for '%s'", recipient)
            return

        self._delivered_count += 1

        # Auto-invoke handler if registered
        handler = self._message_handlers.get(recipient)
        if handler is not None:
            try:
                reply = await asyncio.wait_for(handler(message), timeout=30.0)
                if reply is not None and message.message_type == MessageType.REQUEST:
                    await self.reply(
                        original_message=message,
                        sender=recipient,
                        payload=reply.payload if isinstance(reply, AgentMessage) else {"result": str(reply)},
                    )
            except asyncio.TimeoutError:
                logger.warning("Handler timeout for agent '%s'", recipient)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Handler error for agent '%s'", recipient)

    async def _broadcast(self, message: AgentMessage) -> None:
        """Deliver a message to all registered agents except the sender."""
        async with self._lock:
            targets = [
                aid for aid in self._mailboxes
                if aid != message.sender_agent_id
            ]
        for target_id in targets:
            broadcast_copy = AgentMessage(
                message_id=str(uuid4()),
                sender_agent_id=message.sender_agent_id,
                recipient_agent_id=target_id,
                message_type=MessageType.BROADCAST,
                payload=message.payload,
                timestamp=message.timestamp,
                priority=message.priority,
                correlation_id=message.correlation_id,
                session_id=message.session_id,
                topic=message.topic,
                metadata=message.metadata,
            )
            await self._deliver_direct(broadcast_copy)

    async def _publish_topic(self, message: AgentMessage, topic: str) -> None:
        """Deliver a message to all subscribers of a topic."""
        normalized_topic = topic.strip().lower()
        async with self._lock:
            subscribers = set(self._topic_subscribers.get(normalized_topic, set()))
        subscribers.discard(message.sender_agent_id)
        for subscriber_id in subscribers:
            topic_copy = AgentMessage(
                message_id=str(uuid4()),
                sender_agent_id=message.sender_agent_id,
                recipient_agent_id=subscriber_id,
                message_type=MessageType.TOPIC,
                payload=message.payload,
                timestamp=message.timestamp,
                priority=message.priority,
                correlation_id=message.correlation_id,
                session_id=message.session_id,
                topic=topic,
                metadata=message.metadata,
            )
            await self._deliver_direct(topic_copy)

    async def _deliver_reply(self, message: AgentMessage) -> None:
        """Deliver a reply, resolving any pending futures."""
        correlation_id = message.correlation_id
        if correlation_id and correlation_id in self._pending_replies:
            future = self._pending_replies.pop(correlation_id)
            if not future.done():
                future.set_result(message)
        # Also deliver to mailbox
        await self._deliver_direct(message)

    async def stats(self) -> dict[str, Any]:
        """Get message bus statistics."""
        async with self._lock:
            return {
                "session_id": self._session_id,
                "registered_agents": list(self._mailboxes.keys()),
                "total_sent": self._sent_count,
                "total_delivered": self._delivered_count,
                "total_failed": self._failed_count,
                "dead_letters": len(self._dead_letter_queue),
                "pending_replies": len(self._pending_replies),
                "topics": {
                    topic: list(subs) for topic, subs in self._topic_subscribers.items()
                },
                "mailbox_sizes": {
                    aid: mb.pending_count for aid, mb in self._mailboxes.items()
                },
            }
