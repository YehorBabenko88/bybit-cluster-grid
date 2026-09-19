# Failure model

## Internet/WebSocket outage
- detect failed connection
- exponential backoff with jitter
- wait for internet reachability
- reconnect and re-subscribe
- order-book snapshot replaces stale local state
- coordinator eventually reassigns symbols when node heartbeat is lost

## PostgreSQL outage
- ingestion and persistence are separated by bounded queues
- failed writes retry with exponential delay
- idempotent keys / conflict handling allow replay without duplicate analytical rows

## Worker overload
- worker heartbeat reports CPU/RAM/free disk
- coordinator capacity score drops to zero above configured pressure limits
- symbols are redistributed
- no fixed assumption that exactly five computers exist

## Disk pressure
- node stops receiving new assignments when reserve is breached
- future retention jobs purge raw/high-frequency history before compact analytical aggregates

## Process crash
- intended deployment uses an OS service with automatic restart
- structured JSONL rotating logs preserve diagnostics
