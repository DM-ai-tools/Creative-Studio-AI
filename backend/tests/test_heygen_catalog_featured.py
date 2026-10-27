from app.services.heygen_catalog import (
    ELIN_PRESENTER_LOOK_ID,
    _pin_featured_avatars,
)
from app.schemas.generation import CatalogOption


def test_elin_presenter_is_always_in_featured_catalog_once():
    featured, _poses = _pin_featured_avatars([], [])

    elin = [option for option in featured if option.id == ELIN_PRESENTER_LOOK_ID]
    assert len(elin) == 1
    assert elin[0].label == "Elin Presenter 1 (Female)"


def test_elin_presenter_is_not_duplicated_when_configured():
    featured, _poses = _pin_featured_avatars(
        [
            CatalogOption(
                id=ELIN_PRESENTER_LOOK_ID,
                label="Elin Presenter 1 (Female)",
                gender="female",
            )
        ],
        [],
    )

    assert sum(option.id == ELIN_PRESENTER_LOOK_ID for option in featured) == 1
