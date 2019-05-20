import logging

from aleph.core import settings
from aleph.model import Collection
from aleph.queue import get_next_task, get_rate_limit
from aleph.queue import OP_INDEX, OP_BULKLOAD, OP_PROCESS
from aleph.logic.alerts import check_alerts
from aleph.logic.collections import index_collections
from aleph.logic.notifications import generate_digest
from aleph.logic.bulkload import bulk_load
from aleph.logic.processing import index_aggregate, process_collection

log = logging.getLogger(__name__)


def hourly_tasks():
    index_collections()


def daily_tasks():
    check_alerts()
    generate_digest()


def queue_worker(timeout=5):
    hourly = get_rate_limit('hourly', unit=3600, interval=1, limit=1)
    daily = get_rate_limit('daily', unit=3600, interval=24, limit=1)
    log.info("Listening for incoming tasks...")
    while True:
        if hourly.check():
            hourly_tasks()
            hourly.update()
        if daily.check():
            daily_tasks()
            daily.update()

        queue, payload, context = get_next_task(timeout=timeout)
        if queue is None:
            continue
        try:
            collection = Collection.by_foreign_id(queue.dataset)
            if queue.operation == OP_INDEX:
                unsafe = payload.get('unsafe', False)
                index_aggregate(collection, unsafe=unsafe)
            if queue.operation == OP_BULKLOAD:
                bulk_load(queue, collection, payload)
            if queue.operation == OP_PROCESS:
                process_collection(collection)
        finally:
            queue.task_done()


def sync_worker():
    if settings.EAGER:
        queue_worker(timeout=1)
