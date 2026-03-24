"""Tests for firebase_storage.py."""

import json
from unittest.mock import MagicMock, patch

import pytest

from firebase_storage import (
    _check_configured,
    download_summary,
    upload_summary,
    download_accuracy_log,
    upload_accuracy_log,
    cleanup_old_archives,
)


class TestCheckConfigured:
    def test_returns_false_without_env(self, monkeypatch):
        monkeypatch.delenv('FIREBASE_PROJECT', raising=False)
        assert _check_configured() is False

    def test_returns_true_with_env(self, monkeypatch):
        monkeypatch.setenv('FIREBASE_PROJECT', 'test-proj')
        assert _check_configured() is True


class TestDownloadSummary:
    @patch('firebase_storage.read_document')
    def test_returns_dict(self, mock_read):
        mock_read.return_value = {'meta': {'init_utc': '2026-01-01T00:00:00+00:00'}}
        result = download_summary()
        assert result['meta']['init_utc'] == '2026-01-01T00:00:00+00:00'
        mock_read.assert_called_once_with('pipeline_state', 'keelung_summary')

    @patch('firebase_storage.read_document')
    def test_returns_none_when_missing(self, mock_read):
        mock_read.return_value = None
        assert download_summary() is None


class TestUploadSummary:
    @patch('firebase_storage.write_document')
    def test_calls_write(self, mock_write):
        data = {'meta': {'init_utc': '2026-01-01T00:00:00+00:00'}}
        upload_summary(data)
        mock_write.assert_called_once_with('pipeline_state', 'keelung_summary', data)


class TestDownloadAccuracyLog:
    @patch('firebase_storage.read_document')
    def test_returns_entries_list(self, mock_read):
        mock_read.return_value = {'entries': [{'init_utc': 'a'}, {'init_utc': 'b'}]}
        result = download_accuracy_log()
        assert len(result) == 2

    @patch('firebase_storage.read_document')
    def test_returns_none_when_missing(self, mock_read):
        mock_read.return_value = None
        assert download_accuracy_log() is None

    @patch('firebase_storage.read_document')
    def test_returns_none_when_no_entries_key(self, mock_read):
        mock_read.return_value = {'something_else': 'data'}
        assert download_accuracy_log() is None


class TestUploadAccuracyLog:
    @patch('firebase_storage.write_document')
    def test_writes_full_array_and_latest_entry(self, mock_write):
        entries = [
            {'init_utc': '2026-01-01T00:00:00+00:00', 'model_id': 'WRF'},
            {'init_utc': '2026-01-02T00:00:00+00:00', 'model_id': 'WRF'},
        ]
        upload_accuracy_log(entries)
        # Should write full array + latest entry individually
        assert mock_write.call_count == 2
        # First call: full array
        args0 = mock_write.call_args_list[0]
        assert args0[0][0] == 'pipeline_state'
        assert args0[0][1] == 'accuracy_log'
        assert len(args0[0][2]['entries']) == 2
        # Second call: individual entry
        args1 = mock_write.call_args_list[1]
        assert args1[0][0] == 'accuracy_log'
        assert 'WRF' in args1[0][1]

    @patch('firebase_storage.write_document')
    def test_empty_list_only_writes_array(self, mock_write):
        upload_accuracy_log([])
        assert mock_write.call_count == 1


class TestDocIdSanitization:
    @patch('firebase_storage.write_document')
    def test_colons_and_plus_replaced(self, mock_write):
        entries = [{'init_utc': '2026-01-01T00:00:00+00:00', 'model_id': 'WRF'}]
        upload_accuracy_log(entries)
        doc_id = mock_write.call_args_list[1][0][1]
        assert ':' not in doc_id
        assert '+' not in doc_id


class TestCleanupOldArchives:
    @patch('firebase_storage._get_bucket')
    def test_keeps_named_archive(self, mock_bucket_fn):
        from datetime import datetime, timezone
        mock_bucket = MagicMock()
        mock_bucket_fn.return_value = mock_bucket

        # Two blobs: one to keep, one to delete
        blob_keep = MagicMock()
        blob_keep.name = 'archives/current.tar.gz'
        blob_delete = MagicMock()
        blob_delete.name = 'archives/old.tar.gz'
        mock_bucket.list_blobs.return_value = [blob_keep, blob_delete]

        deleted = cleanup_old_archives(keep_name='current.tar.gz')
        assert deleted == 1
        blob_delete.delete.assert_called_once()
        blob_keep.delete.assert_not_called()

    @patch('firebase_storage._get_bucket')
    def test_deletes_all_when_no_keep(self, mock_bucket_fn):
        mock_bucket = MagicMock()
        mock_bucket_fn.return_value = mock_bucket

        blob1 = MagicMock()
        blob1.name = 'archives/a.tar.gz'
        blob2 = MagicMock()
        blob2.name = 'archives/b.tar.gz'
        mock_bucket.list_blobs.return_value = [blob1, blob2]

        deleted = cleanup_old_archives()
        assert deleted == 2
