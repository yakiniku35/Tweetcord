import os
import sys
import copy
import asyncio
import sqlite3
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Ensure project root and test directory are importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    import conftest  # noqa: F401 - global test isolation for standalone execution
except ImportError:
    pass

from core.classes import ParsedTweet
from src.notification import display_tools
from src.notification.display_tools import _get_media_url, _md_escape_label, gen_embed
from src.db_function.init_db import migrate_db


PBS = 'https://pbs.twimg.com/media/ABC123.jpg'


# ---------------------------------------------------------------------------
# _get_media_url
# ---------------------------------------------------------------------------
class TestGetMediaUrl(unittest.TestCase):
    def test_pbs_url_gets_quality(self):
        self.assertEqual(_get_media_url(PBS, 'orig'), f'{PBS}?name=orig')
        self.assertEqual(_get_media_url(PBS, 'large'), f'{PBS}?name=large')

    def test_existing_query_replaced_not_duplicated(self):
        result = _get_media_url(f'{PBS}?format=jpg&name=small', '4096x4096')
        self.assertEqual(result, f'{PBS}?format=jpg&name=4096x4096')
        self.assertEqual(result.count('?'), 1)
        self.assertEqual(result.count('name='), 1)

    def test_non_pbs_urls_unchanged(self):
        for url in (
            'https://mosaic.fxtwitter.com/jpeg/123/a/b',
            'https://d.fxtwitter.com/user/status/123.jpg',
            'https://video.twimg.com/ext_tw_video/1/vid.mp4?tag=12',
            'https://pbs.twimg.com/profile_images/1/abc_normal.jpg',
        ):
            self.assertEqual(_get_media_url(url, 'orig'), url)

    def test_none_and_empty_unchanged(self):
        self.assertIsNone(_get_media_url(None, 'orig'))
        self.assertEqual(_get_media_url('', 'orig'), '')


# ---------------------------------------------------------------------------
# _md_escape_label
# ---------------------------------------------------------------------------
class TestMdEscapeLabel(unittest.TestCase):
    def test_replaces_brackets(self):
        self.assertEqual(_md_escape_label('a]b)c'), 'a］b）c')

    def test_plain_unchanged(self):
        self.assertEqual(_md_escape_label('normal_user'), 'normal_user')

    def test_none(self):
        self.assertEqual(_md_escape_label(None), '')


# ---------------------------------------------------------------------------
# gen_embed (built_in mode)
# ---------------------------------------------------------------------------
def _make_tweet(text='hello world', is_retweet=False, is_quoted=False):
    author = SimpleNamespace(
        name='Test Name',
        username='test_user',
        profile_image_url_https='https://pbs.twimg.com/profile_images/1/abc_normal.jpg',
    )
    return SimpleNamespace(
        author=author,
        text=text,
        url='https://twitter.com/test_user/status/123',
        created_on=datetime(2026, 1, 1, tzinfo=timezone.utc),
        is_retweet=is_retweet,
        is_quoted=is_quoted,
    )


def _make_parsed(urls=None, media_type=None):
    parsed = ParsedTweet({
        'tweet': {
            'raw_text': {'text': 'hello world'},
            'author': {'screen_name': 'test_user'},
            'media': {'all': []},
            'translation': {'text': None, 'source_lang': 'en'},
        }
    })
    urls = urls or []
    parsed.media.urls = urls
    parsed.media.length = len(urls)
    parsed.media.type = media_type if urls else None
    parsed.media.mosaic_url = 'https://mosaic.fxtwitter.com/jpeg/123/a/b' if len(urls) > 1 else (urls[0] if urls else None)
    parsed.media.external_url = None
    return parsed


