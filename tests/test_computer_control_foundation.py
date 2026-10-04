from app.computer.controller import ComputerController
from app.permissions.policy import PermissionPolicy


def test_permission_policy_levels():
    policy = PermissionPolicy()
    assert policy.allows("screenshot", "safe") is True
    assert policy.allows("delete_file", "dangerous") is False
    assert policy.allows("delete_file", "dangerous", confirm=True) is True


def test_controller_action_log():
    controller = ComputerController()
    controller.log_action("Opened Chrome")
    assert controller.action_log[-1] == "Opened Chrome"
