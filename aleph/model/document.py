import cgi
import logging
from normality import slugify
from followthemoney import model
from followthemoney.types import registry
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm.attributes import flag_modified

from aleph.core import db, cache
from aleph.model.metadata import Metadata
from aleph.model.collection import Collection
from aleph.model.common import DatedModel
from aleph.model.document_record import DocumentRecord
from aleph.model.document_tag import DocumentTag
from aleph.util import filter_texts

log = logging.getLogger(__name__)


class Document(db.Model, DatedModel, Metadata):
    MAX_TAGS = 10000

    SCHEMA = 'Document'
    SCHEMA_FOLDER = 'Folder'
    SCHEMA_PACKAGE = 'Package'
    SCHEMA_WORKBOOK = 'Workbook'
    SCHEMA_TEXT = 'PlainText'
    SCHEMA_HTML = 'HyperText'
    SCHEMA_PDF = 'Pages'
    SCHEMA_IMAGE = 'Image'
    SCHEMA_AUDIO = 'Audio'
    SCHEMA_VIDEO = 'Video'
    SCHEMA_TABLE = 'Table'
    SCHEMA_EMAIL = 'Email'

    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAIL = 'fail'

    id = db.Column(db.BigInteger, primary_key=True)
    content_hash = db.Column(db.Unicode(65), nullable=True, index=True)
    foreign_id = db.Column(db.Unicode, unique=False, nullable=True, index=True)
    schema = db.Column(db.String(255), nullable=False)
    status = db.Column(db.Unicode(10), nullable=True)
    meta = db.Column(JSONB, default={})
    error_message = db.Column(db.Unicode(), nullable=True)
    body_text = db.Column(db.Unicode(), nullable=True)
    body_raw = db.Column(db.Unicode(), nullable=True)

    uploader_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=True)  # noqa
    parent_id = db.Column(db.BigInteger, db.ForeignKey('document.id'), nullable=True, index=True)  # noqa
    children = db.relationship('Document', lazy='dynamic', backref=db.backref('parent', uselist=False, remote_side=[id]))   # noqa
    collection_id = db.Column(db.Integer, db.ForeignKey('collection.id'), nullable=False, index=True)  # noqa
    collection = db.relationship(Collection, backref=db.backref('documents', lazy='dynamic'))  # noqa

    def __init__(self, **kw):
        self.meta = {}
        super(Document, self).__init__(**kw)

    @property
    def model(self):
        return model.get(self.schema)

    @property
    def name(self):
        if self.title is not None:
            return self.title
        if self.file_name is not None:
            return self.file_name
        if self.source_url is not None:
            return self.source_url

    @property
    def supports_records(self):
        # Slightly unintuitive naming: this just checks the document type,
        # not if there actually are any records.
        return self.schema in [self.SCHEMA_PDF, self.SCHEMA_TABLE]

    @property
    def supports_pages(self):
        return self.schema == self.SCHEMA_PDF

    @property
    def supports_nlp(self):
        structural = [
            Document.SCHEMA,
            Document.SCHEMA_PACKAGE,
            Document.SCHEMA_FOLDER,
            Document.SCHEMA_WORKBOOK,
            Document.SCHEMA_VIDEO,
            Document.SCHEMA_AUDIO,
        ]
        return self.schema not in structural

    @property
    def ancestors(self):
        if self.parent_id is None:
            return []
        key = cache.key('ancestors', self.id)
        ancestors = cache.get_list(key)
        if len(ancestors):
            return ancestors
        parent_key = cache.key('ancestors', self.parent_id)
        ancestors = cache.get_list(parent_key)
        if not len(ancestors):
            ancestors = []
            parent = Document.by_id(self.parent_id)
            if parent is not None:
                ancestors = parent.ancestors
        ancestors.append(self.parent_id)
        if self.model.is_a(model.get(self.SCHEMA_FOLDER)):
            cache.set_list(key, ancestors, expire=cache.EXPIRE)
        return ancestors

    def update(self, data):
        props = ('title', 'summary', 'author', 'crawler', 'source_url',
                 'file_name', 'mime_type', 'headers', 'date', 'authored_at',
                 'modified_at', 'published_at', 'retrieved_at', 'languages',
                 'countries', 'keywords')
        for prop in props:
            value = data.get(prop, self.meta.get(prop))
            setattr(self, prop, value)
        db.session.add(self)

    def update_meta(self):
        flag_modified(self, 'meta')

    def delete_records(self):
        pq = db.session.query(DocumentRecord)
        pq = pq.filter(DocumentRecord.document_id == self.id)
        pq.delete()
        db.session.flush()

    def delete_tags(self):
        pq = db.session.query(DocumentTag)
        pq = pq.filter(DocumentTag.document_id == self.id)
        pq.delete()
        db.session.flush()

    def delete(self, deleted_at=None):
        self.delete_records()
        self.delete_tags()
        db.session.delete(self)

    @classmethod
    def delete_by_collection(cls, collection_id, deleted_at=None):
        documents = db.session.query(cls.id)
        documents = documents.filter(cls.collection_id == collection_id)
        documents = documents.subquery()

        pq = db.session.query(DocumentRecord)
        pq = pq.filter(DocumentRecord.document_id.in_(documents))
        pq.delete(synchronize_session=False)

        pq = db.session.query(DocumentTag)
        pq = pq.filter(DocumentTag.document_id.in_(documents))
        pq.delete(synchronize_session=False)

        pq = db.session.query(cls)
        pq = pq.filter(cls.collection_id == collection_id)
        pq.delete(synchronize_session=False)

    def raw_texts(self):
        yield self.title
        yield self.file_name
        yield self.source_url
        yield self.summary
        yield self.author

        if self.status != self.STATUS_SUCCESS:
            return

        yield self.body_text
        if self.supports_records:
            # iterate over all the associated records.
            pq = db.session.query(DocumentRecord)
            pq = pq.filter(DocumentRecord.document_id == self.id)
            pq = pq.order_by(DocumentRecord.index.asc())
            for record in pq.yield_per(10000):
                yield from record.raw_texts()

    @property
    def texts(self):
        yield from filter_texts(self.raw_texts())

    @classmethod
    def by_keys(cls, parent_id=None, collection_id=None, foreign_id=None,
                content_hash=None):
        """Try and find a document by various criteria."""
        q = cls.all()
        q = q.filter(Document.collection_id == collection_id)

        if parent_id is not None:
            q = q.filter(Document.parent_id == parent_id)

        if foreign_id is not None:
            q = q.filter(Document.foreign_id == foreign_id)
        elif content_hash is not None:
            q = q.filter(Document.content_hash == content_hash)
        else:
            raise ValueError("No unique criterion for document.")

        document = q.first()
        if document is None:
            document = cls()
            document.schema = cls.SCHEMA
            document.collection_id = collection_id

        if parent_id is not None:
            document.parent_id = parent_id

        if foreign_id is not None:
            document.foreign_id = foreign_id

        if content_hash is not None:
            document.content_hash = content_hash

        db.session.add(document)
        return document

    @classmethod
    def by_id(cls, id, collection_id=None):
        if id is None:
            return
        q = cls.all()
        q = q.filter(cls.id == id)
        if collection_id is not None:
            q = q.filter(cls.collection_id == collection_id)
        return q.first()

    @classmethod
    def by_collection(cls, collection_id=None):
        q = cls.all()
        q = q.filter(cls.collection_id == collection_id)
        return q

    @classmethod
    def find_ids(cls, collection_id=None, failed_only=False):
        q = cls.all_ids()
        if collection_id is not None:
            q = q.filter(cls.collection_id == collection_id)
        if failed_only:
            q = q.filter(cls.status != cls.STATUS_SUCCESS)
        q = q.order_by(cls.id.asc())
        return q

    def to_proxy(self):
        meta = dict(self.meta)
        headers = meta.pop('headers', {})
        headers = {slugify(k, sep='_'): v for k, v in headers.items()}
        proxy = model.get_proxy({
            'id': str(self.id),
            'schema': self.model,
            'properties': meta
        })
        proxy.set('contentHash', self.content_hash)
        proxy.set('parent', self.parent_id)
        proxy.set('ancestors', self.ancestors)
        proxy.set('processingStatus', self.status)
        proxy.set('processingError', self.error_message)
        proxy.set('fileSize', meta.get('file_size'))
        proxy.set('fileName', meta.get('file_name'))
        if not proxy.has('fileName'):
            disposition = headers.get('content_disposition')
            if disposition is not None:
                _, attrs = cgi.parse_header(disposition)
                proxy.set('fileName', attrs.get('filename'))
        proxy.set('mimeType', meta.get('mime_type'))
        if not proxy.has('mimeType'):
            proxy.set('mimeType', headers.get('content_type'))
        proxy.set('language', meta.get('languages'))
        proxy.set('country', meta.get('countries'))
        proxy.set('authoredAt', meta.get('authored_at'))
        proxy.set('modifiedAt', meta.get('modified_at'))
        proxy.set('publishedAt', meta.get('published_at'))
        proxy.set('retrievedAt', meta.get('retrieved_at'))
        proxy.set('sourceUrl', meta.get('source_url'))
        proxy.set('messageId', meta.get('message_id'), quiet=True)
        proxy.set('inReplyTo', meta.get('in_reply_to'), quiet=True)
        proxy.set('bodyText', self.body_text, quiet=True)
        proxy.set('bodyHtml', self.body_raw, quiet=True)
        columns = meta.get('columns')
        proxy.set('columns', registry.json.pack(columns), quiet=True)
        proxy.set('headers', registry.json.pack(headers), quiet=True)

        pdf = 'application/pdf'
        if meta.get('extension') == 'pdf' or proxy.first('mimeType') == pdf:
            proxy.set('pdfHash', self.content_hash, quiet=True)
        proxy.add('pdfHash', meta.get('pdf_version'), quiet=True)

        q = db.session.query(DocumentTag)
        q = q.filter(DocumentTag.document_id == self.id)
        q = q.filter(DocumentTag.type.in_(DocumentTag.MAPPING.keys()))
        q = q.order_by(DocumentTag.weight.desc())
        q = q.limit(Document.MAX_TAGS)
        for tag in q.all():
            prop = DocumentTag.MAPPING.get(tag.type)
            if prop is not None:
                proxy.add(prop, tag.text)
        return proxy

    def to_dict(self):
        proxy = self.to_proxy()
        data = proxy.to_full_dict()
        data.update(self.to_dict_dates())
        data.update({
            'name': self.name,
            'status': self.status,
            'foreign_id': self.foreign_id,
            'document_id': self.id,
            'collection_id': self.collection_id,
            'error_message': self.error_message,
            'uploader_id': self.uploader_id,
        })
        return data

    def __repr__(self):
        return '<Document(%r,%r,%r)>' % (self.id, self.schema, self.title)
