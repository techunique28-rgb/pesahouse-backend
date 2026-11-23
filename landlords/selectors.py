from .models import Landlord, OrgUnit


def landlord_for_context(landlord_id):
    return Landlord.objects.get(id=landlord_id)


def org_units_for_landlord():
    return OrgUnit.objects.select_related("parent").filter(status="ACTIVE")