class TestGenEmbed(unittest.TestCase):
    def setUp(self):
        fx = copy.deepcopy(display_tools.FX_SETTINGS)
        fx['media']['enabled'] = True
        fx['media']['external'] = False
        fx['rt_text']['enabled'] = True
        fx['rt_text']['simplified'] = True
        fx['mosaic'] = True
        self.fx = fx
        self.patchers = [
            patch.object(display_tools, 'FX_SETTINGS', fx),
            patch.object(display_tools, 't', side_effect=lambda key, **kw: f'ACTION({key})'),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    @staticmethod
    def _field(embed, name):
        return next((f for f in embed.fields if f.name == name), None)

    def test_title_and_description(self):
        tweet = _make_tweet()
        embeds = gen_embed(tweet, _make_parsed(), 'orig')
        self.assertEqual(len(embeds), 1)
        e = embeds[0]
        self.assertEqual(e.title, 'Test Name (@test_user) ACTION(display.action.tweeted)')
        self.assertTrue(e.description.endswith(
            '[ACTION(display.field.open_tweet)](https://twitter.com/test_user/status/123) | [@test_user](https://twitter.com/test_user)'
        ))
        self.assertIn('hello world', e.description)
        self.assertIsNotNone(self._field(e, 'ACTION(display.field.action)'))
        self.assertEqual(self._field(e, 'ACTION(display.field.action)').value, 'ACTION(display.field.tweeted)')
        self.assertIsNone(self._field(e, 'ACTION(display.field.media)'))

    def test_retweet_action(self):
        e = gen_embed(_make_tweet(is_retweet=True), _make_parsed(), 'orig')[0]
        self.assertTrue(e.title.endswith('ACTION(display.action.retweeted)'))
        self.assertEqual(self._field(e, 'ACTION(display.field.action)').value, 'ACTION(display.field.retweeted)')

    def test_single_photo_quality(self):
        e = gen_embed(_make_tweet(), _make_parsed([PBS], 'photo'), 'large')
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].image.url, f'{PBS}?name=large')
        self.assertEqual(self._field(e[0], 'ACTION(display.field.media)').value, 'ACTION(display.field.photo)')

    def test_multi_photo_non_mosaic_quality(self):
        self.fx['mosaic'] = False
        urls = [f'https://pbs.twimg.com/media/IMG{i}.jpg?format=jpg&name=small' for i in range(3)]
        embeds = gen_embed(_make_tweet(), _make_parsed(urls, 'photo'), '4096x4096')
        self.assertEqual(len(embeds), 4)
        self.assertEqual(self._field(embeds[0], 'ACTION(display.field.media)').value, 'ACTION(display.field.photos)')
        for i, img_embed in enumerate(embeds[1:]):
            self.assertEqual(img_embed.image.url, f'https://pbs.twimg.com/media/IMG{i}.jpg?format=jpg&name=4096x4096')
            self.assertEqual(img_embed.url, 'https://twitter.com/test_user/status/123')

    def test_multi_photo_mosaic_uses_mosaic_url(self):
        urls = [PBS, 'https://pbs.twimg.com/media/DEF.jpg']
        embeds = gen_embed(_make_tweet(), _make_parsed(urls, 'photo'), 'orig')
        self.assertEqual(len(embeds), 1)
        self.assertEqual(embeds[0].image.url, 'https://mosaic.fxtwitter.com/jpeg/123/a/b')


# ---------------------------------------------------------------------------
# migrate_db
# ---------------------------------------------------------------------------
def _create_legacy_db(db_path):
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE user (id TEXT PRIMARY KEY, username TEXT, latest_tweet TEXT, client_used TEXT, enabled INTEGER DEFAULT 1);
        CREATE TABLE channel (id TEXT PRIMARY KEY, server_id TEXT);
        CREATE TABLE notification (user_id TEXT, channel_id TEXT, role_id TEXT, enabled INTEGER DEFAULT 1, enable_type TEXT DEFAULT 11, enable_media_type TEXT DEFAULT 11, customized_msg TEXT DEFAULT NULL, PRIMARY KEY(user_id, channel_id));
        INSERT INTO notification (user_id, channel_id) VALUES ('u1', 'c1');
    """)
    con.commit()
    con.close()


def _notification_columns(db_path):
    con = sqlite3.connect(db_path)
    try:
        return {row[1]: row for row in con.execute('PRAGMA table_info(notification)')}
    finally:
        con.close()


async def test_migrate_db_adds_image_quality(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_PATH', str(tmp_path))
    db_path = tmp_path / 'tracked_accounts.db'
    _create_legacy_db(db_path)
    assert 'image_quality' not in _notification_columns(db_path)

    await migrate_db()

    cols = _notification_columns(db_path)
    assert 'image_quality' in cols
    assert cols['image_quality'][4] == "'orig'"  # dflt_value

    con = sqlite3.connect(db_path)
    try:
        assert con.execute("SELECT image_quality FROM notification WHERE user_id='u1'").fetchone()[0] == 'orig'
        con.execute("INSERT INTO notification (user_id, channel_id) VALUES ('u2', 'c2')")
        assert con.execute("SELECT image_quality FROM notification WHERE user_id='u2'").fetchone()[0] == 'orig'
    finally:
        con.close()


async def test_migrate_db_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_PATH', str(tmp_path))
    db_path = tmp_path / 'tracked_accounts.db'
    _create_legacy_db(db_path)

    with patch('src.db_function.init_db.log') as mock_log:
        await migrate_db()
        await migrate_db()  # must not raise
        mock_log.error.assert_not_called()

    assert list(_notification_columns(db_path)).count('image_quality') == 1
