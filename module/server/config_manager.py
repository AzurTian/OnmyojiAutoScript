# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import copy
import json
import re
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError

from module.config.config_model import ConfigModel
from module.config.utils import convert_to_underscore, read_file, write_file
from module.logger import logger


CONFIG_NAME_RESERVED_CHARS = set('/\\:*?"<>|')
CONFIG_TASK_TRANSFER_EXCLUDED_KEYS = {
    "config_name",
    "running_task",
}
CONFIG_REDACTION_VALUE = "XXX"
CONFIG_REDACTION_PATHS = (
    "wanted_quests.wanted_quests_config.invite_friend_name",
    "*.invite_config.friend_list",
    "script.error.notify_config",
    "global_game.server.password",
    "script.device.serial",
    "script.device.handle",
    "script.device.emulatorinfo_name",
    "script.device.emulatorinfo_path",
    "find_jade.sup_account_list_*.account",
    "find_jade.sup_account_list_*.account_alias",
    "assist_battle.account_list_*.account",
    "assist_battle.account_list_*.account_alias",
)
CONFIG_REDACTION_KEYS = {
    "password",
    "token",
    "access_token",
    "cookie",
    "authorization",
}


class ConfigNameError(ValueError):
    """配置名称不合法。"""


class ConfigAlreadyExistsError(FileExistsError):
    """导入目标配置已存在。"""


class ConfigNotFoundError(FileNotFoundError):
    """配置文件不存在。"""


class ConfigJsonError(ValueError):
    """配置 JSON 无法解析。"""


class ConfigTaskError(ValueError):
    """配置任务名称或任务 JSON 不合法。"""


class ConfigValidationError(ValueError):
    """配置内容不符合当前 ConfigModel。"""

    def __init__(self, fields: list[dict[str, str]]) -> None:
        super().__init__("Config validation failed")
        self.fields = fields

