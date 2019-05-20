# coding: utf-8
import os
import logging
from pprint import pprint  # noqa
from banal import ensure_list
from normality import slugify
from ingestors.util import decode_path
from alephclient.util import load_config_file
from flask_script import Manager, commands as flask_script_commands
from flask_script.commands import ShowUrls
from flask_migrate import MigrateCommand

from aleph.core import create_app, db, cache
from aleph.model import Collection, Document, Role
from aleph.migration import upgrade_system, destroy_db, cleanup_deleted
from aleph.views import mount_app_blueprints
from aleph.worker import queue_worker, sync_worker, hourly_tasks, daily_tasks
from aleph.queue import get_queue, get_status, OP_BULKLOAD, OP_PROCESS
from aleph.index.admin import delete_index
from aleph.logic.processing import process_collection
from aleph.logic.collections import create_collection, update_collection
from aleph.logic.collections import index_collections, index_collection
from aleph.logic.collections import delete_collection
from aleph.logic.roles import update_role, update_roles
from aleph.logic.entities.xref import xref_collection
from aleph.logic.entities.rdf import export_collection
from aleph.logic.permissions import update_permission

log = logging.getLogger('aleph')
flask_script_commands.text_type = str

app = create_app()
mount_app_blueprints(app)
manager = Manager(app)
manager.add_command('db', MigrateCommand)
manager.add_command('routes', ShowUrls)


def get_collection(foreign_id):
    collection = Collection.by_foreign_id(foreign_id, deleted=True)
    if collection is None:
        raise ValueError("No such collection: %r" % foreign_id)
    return collection


@manager.command
def collections():
    """List all collections."""
    for collection in Collection.all():
        print(collection.id, collection.foreign_id, collection.label)


@manager.command
def scheduled():
    """Run scheduled clean-up and notification operations."""
    hourly_tasks()
    daily_tasks()


@manager.command
def worker():
    """Run the queue-based worker service."""
    queue_worker()


# @manager.command
# @manager.option('-l', '--language', dest='language', nargs='*')
# @manager.option('-f', '--foreign_id', dest='foreign_id')
# def crawldir(path, language=None, foreign_id=None):
#     """Crawl the given directory."""
#     path = decode_path(os.path.abspath(os.path.normpath(path)))
#     if path is None or not os.path.exists(path):
#         log.error("Invalid path: %r", path)
#         return
#     path_name = os.path.basename(path)

#     if foreign_id is None:
#         foreign_id = 'directory:%s' % slugify(path)

#     collection = create_collection({
#         'foreign_id': foreign_id,
#         'label': path_name,
#         'languages': language
#     })
#     collection_id = collection.get('id')
#     log.info('Crawling %s to %s (%s)...', path, foreign_id, collection_id)
#     document = Document.by_keys(collection_id=collection_id, foreign_id=path)
#     document.file_name = path_name
#     db.session.commit()
#     ingest_document(document, path)


@manager.command
def delete(foreign_id):
    """Delete all the contents for a given collecton."""
    collection = get_collection(foreign_id)
    delete_collection(collection)


@manager.command
def flushdeleted():
    """Remove soft-deleted database objects."""
    cleanup_deleted()


@manager.command
def process(foreign_id):
    """Re-process documents in the given collection."""
    collection = get_collection(foreign_id)
    queue = get_queue(collection, OP_PROCESS)
    queue.queue_task({}, {})
    sync_worker()


@manager.command
@manager.option('-f', '--foreign_id')
@manager.option('-e', '--entities', default=False)
def repair(foreign_id=None, entities=False):
    """Re-index all the collections and entities."""
    update_roles()
    if foreign_id:
        collection = get_collection(foreign_id)
        index_collection(collection, entities=entities, refresh=True)
    else:
        index_collections(entities=entities, refresh=True)


@manager.option('-a', '--against', dest='against', nargs='*', help='foreign-ids of collections to xref against')  # noqa
@manager.option('-f', '--foreign_id', dest='foreign_id', required=True, help='foreign-id of collection to xref')  # noqa
def xref(foreign_id, against=None):
    """Cross-reference all entities and documents in a collection."""
    collection = get_collection(foreign_id)
    against = ensure_list(against)
    against = [get_collection(c).id for c in against]
    xref_collection(collection.id, against_collection_ids=against)


@manager.command
def bulkload(file_name):
    """Index all the entities in a given dataset."""
    log.info("Loading bulk data from: %s", file_name)
    config = load_config_file(file_name)
    for foreign_id, data in config.items():
        data['foreign_id'] = foreign_id
        data['label'] = data.get('label', foreign_id)
        create_collection(data)
        collection = Collection.by_foreign_id(foreign_id)
        queue = get_queue(collection, OP_BULKLOAD)
        queue.queue_task(data, {})
        sync_worker()


@manager.command
def status(foreign_id):
    collection = get_collection(foreign_id)
    status = get_status(collection)
    pprint(status)


@manager.command
@manager.option('-n', '--name', dest='name')
@manager.option('-e', '--email', dest='email')
@manager.option('-i', '--is_admin', dest='is_admin')
@manager.option('-p', '--password', dest='password')
def createuser(foreign_id, password=None, name=None, email=None,
               is_admin=False):
    """Create a user and show their API key."""
    role = Role.load_or_create(foreign_id, Role.USER,
                               name or foreign_id,
                               email=email or "user@example.com",
                               is_admin=is_admin)
    if password is not None:
        role.set_password(password)
    db.session.add(role)
    db.session.commit()
    update_role(role)
    return role.api_key


@manager.command
def publish(foreign_id):
    """Make a collection visible to all users."""
    collection = get_collection(foreign_id)
    role = Role.by_foreign_id(Role.SYSTEM_GUEST)
    editor = Role.load_cli_user()
    update_permission(role, collection, True, False, editor_id=editor.id)
    update_collection(collection)


@manager.command
def rdf(foreign_id):
    """Generate a RDF triples for the given collection."""
    collection = get_collection(foreign_id)
    for line in export_collection(collection):
        line = line.strip().decode('utf-8')
        if len(line):
            print(line)


@manager.command
def upgrade():
    """Create or upgrade the search index and database."""
    upgrade_system()


@manager.command
def resetindex():
    """Re-create the ES index configuration, dropping all data."""
    delete_index()
    upgrade()


@manager.command
def resetcache():
    """Clear the redis cache."""
    cache.flush()


@manager.command
def evilshit():
    """EVIL: Delete all data and recreate the database."""
    delete_index()
    destroy_db()
    upgrade()


def main():
    manager.run()


if __name__ == "__main__":
    main()
