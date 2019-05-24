import logging
from flask_babel import gettext
from werkzeug.exceptions import BadRequest

from aleph.index.indexes import entities_read_index
from aleph.index.indexes import collections_index
from aleph.index.entities import EXCLUDE_DEFAULT
from aleph.logic.matching import match_query
from aleph.search.parser import QueryParser, SearchQueryParser  # noqa
from aleph.search.result import QueryResult, DatabaseQueryResult  # noqa
from aleph.search.result import SearchQueryResult  # noqa
from aleph.search.query import Query

log = logging.getLogger(__name__)


class EntitiesQuery(Query):
    TEXT_FIELDS = ['text']
    PREFIX_FIELD = 'names.text'
    SKIP_FILTERS = ['schema', 'schemata']
    EXCLUDE_FIELDS = EXCLUDE_DEFAULT
    SORT_DEFAULT = []

    def get_index(self):
        schemata = self.parser.getlist('filter:schema')
        if len(schemata):
            return entities_read_index(schema=schemata, expand=False)
        schemata = self.parser.getlist('filter:schemata')
        if not len(schemata):
            raise BadRequest(gettext("No schema is specified for the query."))
        return entities_read_index(schema=schemata)


class MatchQuery(EntitiesQuery):
    """Given an entity, find the most similar other entities."""

    def __init__(self, parser, entity=None, collection_ids=None):
        self.entity = entity
        self.collection_ids = collection_ids
        super(MatchQuery, self).__init__(parser)

    def get_index(self):
        # Attempt to find only matches within the "matchable" set of
        # entity schemata. For example, a Company and be matched to
        # another company or a LegalEntity, but not a Person.
        # Real estate is "unmatchable", i.e. even if two plots of land
        # have almost the same name and criteria, it does not make
        # sense to suggest they are the same.
        schemata = list(self.entity.schema.matchable_schemata)
        return entities_read_index(schema=schemata)

    def get_query(self):
        query = super(MatchQuery, self).get_query()
        return match_query(self.entity,
                           collection_ids=self.collection_ids,
                           query=query)


class CollectionsQuery(Query):
    TEXT_FIELDS = ['label^3', 'foreign_id^3', 'text']
    SORT_DEFAULT = ['_score', {'label.kw': 'asc'}]
    PREFIX_FIELD = 'label'

    def get_index(self):
        return collections_index()
