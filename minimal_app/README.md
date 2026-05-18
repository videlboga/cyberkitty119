Minimal Transkribator skeleton

Structure:
- minimal_app/db.py - sqlalchemy engine/session + Base
- minimal_app/models.py - ProcessingJob model
- minimal_app/queue.py - simple enqueue/acquire/complete/fail helpers
- minimal_app/bot.py - minimal handler that enqueues jobs
- minimal_app/worker.py - worker loop stub

How to run tests:

```bash
PYTHONPATH=. pytest -q tests/test_minimal_app_queue.py
```
