from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
import weakref

from ..domain.domain import RuntimeEvent, RuntimeEventType


@dataclass
class EventSubscription:
    """事件订阅"""
    callback: Callable[[RuntimeEvent], None]
    event_types: set[RuntimeEventType] | None = None  # None 表示订阅所有事件


class EventBus:
    """简单的事件总线，支持同步和异步事件发布"""

    def __init__(self):
        self._subscriptions: dict[RuntimeEventType, list[weakref.ref[EventSubscription]]] = defaultdict(list)
        self._all_event_subscriptions: list[weakref.ref[EventSubscription]] = []
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        callback: Callable[[RuntimeEvent], None],
        event_types: RuntimeEventType | list[RuntimeEventType] | None = None
    ) -> EventSubscription:
        """订阅事件

        Args:
            callback: 事件回调函数
            event_types: 要订阅的事件类型，None 表示订阅所有事件

        Returns:
            EventSubscription: 订阅对象，可用于取消订阅
        """
        subscription = EventSubscription(callback=callback)

        if event_types is None:
            # 订阅所有事件
            self._all_event_subscriptions.append(weakref.ref(subscription))
        else:
            # 订阅特定事件类型
            if isinstance(event_types, str):
                event_types = [event_types]

            subscription.event_types = set(event_types)
            for event_type in event_types:
                self._subscriptions[event_type].append(weakref.ref(subscription))

        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """取消订阅"""
        # 从所有事件订阅中移除
        self._all_event_subscriptions = [
            ref for ref in self._all_event_subscriptions
            if ref() is not subscription
        ]

        # 从特定事件类型订阅中移除
        for event_type in list(self._subscriptions.keys()):
            self._subscriptions[event_type] = [
                ref for ref in self._subscriptions[event_type]
                if ref() is not subscription
            ]

    def publish(self, event: RuntimeEvent) -> None:
        """发布事件（同步）"""
        # 调用所有订阅了该事件类型的回调
        if event.type in self._subscriptions:
            for ref in self._subscriptions[event.type][:]:  # 复制列表以防在回调中修改
                subscription = ref()
                if subscription is not None:
                    try:
                        subscription.callback(event)
                    except Exception:
                        # 避免一个回调的异常影响其他回调
                        import traceback
                        traceback.print_exc()

        # 调用订阅了所有事件的回调
        for ref in self._all_event_subscriptions[:]:
            subscription = ref()
            if subscription is not None:
                try:
                    subscription.callback(event)
                except Exception:
                    import traceback
                    traceback.print_exc()

    async def publish_async(self, event: RuntimeEvent) -> None:
        """发布事件（异步）"""
        async with self._lock:
            self.publish(event)

    def clear(self) -> None:
        """清除所有订阅"""
        self._subscriptions.clear()
        self._all_event_subscriptions.clear()


# 全局事件总线实例
_global_event_bus: EventBus | None = None


def get_global_event_bus() -> EventBus:
    """获取全局事件总线实例"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def publish_event(event: RuntimeEvent) -> None:
    """发布事件到全局事件总线"""
    get_global_event_bus().publish(event)


async def publish_event_async(event: RuntimeEvent) -> None:
    """异步发布事件到全局事件总线"""
    await get_global_event_bus().publish_async(event)


def subscribe_to_events(
    callback: Callable[[RuntimeEvent], None],
    event_types: RuntimeEventType | list[RuntimeEventType] | None = None
) -> EventSubscription:
    """订阅全局事件总线的事件"""
    return get_global_event_bus().subscribe(callback, event_types)


class EventHandler:
    """事件处理器基类，简化事件订阅"""

    def __init__(self, event_bus: EventBus | None = None):
        self._event_bus = event_bus or get_global_event_bus()
        self._subscriptions: list[EventSubscription] = []

    def subscribe(
        self,
        event_types: RuntimeEventType | list[RuntimeEventType] | None = None
    ) -> Callable:
        """装饰器：订阅事件"""
        def decorator(func: Callable[[RuntimeEvent], None]) -> Callable[[RuntimeEvent], None]:
            subscription = self._event_bus.subscribe(func, event_types)
            self._subscriptions.append(subscription)
            return func
        return decorator

    def unsubscribe_all(self) -> None:
        """取消所有订阅"""
        for subscription in self._subscriptions:
            self._event_bus.unsubscribe(subscription)
        self._subscriptions.clear()

    def __del__(self):
        self.unsubscribe_all()