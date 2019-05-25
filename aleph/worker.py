import logging

from aleph.core import db, settings
from aleph.model import Collection
from aleph.queues import get_next_task, get_rate_limit
from aleph.queues import OP_INDEX, OP_BULKLOAD, OP_PROCESS, OP_XREF
from aleph.logic.alerts import check_alerts
from aleph.logic.collections import index_collections
from aleph.logic.notifications import generate_digest
from aleph.logic.bulkload import bulk_load
from aleph.logic.xref import xref_collection
from aleph.logic.processing import index_aggregate, process_collection

log = logging.getLogger(__name__)


def hourly_tasks():
    log.info("Running hourly tasks...")
    index_collections()


def daily_tasks():
    log.info("Running daily tasks...")
    check_alerts()
    generate_digest()


def handle_task(queue, payload, context):
    log.info("Task [%s->%s]: %r", queue.dataset, queue.operation, payload)
    try:
        collection = Collection.by_foreign_id(queue.dataset)
        if queue.operation == OP_INDEX:
            unsafe = payload.get('unsafe', False)
            index_aggregate(collection, unsafe=unsafe)
        if queue.operation == OP_BULKLOAD:
            bulk_load(queue, collection, payload)
        if queue.operation == OP_PROCESS:
            process_collection(collection)
        if queue.operation == OP_XREF:
            against = payload.get('against_collection_ids')
            xref_collection(queue, collection,
                            against_collection_ids=against)
    finally:
        queue.task_done()
        db.session.remove()


def queue_worker(timeout=5):
    hourly = get_rate_limit('hourly', unit=3600, interval=1, limit=1)
    daily = get_rate_limit('daily', unit=3600, interval=24, limit=1)
    log.info("Aleph worker started.")
    while True:
        if hourly.check():
            hourly_tasks()
            hourly.update()
        if daily.check():
            daily_tasks()
            daily.update()

        queue, payload, context = get_next_task(timeout=timeout)
        if queue is None:
            log.info("Waiting for queue tasks.")
            continue
        handle_task(queue, payload, context)


def sync_worker(timeout=1):
    if settings.EAGER:
        while True:
            queue, payload, context = get_next_task(timeout=timeout)
            if queue is None:
                return
            handle_task(queue, payload, context)
