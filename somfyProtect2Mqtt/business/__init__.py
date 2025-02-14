"""Business Functions"""
import logging
import os
from datetime import datetime
from time import sleep

import schedule
from business.mqtt import mqtt_publish
from business.watermark import insert_watermark
from exceptions import SomfyProtectInitError
from http.client import RemoteDisconnected
from homeassistant.ha_discovery import (
    ALARM_STATUS,
    DEVICE_CAPABILITIES,
    ha_discovery_alarm,
    ha_discovery_alarm_actions,
    ha_discovery_cameras,
    ha_discovery_devices,
)
from mqtt import MQTTClient
from somfy_protect.api import SomfyProtectApi
from somfy_protect.api.devices.category import Category

LOGGER = logging.getLogger(__name__)

DEVICE_TAG = {}


def ha_sites_config(
    api: SomfyProtectApi,
    mqtt_client: MQTTClient,
    mqtt_config: dict,
    homeassistant_config: dict,
    my_sites_id: list,
) -> None:
    """HA Site Config"""
    LOGGER.info("Looking for Sites")
    for site_id in my_sites_id:
        # Alarm Status
        my_site = api.get_site(site_id=site_id)
        site = ha_discovery_alarm(
            site=my_site,
            mqtt_config=mqtt_config,
            homeassistant_config=homeassistant_config,
        )
        site_extended = ha_discovery_alarm_actions(
            site=my_site, mqtt_config=mqtt_config
        )
        configs = [site, site_extended]
        for site_config in configs:
            mqtt_publish(
                mqtt_client=mqtt_client,
                topic=site_config.get("topic"),
                payload=site_config.get("config"),
                retain=True,
            )
            mqtt_client.client.subscribe(site_config.get("config").get("command_topic"))

        try:
            scenarios_core = api.get_scenarios_core(site_id=my_site.id)
            LOGGER.info(f"Scenarios Core for {my_site.label} => {scenarios_core}")
            scenarios = api.get_scenarios(site_id=my_site.id)
            LOGGER.info(f"Scenarios for {my_site.label} => {scenarios}")
            LOGGER.warning(f"v4 => {api.get_site_scenario(site_id=site_id)}")
        except Exception as exp:
            LOGGER.warning(f"Error while getting scenarios: {exp}")
            continue


