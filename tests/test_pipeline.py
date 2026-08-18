from src.main import image_sync_allows_catalogue


def test_deployment_readiness_requires_complete_image_traversal():
    assert image_sync_allows_catalogue(
        {
            "image_sync_complete": False,
            "stopped_after_budget": True,
            "stopped_after_failures": False,
            "remaining": 20,
        }
    ) is False
    assert image_sync_allows_catalogue(
        {
            "image_sync_complete": False,
            "stopped_after_budget": False,
            "stopped_after_failures": True,
            "remaining": 1,
        }
    ) is False
    assert image_sync_allows_catalogue(
        {
            "image_sync_complete": True,
            "stopped_after_budget": False,
            "stopped_after_failures": False,
            "remaining": 0,
            "failed": 2,
            "missing": 3,
        }
    ) is True
