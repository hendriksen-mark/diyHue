import logManager
import configManager

from datetime import datetime
from threading import Thread
from time import sleep
import requests
from typing import List, Tuple, Union, Any
from HueObjects import Rule, Sensor, Rule

logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config

def evaluate_condition(condition: dict[str, Any], device: Any, current_time: datetime) -> Tuple[bool, int, List[str]]:
    """
    Evaluate a single condition for a rule.

    Args:
        condition (dict[str, Any]): The condition to evaluate.
        device (Any): The device to check the condition against.
        current_time (datetime): The current time.

    Returns:
        Tuple[bool, int, List[str]]: A tuple containing the result of the evaluation, delay if any, and sensor details.
    """
    try:
        url_pieces = condition["address"].split('/')
        resource, device_id, state_key = url_pieces[1], url_pieces[2], url_pieces[4]
        state_value = bridgeConfig[resource][device_id].state[state_key]
        operator, value = condition["operator"], condition["value"]
        device_found = resource == device.getObjectPath()["resource"] and device_id == device.getObjectPath()["id"]

        if operator == "eq":
            return (state_value == (value == "true")) if value in ["true", "false"] else (int(state_value) == int(value)), 0, []
        elif operator == "gt":
            return int(state_value) > int(value), 0, []
        elif operator == "lt":
            return int(state_value) < int(value), 0, []
        elif operator == "dx":
            return device_found and bridgeConfig[resource][device_id].dxState[state_key] == current_time, 0, []
        elif operator == "in":
            return evaluate_time_condition(value), 0, []
        elif operator == "ddx":
            if bridgeConfig[resource][device_id].dxState[state_key] == current_time:
                ddx = int(value[2:4]) * 3600 + int(value[5:7]) * 60 + int(value[-2:])
                return True, ddx, url_pieces
            return False, 0, []
    except Exception as e:
        logging.exception(f"rule {condition.get('name', 'unknown')} failed, reason: {type(e).__name__} {e}")
        return False, 0, []

    return False, 0, []

def evaluate_time_condition(value: str) -> bool:
    """
    Evaluate a time condition.

    Args:
        value (str): The time condition value.

    Returns:
        bool: True if the current time is within the specified period, False otherwise.
    """
    periods = value.split('/')
    if value[0] == "T":
        time_start = datetime.strptime(periods[0], "T%H:%M:%S").time()
        time_end = datetime.strptime(periods[1], "T%H:%M:%S").time()
        now_time = datetime.now().time()
        if time_start < time_end:
            return time_start <= now_time <= time_end
        return time_start <= now_time or now_time <= time_end
    return False

def checkRuleConditions(rule: Rule.Rule, device: Any, current_time: datetime, ignore_ddx: bool = False) -> Union[Tuple[bool, int, List[str]], Tuple[bool]]:
    """
    Check all conditions for a rule.

    Args:
        rule (Any): The rule to check.
        device (Any): The device to check the rule against.
        current_time (datetime): The current time.
        ignore_ddx (bool): Whether to ignore ddx conditions.

    Returns:
        Union[Tuple[bool, int, List[str]], Tuple[bool]]: A tuple containing the result of the check, delay if any, and sensor details.
    """
    ddx = 0
    device_found = False
    ddx_sensor = []
    for condition in rule.conditions:
        result, delay, sensor = evaluate_condition(condition, device, current_time)
        if not result:
            return [False, 0]
        if delay > 0:
            ddx = delay
            ddx_sensor = sensor
        device_found = True

    return [True, ddx, ddx_sensor] if device_found else [False]

def ddxRecheck(rule: Rule.Rule, device: Any, current_time: datetime, ddx_delay: int, ddx_sensor: List[str]) -> None:
    """
    Recheck a ddx rule after a delay.

    Args:
        rule (Any): The rule to recheck.
        device (Any): The device to check the rule against.
        current_time (datetime): The current time.
        ddx_delay (int): The delay in seconds.
        ddx_sensor (List[str]): The sensor details.
    """
    for x in range(ddx_delay):
        if current_time != bridgeConfig[ddx_sensor[1]][ddx_sensor[2]].dxState[ddx_sensor[4]]:
            logging.info(f"ddx rule {rule.id_v1}, name: {rule.name} canceled after {x} seconds")
            return # rule not valid anymore because sensor state changed while waiting for ddx delay
        sleep(1)
    current_time = datetime.now()
    rule_state = checkRuleConditions(rule, device, current_time, True)
    if rule_state[0]: #if all conditions are met again
        logging.info(f"delayed rule {rule.id_v1}, name: {rule.name} is triggered")
        rule.lasttriggered = current_time.strftime("%Y-%m-%dT%H:%M:%S")
        rule.timestriggered += 1
        for action in rule.actions:
            if action["method"] == "POST":
                requests.post(f"http://localhost/api/local{action['address']}", json=action["body"], timeout=5)
            elif action["method"] == "PUT":
                requests.put(f"http://localhost/api/local{action['address']}", json=action["body"], timeout=5)

def threadActions(actionsToExecute: List[dict[str, Any]]) -> None:
    """
    Execute actions in a separate thread.

    Args:
        actionsToExecute (List[dict[str, Any]]): The actions to execute.
    """
    sleep(0.2)
    for action in actionsToExecute:
        urlPrefix = "http://localhost/api/local"
        if action["address"].startswith("http"):
            urlPrefix = ""
        if action["method"] == "POST":
            requests.post(f"{urlPrefix}{action['address']}", json=action["body"], timeout=5)
        elif action["method"] == "PUT":
            requests.put(f"{urlPrefix}{action['address']}", json=action["body"], timeout=5)

def rulesProcessor(device: Any, current_time: datetime) -> None:
    """
    Process all rules for a device.

    Args:
        device (Any): The device to process rules for.
        current_time (datetime): The current time.
    """
    logging.debug(f"Processing rules for {device.name}")
    bridgeConfig["config"]["localtime"] = current_time.strftime("%Y-%m-%dT%H:%M:%S") #required for operator dx to address /config/localtime
    actionsToExecute = []
    for key, rule in bridgeConfig["rules"].items():
        rule: Rule.Rule = rule
        if rule.status == "enabled":
            rule_result = checkRuleConditions(rule, device, current_time)
            if rule_result[0]:
                if rule_result[1] == 0: #is not ddx rule
                    logging.info(f"rule {rule.id_v1}, name: {rule.name} is triggered")
                    rule.lasttriggered = current_time.strftime("%Y-%m-%dT%H:%M:%S")
                    rule.timestriggered += 1
                    for action in rule.actions:
                        actionsToExecute.append(action)
                else: #if ddx rule
                    logging.info(f"ddx rule {rule.id_v1}, name: {rule.name} will be re validated after {rule_result[1]} seconds")
                    Thread(target=ddxRecheck, args=[rule, device, current_time, rule_result[1], rule_result[2]]).start()

    Thread(target=threadActions, args=[actionsToExecute]).start()
