from aleph.tests.util import TestCase
from followthemoney import model
from followthemoney.types import registry

from aleph.analysis import tag_entity
from aleph.analysis.patterns import EMAIL_REGEX, IPV4_REGEX
from aleph.analysis.patterns import IPV6_REGEX, PHONE_REGEX
from aleph.analysis.patterns import IBAN_REGEX


class TestAnalysis(TestCase):

    def test_ner_extract(self):
        text = 'Das ist der Pudel von Angela Merkel. '
        text = text + text + text + text + text
        entity = model.make_entity('PlainText')
        entity.add('bodyText', text)
        tag_entity(entity)
        names = entity.get_type_values(registry.name)
        assert 'Angela Merkel' in names, names

    def test_pattern_extract(self):
        text = "Mr. Flubby Flubber called the number tel:+919988111222 twice"
        entity = model.make_entity('PlainText')
        entity.add('bodyText', text)
        tag_entity(entity)
        phones = entity.get_type_values(registry.phone)
        assert '+919988111222' in phones
        countries = entity.get_type_values(registry.country)
        assert 'in' in countries


class TestPatterns(TestCase):

    def test_phonenumbers(self):
        PHONE_NUMBERS = [
            '754-3010',
            '(541) 754-3010',
            '+1-541-754-3010',
            '1-541-754-3010',
            '001-541-754-3010',
            '191 541 754 3010',
            '(089) / 636-48018',
            '+49-89-636-48018',
            '19-49-89-636-48018',
            'phone: +49-89-636-48018',
            'tel +49-89-636-48018 or so',
        ]
        for number in PHONE_NUMBERS:
            matches = PHONE_REGEX.findall(number)
            assert len(matches) == 1

    def test_ipv4_address(self):
        IPV4_ADDRESSES = [
            "118.197.24.21",
            "0.0.0.0",
            "172.0.0.1"
        ]
        for ip in IPV4_ADDRESSES:
            matches = IPV4_REGEX.findall(ip)
            assert len(matches) == 1, matches

    def test_ipv6_address(self):
        IPV6_ADDRESSES = [
            "b239:181e:8f52:e4ee:ce42:c45c:6a03:4f14",
            "2001:db8:0:1234:0:567:8:1"
        ]
        for ip in IPV6_ADDRESSES:
            matches = IPV6_REGEX.findall(ip)
            assert len(matches) == 1

    def test_iban(self):
        IBANS = [
            'SC52BAHL01031234567890123456USD',
            'SK8975000000000012345671',
            'SI56192001234567892',
            'ES7921000813610123456789',
            'SE1412345678901234567890',
            'CH5604835012345678009',
            'TL380080012345678910157',
            'TN4401000067123456789123',
            'TR320010009999901234567890',
            'UA903052992990004149123456789',
            'AE460090000000123456789',
            'GB98MIDL07009312345678',
            'VG21PACG0000000123456789',
        ]
        for iban in IBANS:
            matches = IBAN_REGEX.findall(iban)
            assert len(matches) == 1

    def test_email(self):
        EMAILS = [
            "abc@sunu.in",
            "abc+netflix@sunu.in",
            "_@sunu.in"
        ]
        for email in EMAILS:
            matches = EMAIL_REGEX.findall(email)
            assert len(matches) == 1
