def device_topic(branch_id: int, device_id: int, suffix: str = 'event') -> str:
    """与 backend mqtt_bridge 订阅的主题一致：event / telemetry / status。"""
    return f'library/{branch_id}/device/{device_id}/{suffix}'


def command_topic(branch_id: int, device_id: int) -> str:
    """后端 publish_events 下发的门禁命令主题。"""
    return f'library/{branch_id}/device/{device_id}/command'
