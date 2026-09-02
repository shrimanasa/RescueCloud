from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger("rescuecloud.eventbus")

try:
    import redis
except ImportError:
    redis = None


class EventBus:
    """
    Unified Redis Pub/Sub Event Bus with graceful in-memory fallback.
    Enables distributed, decoupled microservice communication and agent orchestration.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
    ):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = int(port or os.getenv("REDIS_PORT", "6379"))
        self.password = password or os.getenv("REDIS_PASSWORD", None)

        self._redis_client: Optional[Any] = None
        self._pubsub: Optional[Any] = None
        self._connected = False
        self._local_subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._lock = threading.Lock()
        self._running = True

        self._init_connection()

    def _init_connection(self) -> None:
        if redis is None:
            logger.warning("redis-py not installed. Falling back to local in-process event bus.")
            return

        try:
            self._redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            # Ping test
            self._redis_client.ping()
            self._connected = True
            logger.info(f"Connected to Redis Pub/Sub at {self.host}:{self.port}")
        except Exception as exc:
            self._connected = False
            logger.warning(f"Could not connect to Redis at {self.host}:{self.port} ({exc}). Using in-memory fallback.")

    def publish(self, channel: str, message: Any) -> None:
        """Publish a message (Pydantic model, dict, or str) to a Redis channel."""
        payload_str = ""
        payload_dict = {}

        if isinstance(message, BaseModel):
            payload_str = message.model_dump_json()
            payload_dict = message.model_dump()
        elif isinstance(message, dict):
            payload_str = json.dumps(message)
            payload_dict = message
        else:
            payload_str = str(message)
            payload_dict = {"raw": payload_str}

        # 1. Dispatch through Redis if available
        if self._connected and self._redis_client:
            try:
                self._redis_client.publish(channel, payload_str)
            except Exception as exc:
                logger.warning(f"Redis publish failed to {channel}: {exc}. Emitting locally.")
                self._connected = False

        # 2. Dispatch to local subscribers (handles fallback or intra-process delivery)
        with self._lock:
            callbacks = list(self._local_subscribers.get(channel, []))
            wildcard_callbacks = list(self._local_subscribers.get("*", []))

        for cb in callbacks + wildcard_callbacks:
            try:
                cb(payload_dict)
            except Exception as err:
                logger.error(f"Error in local event subscriber callback: {err}")

    def subscribe(
        self,
        channels: List[str],
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Subscribe to one or more channels with a handler callback."""
        with self._lock:
            for ch in channels:
                if ch not in self._local_subscribers:
                    self._local_subscribers[ch] = []
                self._local_subscribers[ch].append(callback)

        if self._connected and self._redis_client:
            def _redis_listener():
                try:
                    pubsub = self._redis_client.pubsub()
                    pubsub.subscribe(*channels)
                    for raw in pubsub.listen():
                        if not self._running:
                            break
                        if raw["type"] == "message":
                            try:
                                data = json.loads(raw["data"])
                            except Exception:
                                data = {"raw": raw["data"]}
                            try:
                                callback(data)
                            except Exception as e:
                                logger.error(f"Subscriber callback error: {e}")
                except Exception as exc:
                    logger.warning(f"Redis subscriber loop error on {channels}: {exc}")

            t = threading.Thread(target=_redis_listener, daemon=True)
            t.start()

    def close(self) -> None:
        self._running = False
        if self._redis_client:
            try:
                self._redis_client.close()
            except Exception:
                pass


# Global singleton instance
_default_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus
