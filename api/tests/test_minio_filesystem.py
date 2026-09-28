"""Regression guard for MinioFileSystem.acreate_file.

The MinIO SDK's ``put_object`` requires a file-like object with ``read()`` —
passing raw bytes raises ``'bytes' object has no attribute 'read'``. Voice
previews were the first real caller of ``acreate_file`` and hit this in prod,
so lock the contract: the content source is read via ``await`` and whatever
reaches ``put_object`` must be readable, not raw bytes.
"""

from unittest.mock import MagicMock

import pytest

from api.services.filesystem.minio import MinioFileSystem


class _AsyncBytes:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


@pytest.mark.asyncio
async def test_acreate_file_streams_bytes_to_put_object():
    fs = MinioFileSystem.__new__(MinioFileSystem)  # skip __init__ (no server)
    fs.bucket_name = "voice-audio"
    fs.client = MagicMock()

    payload = b"RIFF....WAVE" * 4
    ok = await fs.acreate_file("voice-previews/x/y/Kore/hi.wav", _AsyncBytes(payload))

    assert ok is True
    fs.client.put_object.assert_called_once()
    kwargs = fs.client.put_object.call_args.kwargs
    data_arg = kwargs["data"] if "data" in kwargs else fs.client.put_object.call_args.args[2]
    # Must be a readable stream, NOT raw bytes.
    assert hasattr(data_arg, "read")
    assert not isinstance(data_arg, (bytes, bytearray))
    assert data_arg.read() == payload
    assert kwargs["length"] == len(payload)


def test_minio_removes_legacy_public_policy():
    from unittest.mock import patch
    with patch('api.services.filesystem.minio.Minio') as client:
        MinioFileSystem(public_endpoint='https://recordings.example.test')
    client.return_value.delete_bucket_policy.assert_called_once_with('voice-audio')
    client.return_value.set_bucket_policy.assert_not_called()


def test_minio_fails_closed_if_policy_cannot_be_removed():
    from unittest.mock import patch
    with patch('api.services.filesystem.minio.Minio') as client:
        client.return_value.delete_bucket_policy.side_effect = RuntimeError('denied')
        with pytest.raises(RuntimeError, match='denied'):
            MinioFileSystem(public_endpoint='https://recordings.example.test')


@pytest.mark.asyncio
async def test_presigned_download_and_upload_sign_public_host():
    from unittest.mock import patch
    from urllib.parse import urlsplit, parse_qs
    from minio import Minio
    internal = MagicMock()
    public = Minio('recordings.example.test', access_key='test-access', secret_key='test-secret', secure=True, region='us-east-1')
    with patch('api.services.filesystem.minio.Minio', side_effect=[internal, public]):
        fs = MinioFileSystem(endpoint='minio:9000', public_endpoint='https://recordings.example.test')
    for url in [await fs.aget_signed_url('org/recording.wav', expiration=60),
                await fs.aget_presigned_put_url('org/leads.csv', expiration=60)]:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        assert parsed.netloc == 'recordings.example.test'
        assert query['X-Amz-Expires'] == ['60']
        assert query['X-Amz-Signature']
    await fs.aget_signed_url('org/recording.wav', use_internal_endpoint=True)
    internal.presigned_get_object.assert_called_once()
