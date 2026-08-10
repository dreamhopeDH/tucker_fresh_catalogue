from src.images import image_has_changed


def test_image_url_change_is_the_only_change_signal():
    assert image_has_changed("https://e/old.jpg", "https://e/old.jpg") is False
    assert image_has_changed("https://e/old.jpg", "https://e/new.jpg") is True
    assert image_has_changed(None, "https://e/new.jpg") is True
