"""
Stage 20 — RQ worker process. Run alongside the API server:
python worker.py

Uses RQ's SimpleWorker, not the default Worker — the default forks worker
processes via os.fork(), which doesn't exist on Windows. SimpleWorker runs
jobs in-process sequentially instead; fine for a single-instance pilot
deployment, the real multi-worker scaling story is Linux-deployment territory
anyway (same as most of Stage 20's "real infra" half).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from rq import SimpleWorker, Queue
from rq.serializers import JSONSerializer
from job_queue import get_redis_connection, QUEUE_NAME

if __name__ == "__main__":
    conn = get_redis_connection()
    queue = Queue(QUEUE_NAME, connection=conn, serializer=JSONSerializer)
    worker = SimpleWorker([queue], connection=conn, serializer=JSONSerializer)
    print("RQ worker started, listening on queue 'caseweave-process'...")
    worker.work()
