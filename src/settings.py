from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic import ValidationError
from pathlib import Path
from collections import ChainMap
from re import compile
from re import MULTILINE
from typing import ClassVar

KV_PATTERN = compile(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)(?:\r?\n|$)", MULTILINE)



class Settings(BaseSettings):
    description: ClassVar[str | None] = None

    @classmethod
    def __pydantic_init_subclass__(cls, **_):
        env_file = ".env." + cls.__name__
        cls.model_config = SettingsConfigDict(env_file=env_file, frozen=False)
        cls.description = cls.description or cls.__name__
        Path(env_file).touch()

    @classmethod
    def _get_filename(cls) -> str:
        return cls.model_config["env_file"]
    
    @classmethod
    def update(cls, new_settings: dict[str]):
        with open(cls._get_filename(), "r+") as f:
            data = f.read()
            f.seek(0)
            f.write(
                "\n".join(
                    f"{key}={value}"
                    for key, value in ChainMap(
                        {
                            key.upper(): value
                            for key, value in new_settings.items()
                        },
                        dict(KV_PATTERN.findall(data))
                    ).items()
                )
            )
            f.truncate()

    def __init__(self):
        try:
            return super().__init__()
        except ValidationError as e:
            missing_names = [
                err["loc"][0]
                for err in e.errors()
                if err["type"] == "missing"
            ]
            if not missing_names:
                raise
            source = type(self)
            missing_fields = [
                (name.upper(), field.description)
                for name, field in source.model_fields.items()
            ]
            raise MissingSettings(source, missing_fields)
        
class MissingSettings(Exception):
    def __init__(
        self,
        source: type[Settings],
        fields: list[tuple[str, str | None]]
    ):
        super().__init__()
        self.source = source
        self.fields = fields
    
class MCCSettings(Settings):
    description = "Microcontrolador"

    wifi_ap: str = Field(description="Ponto de acesso Wi-Fi")
    wifi_pass: str = Field(description="Senha do Wi-Fi")


class ServerSettings(Settings):
    description = "Servidor"

    bot_token: str = Field(description="Token do BOT Telegram")
    teacher_user_id: int = Field(
        description="ID de usuário da conta "
        "Telegram do professor"
    )



    









