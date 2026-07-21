"""Domain model boundary.

Concrete immutable state dataclasses are intentionally deferred to the protocol-contract
delivery so that no endpoint starts depending on an untested wire schema.
"""

from typing import TypeAlias

SequenceNumber: TypeAlias = int
MessageId: TypeAlias = str