def ha_devices_config(
    api: SomfyProtectApi,
    mqtt_client: MQTTClient,
    mqtt_config: dict,
    my_sites_id: list,
) -> None:
    """HA Devices Config"""
    LOGGER.info("Looking for Devices")
    for site_id in my_sites_id:
        my_devices = api.get_devices(site_id=site_id)
        for device in my_devices:
            LOGGER.info(f"Configuring Device: {device.label}")
            settings = device.settings.get("global")
            status = device.status
            status_settings = {**status, **settings}

            for state in status_settings:
                if not DEVICE_CAPABILITIES.get(state):
                    LOGGER.debug(f"No Config for {state}")
                    continue
                device_config = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name=state,
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=device_config.get("topic"),
                    payload=device_config.get("config"),
                    retain=True,
                )
                if state == "device_lost":
                    old_topic = device_config.get("topic").replace(
                        "device_tracker", "binary_sensor"
                    )
                    mqtt_publish(
                        mqtt_client=mqtt_client,
                        topic=old_topic,
                        payload={},
                        retain=True,
                    )

                if device_config.get("config").get("command_topic"):
                    mqtt_client.client.subscribe(
                        device_config.get("config").get("command_topic")
                    )

            if "box" in device.device_definition.get("type"):
                LOGGER.info(f"Found Link {device.device_definition.get('label')}")
                reboot = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="reboot",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=reboot.get("topic"),
                    payload=reboot.get("config"),
                    retain=True,
                )
                mqtt_client.client.subscribe(reboot.get("config").get("command_topic"))

                halt = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="halt",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=halt.get("topic"),
                    payload=halt.get("config"),
                    retain=True,
                )
                mqtt_client.client.subscribe(halt.get("config").get("command_topic"))

            if "camera" in device.device_definition.get(
                "type"
            ) or "allinone" in device.device_definition.get("type"):
                LOGGER.info(f"Found Camera {device.device_definition.get('label')}")
                camera_config = ha_discovery_cameras(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=camera_config.get("topic"),
                    payload=camera_config.get("config"),
                    retain=True,
                )
                reboot = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="reboot",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=reboot.get("topic"),
                    payload=reboot.get("config"),
                    retain=True,
                )
                mqtt_client.client.subscribe(reboot.get("config").get("command_topic"))

                halt = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="halt",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=halt.get("topic"),
                    payload=halt.get("config"),
                    retain=True,
                )
                mqtt_client.client.subscribe(halt.get("config").get("command_topic"))
                # Manual Snapshot
                device_config = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="snapshot",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=device_config.get("topic"),
                    payload=device_config.get("config"),
                    retain=True,
                )
                if device_config.get("config").get("command_topic"):
                    mqtt_client.client.subscribe(
                        device_config.get("config").get("command_topic")
                    )

                # Stream
                stream = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="stream",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=stream.get("topic"),
                    payload=stream.get("config"),
                    retain=True,
                )
                if stream.get("config").get("command_topic"):
                    mqtt_client.client.subscribe(
                        stream.get("config").get("command_topic")
                    )
                    mqtt_client.client.subscribe(
                        f"{mqtt_config.get('topic_prefix', 'somfyProtect2mqtt')}/{site_id}/{device.id}/stream"
                    )

            # Works with Websockets
            if "remote" in device.device_definition.get("type"):
                LOGGER.info(f"Found {device.device_definition.get('label')}")
                key_fob_config = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="presence",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=key_fob_config.get("topic"),
                    payload=key_fob_config.get("config"),
                    retain=True,
                )
            if "mss_outdoor_siren" in device.device_definition.get(
                "device_definition_id"
            ):
                mss_outdoor_siren = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="test_siren1s",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=mss_outdoor_siren.get("topic"),
                    payload=mss_outdoor_siren.get("config"),
                    retain=True,
                )
                mqtt_client.client.subscribe(
                    mss_outdoor_siren.get("config").get("command_topic")
                )

            if "mss_siren" in device.device_definition.get("device_definition_id"):
                for sensor in [
                    "smokeExtended",
                    "siren1s",
                    "armed",
                    "disarmed",
                    "intrusion",
                    "ok",
                ]:
                    LOGGER.info(f"Found mss_siren, adding sound test: {sensor}")
                    mss_siren = ha_discovery_devices(
                        site_id=site_id,
                        device=device,
                        mqtt_config=mqtt_config,
                        sensor_name=f"test_{sensor}",
                    )
                    mqtt_publish(
                        mqtt_client=mqtt_client,
                        topic=mss_siren.get("topic"),
                        payload=mss_siren.get("config"),
                        retain=True,
                    )
                mqtt_client.client.subscribe(
                    mss_siren.get("config").get("command_topic")
                )

            if "pir" in device.device_definition.get(
                "type"
            ) or "tag" in device.device_definition.get("type"):
                LOGGER.info(
                    f"Found Motion Sensor (PIR & IntelliTag) {device.device_definition.get('label')}"
                )
                pir_config = ha_discovery_devices(
                    site_id=site_id,
                    device=device,
                    mqtt_config=mqtt_config,
                    sensor_name="motion_sensor",
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=pir_config.get("topic"),
                    payload=pir_config.get("config"),
                    retain=True,
                )
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=pir_config.get("config").get("state_topic"),
                    payload={"motion_sensor": "False"},
                    retain=True,
                )


