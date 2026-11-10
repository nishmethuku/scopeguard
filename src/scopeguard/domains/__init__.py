from . import booking, inbox, shop

ALL_FAMILIES = booking.FAMILIES + shop.FAMILIES + inbox.FAMILIES
FAMILY_INDEX = {(f.domain, f.name): f for f in ALL_FAMILIES}
