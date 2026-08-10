from io import BytesIO

from src.b2_store import B2ImageStore


class FakeS3:
    def __init__(self):
        self.uploads = []

    def get_object(self, **kwargs):
        return {"Body": BytesIO(b'{"p": {"status": "downloaded"}}')}

    def upload_fileobj(self, stream, bucket, key, ExtraArgs):
        self.uploads.append((bucket, key, stream.read(), ExtraArgs))

    def upload_file(self, path, bucket, key, ExtraArgs):
        self.uploads.append((bucket, key, path, ExtraArgs))


def test_b2_manifest_and_immutable_image_metadata(tmp_path):
    client = FakeS3()
    store = B2ImageStore("https://s3.test", "id", "key", "bucket", client=client)
    assert store.download_manifest()["p"]["status"] == "downloaded"
    store.upload_manifest({"a": 1})
    image = tmp_path / "x.webp"
    image.write_bytes(b"webp")
    store.upload_image(image, "test/products/x/hash.webp")
    assert client.uploads[0][1] == "test/state/image-manifest.json"
    assert client.uploads[1][3] == {
        "ContentType": "image/webp",
        "CacheControl": "public, max-age=31536000, immutable",
    }