class ConfigManager:
    @staticmethod
    def config_dir() -> Path:
        return Path.cwd() / 'config'

    @staticmethod
    def config_path(name: str) -> Path:
        return ConfigManager.config_dir() / f'{name}.json'

    @staticmethod
    def validate_config_name(name: str, *, allow_template: bool = True) -> str:
        """
        校验配置名称，返回去除首尾空白后的名称。
        """
        name = (name or '').strip()
        if not name:
            raise ConfigNameError("Config name is required")
        if not allow_template and name == 'template':
            raise ConfigNameError("Config name template is reserved")
        if '.' in name:
            raise ConfigNameError("Config name cannot contain dots")
        if any(ch in CONFIG_NAME_RESERVED_CHARS for ch in name):
            raise ConfigNameError("Config name contains reserved path characters")
        if any(ord(ch) < 32 for ch in name):
            raise ConfigNameError("Config name contains control characters")
        return name

    @staticmethod
    def _format_validation_error(error: ValidationError) -> list[dict[str, str]]:
        fields = []
        for item in error.errors():
            loc = item.get("loc", ())
            field = ".".join(str(part) for part in loc) if loc else "__root__"
            fields.append(
                {
                    "field": field,
                    "message": item.get("msg", ""),
                    "type": item.get("type", ""),
                }
            )
        return fields

    @staticmethod
    def _format_field_error(field: str, message: str, error_type: str) -> dict[str, str]:
        return {
            "field": field,
            "message": message,
            "type": error_type,
        }

    @staticmethod
    def _is_model_type(annotation: Any) -> bool:
        return isinstance(annotation, type) and issubclass(annotation, BaseModel)

    @staticmethod
    def _list_item_model(annotation: Any) -> type[BaseModel] | None:
        origin = get_origin(annotation)
        if origin is not list:
            return None
        args = get_args(annotation)
        if not args:
            return None
        item_type = args[0]
        return item_type if ConfigManager._is_model_type(item_type) else None

    @staticmethod
    def _dynamic_list_item_model(key: str, fields: dict[str, Any]) -> tuple[str, type[BaseModel]] | None:
        for field_name, field_info in fields.items():
            if not re.fullmatch(rf'{re.escape(field_name)}_\d+', key):
                continue
            item_model = ConfigManager._list_item_model(field_info.annotation)
            if item_model is not None:
                return field_name, item_model
        return None

    @staticmethod
    def _join_field_path(prefix: str, key: str) -> str:
        return f'{prefix}.{key}' if prefix else key

    @staticmethod
    def _collect_unknown_field_errors(data: Any, model_type: type[BaseModel], prefix: str = '') -> list[dict[str, str]]:
        if not isinstance(data, dict):
            return []

        errors = []
        fields = model_type.model_fields
        for key, value in data.items():
            field_path = ConfigManager._join_field_path(prefix, str(key))
            if key == 'config_name' and model_type is ConfigModel:
                continue
            if key not in fields:
                dynamic_field = ConfigManager._dynamic_list_item_model(str(key), fields)
                if dynamic_field is None:
                    errors.append(
                        ConfigManager._format_field_error(
                            field_path,
                            'Extra inputs are not permitted',
                            'extra_forbidden',
                        )
                    )
                    continue
                _, item_model = dynamic_field
                errors.extend(ConfigManager._collect_unknown_field_errors(value, item_model, field_path))
                continue

            annotation = fields[key].annotation
            if ConfigManager._is_model_type(annotation):
                errors.extend(ConfigManager._collect_unknown_field_errors(value, annotation, field_path))
                continue
            item_model = ConfigManager._list_item_model(annotation)
            if item_model is not None and isinstance(value, list):
                for index, item in enumerate(value):
                    errors.extend(
                        ConfigManager._collect_unknown_field_errors(item, item_model, f'{field_path}.{index}')
                    )
        return errors

    @staticmethod
    def _collect_dynamic_field_validation_errors(
        data: Any,
        model_type: type[BaseModel],
        prefix: str = '',
    ) -> list[dict[str, str]]:
        if not isinstance(data, dict):
            return []

        errors = []
        fields = model_type.model_fields
        for key, value in data.items():
            field_path = ConfigManager._join_field_path(prefix, str(key))
            dynamic_field = ConfigManager._dynamic_list_item_model(str(key), fields)
            if dynamic_field is not None:
                _, item_model = dynamic_field
                try:
                    item_model(**value)
                except ValidationError as e:
                    for error in ConfigManager._format_validation_error(e):
                        error["field"] = ConfigManager._join_field_path(field_path, error["field"])
                        errors.append(error)
                except TypeError as e:
                    errors.append(ConfigManager._format_field_error(field_path, str(e), 'model_type'))
                continue

            if key not in fields:
                continue
            annotation = fields[key].annotation
            if ConfigManager._is_model_type(annotation):
                errors.extend(ConfigManager._collect_dynamic_field_validation_errors(value, annotation, field_path))
                continue
            item_model = ConfigManager._list_item_model(annotation)
            if item_model is not None and isinstance(value, list):
                for index, item in enumerate(value):
                    errors.extend(
                        ConfigManager._collect_dynamic_field_validation_errors(item, item_model, f'{field_path}.{index}')
                    )
        return errors

    @staticmethod
    def _validate_config_model(name: str, data: dict[str, Any]) -> None:
        fields = ConfigManager._collect_unknown_field_errors(data, ConfigModel)
        fields.extend(ConfigManager._collect_dynamic_field_validation_errors(data, ConfigModel))
        model_data = copy.deepcopy(data)
        model_data.pop('config_name', None)
        try:
            ConfigModel(config_name=name, **model_data)
        except ValidationError as e:
            fields.extend(ConfigManager._format_validation_error(e))
        if fields:
            raise ConfigValidationError(fields)

    @staticmethod
    def validate_task_key(task_name: str) -> str:
        """
        校验并归一化配置任务名称。
        """
        task_key = convert_to_underscore((task_name or '').strip())
        if not task_key:
            raise ConfigTaskError("Task name is required")
        if task_key in CONFIG_TASK_TRANSFER_EXCLUDED_KEYS:
            raise ConfigTaskError(f'Task cannot be transferred: {task_key}')
        if task_key not in ConfigModel.model_fields:
            raise ConfigTaskError(f'Task not found: {task_key}')
        if not ConfigManager._is_model_type(ConfigModel.model_fields[task_key].annotation):
            raise ConfigTaskError(f'Task is not transferable: {task_key}')
        return task_key

    @staticmethod
    def parse_task_json_source(
        *,
        json_text: str | None = None,
        file_content: bytes | None = None,
    ) -> dict[str, Any]:
        """
        解析任务 JSON 输入，json_text 和 file_content 必须二选一。
        """
        has_json_text = json_text is not None
        has_file_content = file_content is not None
        if has_json_text == has_file_content:
            raise ConfigJsonError("Exactly one of json_text or file must be provided")

        if has_file_content:
            try:
                text = file_content.decode('utf-8')
            except UnicodeDecodeError as e:
                raise ConfigJsonError(f'Task JSON file must be UTF-8 JSON: {e}') from e
        else:
            text = json_text

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ConfigJsonError(f'Task JSON parse failed: {e}') from e

        if not isinstance(data, dict):
            raise ConfigJsonError("Task JSON root must be an object")
        return data

    @staticmethod
    def validate_task_import_payload(task_key: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        校验导入任务 JSON 的顶层结构，并返回对应任务 value。
        """
        if len(data) != 1:
            raise ConfigJsonError("Task JSON root must contain exactly one task key")
        payload_task_key, task_value = next(iter(data.items()))
        if payload_task_key != task_key:
            raise ConfigJsonError(f'Task JSON key mismatch: expected {task_key}, got {payload_task_key}')
        if not isinstance(task_value, dict):
            raise ConfigJsonError("Task JSON value must be an object")
        return task_value

    @staticmethod
    def _prefix_validation_error(error: dict[str, str], prefix: str) -> dict[str, str]:
        field = error.get("field", "")
        error["field"] = ConfigManager._join_field_path(prefix, field) if field else prefix
        return error

    @staticmethod
    def validate_task_value(task_key: str, task_value: dict[str, Any]) -> dict[str, Any]:
        """
        使用对应任务模型校验任务 value，返回可写回 JSON 的数据。
        """
        task_model_type = ConfigModel.model_fields[task_key].annotation
        fields = ConfigManager._collect_unknown_field_errors(task_value, task_model_type, task_key)
        fields.extend(ConfigManager._collect_dynamic_field_validation_errors(task_value, task_model_type, task_key))

        try:
            task_model = task_model_type(**copy.deepcopy(task_value))
        except ValidationError as e:
            for error in ConfigManager._format_validation_error(e):
                fields.append(ConfigManager._prefix_validation_error(error, task_key))
            task_model = None

        if fields:
            raise ConfigValidationError(fields)
        return task_model.model_dump()

    @staticmethod
    def import_task_config(name: str, task_name: str, data: dict[str, Any]) -> tuple[str, str]:
        """
        导入单个任务配置，返回配置名称和归一化任务 key。
        """
        name = ConfigManager.validate_config_name(name, allow_template=False)
        task_key = ConfigManager.validate_task_key(task_name)
        file_path = ConfigManager.config_path(name)
        if not file_path.exists():
            raise ConfigNotFoundError(f'Config not found: {name}')

        task_value = ConfigManager.validate_task_import_payload(task_key, data)
        validated_task_value = ConfigManager.validate_task_value(task_key, task_value)

        try:
            config_data = read_file(file_path)
        except json.JSONDecodeError as e:
            raise ConfigJsonError(f'Config JSON parse failed: {e}') from e
        if not isinstance(config_data, dict):
            raise ConfigJsonError("Config JSON root must be an object")
        if task_key not in config_data:
            raise ConfigNotFoundError(f'Task not found in config: {task_key}')

        new_config_data = copy.deepcopy(config_data)
        new_config_data[task_key] = validated_task_value
        ConfigManager._validate_config_model(name, new_config_data)
        write_file(file_path, new_config_data)
        logger.info(f'import task {task_key} to {file_path}')
        return name, task_key

    @staticmethod
    def load_task_for_transfer(name: str, task_name: str, *, allow_template: bool = True) -> tuple[str, str, dict[str, Any]]:
        """
        读取单个任务配置片段，返回配置名、任务 key、任务 JSON。
        """
        name, data = ConfigManager.load_config_for_export(name)
        if not allow_template and name == 'template':
            raise ConfigNameError("Config name template is reserved")
        task_key = ConfigManager.validate_task_key(task_name)
        if task_key not in data:
            raise ConfigNotFoundError(f'Task not found in config: {task_key}')
        task_value = data[task_key]
        if not isinstance(task_value, dict):
            raise ConfigJsonError("Task JSON value must be an object")
        return name, task_key, {task_key: copy.deepcopy(task_value)}

    @staticmethod
    def load_task_for_export(name: str, task_name: str) -> tuple[str, str, dict[str, Any]]:
        """
        读取脱敏后的单个任务配置片段。
        """
        name, data = ConfigManager.load_config_for_export(name)
        task_key = ConfigManager.validate_task_key(task_name)
        if task_key not in data:
            raise ConfigNotFoundError(f'Task not found in config: {task_key}')
        redacted = ConfigManager.redact_config(data)
        task_value = redacted.get(task_key)
        if not isinstance(task_value, dict):
            raise ConfigJsonError("Task JSON value must be an object")
        return name, task_key, {task_key: copy.deepcopy(task_value)}

    @staticmethod
    def import_config(name: str, data: dict[str, Any]) -> str:
        """
        导入配置内容，返回最终配置名称。
        """
        name = ConfigManager.validate_config_name(name, allow_template=False)
        file_path = ConfigManager.config_path(name)
        if file_path.exists():
            raise ConfigAlreadyExistsError(f'Config already exists: {name}')
        if not isinstance(data, dict):
            raise ConfigJsonError("Config JSON root must be an object")

        ConfigManager._validate_config_model(name, data)
        write_file(file_path, data)
        logger.info(f'import config {name} to {file_path}')
        return name

    @staticmethod
    def load_config_for_export(name: str) -> tuple[str, dict[str, Any]]:
        """
        读取待导出的配置，返回校验后的名称和配置内容。
        """
        name = ConfigManager.validate_config_name(name, allow_template=True)
        file_path = ConfigManager.config_path(name)
        if not file_path.exists():
            raise ConfigNotFoundError(f'Config not found: {name}')
        try:
            data = read_file(file_path)
        except json.JSONDecodeError as e:
            raise ConfigJsonError(f'Config JSON parse failed: {e}') from e
        if not isinstance(data, dict):
            raise ConfigJsonError("Config JSON root must be an object")
        return name, data

    @staticmethod
    def redact_config(data: dict[str, Any]) -> dict[str, Any]:
        """
        返回脱敏后的配置副本，不修改传入对象。
        """
        redacted = copy.deepcopy(data)
        for rule in CONFIG_REDACTION_PATHS:
            ConfigManager._redact_by_path(redacted, rule.split('.'))
        ConfigManager._redact_by_key(redacted)
        return redacted

    @staticmethod
    def _segment_match(key: str, segment: str) -> bool:
        if segment == '*':
            return True
        if segment.endswith('*'):
            return key.startswith(segment[:-1])
        return key == segment

    @staticmethod
    def _redact_by_path(node: Any, segments: list[str]) -> None:
        if not segments or not isinstance(node, dict):
            return
        segment = segments[0]
        is_leaf = len(segments) == 1
        for key, value in node.items():
            if not ConfigManager._segment_match(str(key), segment):
                continue
            if is_leaf:
                node[key] = CONFIG_REDACTION_VALUE
            else:
                ConfigManager._redact_by_path(value, segments[1:])

    @staticmethod
    def _redact_by_key(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() in CONFIG_REDACTION_KEYS:
                    node[key] = CONFIG_REDACTION_VALUE
                else:
                    ConfigManager._redact_by_key(value)
        elif isinstance(node, list):
            for item in node:
                ConfigManager._redact_by_key(item)

    @staticmethod
    def all_script_files() -> list[str]:
        """
        获取所有的脚本文件 除了tmplate
        :return: ['oas1', 'oas2']
        """
        # 获取某个路径的所有json文件名
        config_path = Path.cwd() / 'config'
        json_files = config_path.glob('*.json')
        result = []
        for json in json_files:
            if json.stem == 'template':
                continue
            result.append(json.stem)
        if len(result) == 0:
            # 如果没有脚本文件 则创建一个
            ConfigManager.copy(file='oas1', template='template')
            result.append('oas1')
        return result

    @staticmethod
    def all_json_file() -> list:
        """
        获取所有的json文件
        :return: ['oas1', 'oas2']
        """
        # 获取某个路径的所有json文件名
        config_path = Path.cwd() / 'config'
        json_files = config_path.glob('*.json')
        result = []
        for json in json_files:
            if json.stem == 'template':
                result.insert(0, json.stem)
            else:
                result.append(json.stem)
        return result

    @staticmethod
    def copy(file: str, template: str = 'template') -> None:
        """
        复制一个配置文件
        :param file:  不带json后缀
        :param template:
        :return:
        """
        config_path = Path.cwd() / 'config'
        template_path = config_path / f'{template}.json'
        file_path = config_path / f'{file}.json'
        if file_path.exists():
            logger.error(f'{file_path} is exists')
            return

        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(template_content)
        logger.info(f'copy {template_path} to {file_path}')


    @staticmethod
    def generate_script_name() -> str:
        """
        生成一个新的配置的名字
        :return:
        """
        all_script_files = ConfigManager.all_script_files()
        if not all_script_files:
            return 'oas1'

        script_numbers = []
        for script_file in all_script_files:
            match = re.search(r'\d+', script_file)
            if match:
                script_number = int(match.group())
                script_numbers.append(script_number)

        if not script_numbers:
            return 'oas1'
        script_numbers.sort()
        new_script_number = script_numbers[-1] + 1
        return f'oas{new_script_number}'

    @staticmethod
    def rename(old_name: str, new_name: str) -> bool:
        """
        重命名一个配置文件
        :param old_name: 旧的配置文件名称
        :param new_name: 新的配置文件名称
        :return: True or False
        """
        config_path = Path.cwd() / 'config'
        old_path = config_path / f'{old_name}.json'
        new_path = config_path / f'{new_name}.json'
        if not old_path.exists():
            logger.error(f'{old_path} is not exists')
            return False
        if new_path.exists():
            logger.error(f'{new_path} is exists')
            return False
        try:
            old_path.rename(new_path)
            logger.info(f'rename {old_path} to {new_path}')
            return True
        except Exception as e:
            logger.error(f'rename {old_path} to {new_path} failed: {e}')
            return False

    @staticmethod
    def delete(file: str) -> bool:
        """
        删除一个配置文件
        :param file:  不带json后缀
        :return: True or False
        """
        config_path = Path.cwd() / 'config'
        file_path = config_path / f'{file}.json'
        if not file_path.exists():
            logger.error(f'{file_path} is not exists')
            return False
        try:
            file_path.unlink()
            logger.info(f'delete {file_path}')
            return True
        except Exception as e:
            logger.error(f'delete {file_path} failed: {e}')
            return False
