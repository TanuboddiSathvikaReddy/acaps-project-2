"""Bounded packet queue (the router output buffer).

* Capacity K counts WAITING packets only; the packet being transmitted is not in the buffer.
* Items are kept in enqueue order (= arrival order).
* Drop policy (tail-drop, class-blind) is applied by the engine: `try_enqueue` returns False
  when the buffer is full and the ENGINE records the drop with its reason.
"""

from acaps.core.packet import Packet


class BoundedQueue:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("queue capacity must be >= 1")
        self.capacity = capacity
        self._items: list[Packet] = []

    def __len__(self) -> int:
        return len(self._items)

    @property
    def is_full(self) -> bool:
        return len(self._items) >= self.capacity

    @property
    def occupancy(self) -> float:
        """queueOccupancy = currentQueueLength / queueCapacity."""
        return len(self._items) / self.capacity

    def try_enqueue(self, packet: Packet) -> bool:
        if self.is_full:
            return False
        self._items.append(packet)
        return True

    def remove(self, packet: Packet) -> None:
        """Remove a specific waiting packet (identity match). Raises KeyError if absent."""
        for index, item in enumerate(self._items):
            if item is packet:
                del self._items[index]
                return
        raise KeyError(f"packet {packet.packet_id} is not in the queue")

    def items(self) -> tuple[Packet, ...]:
        return tuple(self._items)
