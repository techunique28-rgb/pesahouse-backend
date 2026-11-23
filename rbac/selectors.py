from .models import Role, Staff


def roles_for_landlord():
    return Role.objects.all()


def staff_for_landlord():
    return Staff.objects.select_related("user").all()
