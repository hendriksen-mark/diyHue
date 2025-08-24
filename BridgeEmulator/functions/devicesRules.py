from functions.core import nextFreeId
import configManager
from HueObjects import Rule, ResourceLink
from datetime import datetime, timezone
import logManager
from typing import List, Any

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)

def create_rule(actions: List[dict[str, Any]], conditions: List[dict[str, Any]], name: str) -> dict[str, Any]:
    return {
        "actions": actions,
        "conditions": conditions,
        "name": name
    }

def add_rules_to_bridge(rules: List[dict[str, Any]], sensor_id: str) -> None:
    resourcelinkId = nextFreeId(bridgeConfig, "resourcelinks")
    owner = bridgeConfig["apiUsers"][list(bridgeConfig["apiUsers"])[0]]
    bridgeConfig["resourcelinks"][resourcelinkId] = ResourceLink.ResourceLink({
        "id_v1": resourcelinkId,
        "classid": 15555,
        "description": f"Rules for sensor {sensor_id}",
        "links": [f"/{bridgeConfig['sensors'][sensor_id].getObjectPath()['resource']}/{bridgeConfig['sensors'][sensor_id].getObjectPath()['id']}"],
        "name": f"Emulator rules {sensor_id}",
        "owner": owner
    })
    for rule in rules:
        ruleId = nextFreeId(bridgeConfig, "rules")
        data = rule
        data.update({"id_v1": ruleId, "owner": owner, "recycle": True})
        bridgeConfig["rules"][ruleId] = Rule.Rule(data)
        resourcelink_object: ResourceLink.ResourceLink = bridgeConfig["resourcelinks"][resourcelinkId]
        resourcelink_object.add_link(bridgeConfig["rules"][ruleId])

def addTradfriDimmer(sensor_id: str, group_id: str) -> None:
    rules = [
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": True, "bri": 1}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "2002"},
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "false"}
            ],
            name=f"Remote {sensor_id} turn on"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": False}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "4002"},
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "true"},
                {"address": f"/groups/{group_id}/action/bri", "operator": "eq", "value": "1"}
            ],
            name=f"Dimmer Switch {sensor_id} off"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": False}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "3002"},
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "true"},
                {"address": f"/groups/{group_id}/action/bri", "operator": "eq", "value": "1"}
            ],
            name=f"Remote {sensor_id} turn off"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": 32, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "true"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "2002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} rotate right"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": 56, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "true"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "1002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} rotate fast right"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": -32, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/groups/{group_id}/action/bri", "operator": "gt", "value": "1"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "3002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} rotate left"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": -56, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/groups/{group_id}/action/bri", "operator": "gt", "value": "1"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "4002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} rotate left"
        )
    ]
    add_rules_to_bridge(rules, sensor_id)

def addTradfriCtRemote(sensor_id: str, group_id: str) -> None:
    rules = [
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": True}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "1002"},
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "false"}
            ],
            name=f"Remote {sensor_id} button on"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": False}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "1002"},
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "true"}
            ],
            name=f"Remote {sensor_id} button off"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": 30, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "2002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} up-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": 56, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "2001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} up-long"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": -30, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "3002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} dn-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": -56, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "3001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} dn-long"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"ct_inc": 50, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "4002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} ctl-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"ct_inc": 100, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "4001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} ctl-long"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"ct_inc": -50, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "5002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} ct-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"ct_inc": -100, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "5001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} ct-long"
        )
    ]
    add_rules_to_bridge(rules, sensor_id)

def addTradfriOnOffSwitch(sensor_id: str, group_id: str) -> None:
    rules = [
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": True}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "1002"}
            ],
            name=f"Remote {sensor_id} button on"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": False}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "2002"}
            ],
            name=f"Remote {sensor_id} button off"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": 30, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "1001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} up-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": -30, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "2001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} dn-press"
        )
    ]
    add_rules_to_bridge(rules, sensor_id)

def addTradfriSceneRemote(sensor_id: str, group_id: str) -> None:
    rules = [
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": True}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "1002"},
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "false"}
            ],
            name=f"Remote {sensor_id} button on"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"on": False}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"},
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "1002"},
                {"address": f"/groups/{group_id}/state/any_on", "operator": "eq", "value": "true"}
            ],
            name=f"Remote {sensor_id} button off"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": 30, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "2002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} up-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": 56, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "2001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} up-long"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": -30, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "3002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} dn-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"bri_inc": -56, "transitiontime": 9}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "3001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} dn-long"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"scene_inc": -1}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "4002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} ctl-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"scene_inc": -1}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "4001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} ctl-long"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"scene_inc": 1}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "5002"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} ct-press"
        ),
        create_rule(
            actions=[{"address": f"/groups/{group_id}/action", "body": {"scene_inc": 1}, "method": "PUT"}],
            conditions=[
                {"address": f"/sensors/{sensor_id}/state/buttonevent", "operator": "eq", "value": "5001"},
                {"address": f"/sensors/{sensor_id}/state/lastupdated", "operator": "dx"}
            ],
            name=f"Dimmer Switch {sensor_id} ct-long"
        )
    ]
    resourcelinkId = nextFreeId(bridgeConfig, "resourcelinks")
    bridgeConfig["resourcelinks"][resourcelinkId] = {
        "classid": 15555,
        "description": f"Rules for sensor {sensor_id}",
        "links": [f"/sensors/{sensor_id}"],
        "name": f"Emulator rules {sensor_id}",
        "owner": list(bridgeConfig["config"]["whitelist"])[0]
    }
    for rule in rules:
        ruleId = nextFreeId(bridgeConfig, "rules")
        bridgeConfig["rules"][ruleId] = rule
        bridgeConfig["rules"][ruleId].update({
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "lasttriggered": None,
            "owner": list(bridgeConfig["config"]["whitelist"])[0],
            "recycle": True,
            "status": "enabled",
            "timestriggered": 0
        })
        bridgeConfig["resourcelinks"][resourcelinkId]["links"].append(f"/rules/{ruleId}")