def update_sites_status(
    api: SomfyProtectApi,
    mqtt_client: MQTTClient,
    mqtt_config: dict,
    my_sites_id: list,
) -> None:
    """Uodate Devices Status (Including zone)"""
    LOGGER.info("Update Sites Status")
    for site_id in my_sites_id:
        try:
            site = api.get_site(site_id=site_id)
            LOGGER.info(f"Update {site.label} Status")

            try:
                # Push status to MQTT
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=f"{mqtt_config.get('topic_prefix', 'somfyProtect2mqtt')}/{site_id}/state",
                    payload={
                        "security_level": ALARM_STATUS.get(
                            site.security_level, "disarmed"
                        )
                    },
                    retain=True,
                )
            except Exception as exp:
                LOGGER.warning(f"Error while updating MQTT: {exp}")
                continue
        except RemoteDisconnected as exp:
            LOGGER.info(f"Retrying...")
        except Exception as exp:
            LOGGER.warning(f"Error while refreshing site: {exp}")
            continue

            # history_lines = api.get_history(site_id=site_id)
            # for history_line in history_lines:
            #     LOGGER.info(history_line)
            #     LOGGER.info(
            #        f"{history_line.get('occurred_at')} - {history_line.get('message_type')} - {history_line.get('message_key')} - {history_line.get('origin')}"
            #     )
            #     if history_line.get("message_type") == "home_activity":
            #         if history_line.get("message_key") == "homeActivity.user.exit":
            #             LOGGER.info(f"OUT: {history_line.get('origin').get('user_id')}")
            #             if DEVICE_TAG.get(history_line.get("origin").get("user_id")):
            #                 device = api.get_device(
            #                     site_id=site_id,
            #                     device_id=DEVICE_TAG.get(
            #                         history_line.get("origin").get("user_id")
            #                     ),
            #                 )
            #                 LOGGER.info(device.label)
            #         elif (
            #             history_line.get("message_key") == "homeActivity.user.entrance"
            #         ):
            #             LOGGER.info(f"IN: {history_line.get('origin').get('user_id')}")

        except Exception as exp:
            LOGGER.warning(f"Error while refreshing site: {exp}")
            continue


def update_devices_status(
    api: SomfyProtectApi,
    mqtt_client: MQTTClient,
    mqtt_config: dict,
    my_sites_id: list,
) -> None:
    """Update Devices Status (Including zone)"""
    LOGGER.info("Update Devices Status")
    for site_id in my_sites_id:
        try:
            my_devices = api.get_devices(site_id=site_id)
            for device in my_devices:
                settings = device.settings.get("global")
                if device.settings.get("global").get("user_id"):
                    DEVICE_TAG[device.settings.get("global").get("user_id")] = device.id
                status = device.status
                status_settings = {**status, **settings}

                # Convert Values to String
                keys_values = status_settings.items()
                payload = {str(key): str(value) for key, value in keys_values}

                # Push status to MQTT
                mqtt_publish(
                    mqtt_client=mqtt_client,
                    topic=f"{mqtt_config.get('topic_prefix', 'somfyProtect2mqtt')}/{site_id}/{device.id}/state",
                    payload=payload,
                    retain=True,
                )
        except Exception as exp:
            LOGGER.warning(f"Error while refreshing devices: {exp}")
            continue


def update_camera_snapshot(
    api: SomfyProtectApi,
    mqtt_client: MQTTClient,
    mqtt_config: dict,
    my_sites_id: list,
) -> None:
    """Update Camera Snapshot"""
    LOGGER.info("Update Camera Snapshot")
    for site_id in my_sites_id:
        try:
            for category in [
                Category.INDOOR_CAMERA,
                Category.OUTDDOR_CAMERA,
                Category.MYFOX_CAMERA,
                Category.SOMFY_ONE_PLUS,
                Category.SOMFY_ONE,
            ]:
                my_devices = api.get_devices(site_id=site_id, category=category)
                for device in my_devices:
                    LOGGER.info(
                        f"Shutter is {device.status.get('shutter_state', 'opened')}"
                    )
                    if device.status.get("shutter_state", "opened") != "closed":
                        api.camera_refresh_snapshot(
                            site_id=site_id, device_id=device.id
                        )
                        response = api.camera_snapshot(
                            site_id=site_id, device_id=device.id
                        )
                        if response.status_code == 200:
                            now = datetime.now()
                            timestamp = int(now.timestamp())

                            # Write image to temp file
                            path = f"{device.id}-{timestamp}.jpeg"
                            with open(path, "wb") as tmp_file:
                                for chunk in response:
                                    tmp_file.write(chunk)

                            # Add Watermark
                            insert_watermark(
                                file=f"{os.getcwd()}/{path}",
                                watermark=now.strftime("%Y-%m-%d %H:%M:%S"),
                            )

                            # Read and Push to MQTT
                            with open(path, "rb") as tmp_file:
                                image = tmp_file.read()
                            byte_arr = bytearray(image)
                            topic = f"{mqtt_config.get('topic_prefix', 'somfyProtect2mqtt')}/{site_id}/{device.id}/snapshot"
                            mqtt_publish(
                                mqtt_client=mqtt_client,
                                topic=topic,
                                payload=byte_arr,
                                retain=True,
                                is_json=False,
                            )
                            # Clean file
                            os.remove(path)

        except Exception as exp:
            LOGGER.warning(f"Error while refreshing snapshot: {exp}")
            continue
