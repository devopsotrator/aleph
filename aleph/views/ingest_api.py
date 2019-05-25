import os
import json
import shutil
import logging
from flask import Blueprint, request
from tempfile import mkdtemp
from werkzeug.exceptions import BadRequest
from normality import safe_filename, stringify

from aleph.core import db, archive
from aleph.model import Document
from aleph.queues import ingest_entity
from aleph.views.util import get_db_collection
from aleph.views.util import jsonify, validate_data
from aleph.views.forms import DocumentCreateSchema

log = logging.getLogger(__name__)
blueprint = Blueprint('ingest_api', __name__)


def _load_parent(collection, meta):
    """Determine the parent document for the document that is to be
    ingested."""
    if meta.get('parent_id') is None:
        return
    parent = Document.by_id(meta.get('parent_id'), collection_id=collection.id)
    if parent is None:
        raise BadRequest(response=jsonify({
            'status': 'error',
            'message': 'Cannot load parent document'
        }, status=400))
    return parent


def _load_metadata():
    """Unpack the common, pre-defined metadata for all the uploaded files."""
    try:
        meta = json.loads(request.form.get('meta', '{}'))
    except Exception as ex:
        raise BadRequest(str(ex))

    validate_data(meta, DocumentCreateSchema)
    foreign_id = stringify(meta.get('foreign_id'))
    if not len(request.files) and foreign_id is None:
        raise BadRequest(response=jsonify({
            'status': 'error',
            'message': 'Directories need to have a foreign_id'
        }, status=400))
    return meta, foreign_id


@blueprint.route('/api/2/collections/<int:collection_id>/ingest',
                 methods=['POST', 'PUT'])
def ingest_upload(collection_id):
    collection = get_db_collection(collection_id, request.authz.WRITE)
    meta, foreign_id = _load_metadata()
    parent = _load_parent(collection, meta)
    upload_dir = mkdtemp(prefix='aleph.upload.')
    try:
        content_hash = None
        for storage in request.files.values():
            path = safe_filename(storage.filename, default='upload')
            path = os.path.join(upload_dir, path)
            storage.save(path)
            content_hash = archive.archive_file(path)
        document = Document.save(collection_id=collection_id,
                                 parent_id=parent.id,
                                 foreign_id=foreign_id,
                                 content_hash=content_hash,
                                 meta=meta)
        db.session.commit()
        ingest_entity(collection, document.to_proxy())
    finally:
        shutil.rmtree(upload_dir)

    return jsonify({
        'status': 'ok',
        'id': stringify(document.id)
    }, status=201)
