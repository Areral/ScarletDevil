from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any

class ProxyConfig(BaseModel):
    server: str
    port: int
    uuid: Optional[str] = None
    password: Optional[str] = None
    method: Optional[str] = None
    type: str = "tcp"
    security: str = "none"
    path: Optional[str] = None
    host: Optional[str] = None
    sni: Optional[str] = None
    fp: Optional[str] = None
    alpn: Optional[str] = None
    pbk: Optional[str] = None
    sid: Optional[str] = None
    flow: Optional[str] = None
    spx: Optional[str] = None
    service_name: Optional[str] = Field(None, alias="serviceName")
    alter_id: int = Field(0, alias="aid")
    obfs: Optional[str] = None
    obfs_password: Optional[str] = Field(None, alias="obfs-password")
    raw_meta: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('port', mode='before')
    @classmethod
    def validate_port(cls, v):
        try:
            return int(v)
        except (ValueError, TypeError):
            return 443

class ProxyNode(BaseModel):
    protocol: str
    config: ProxyConfig
    raw_uri: str
    latency: int = -1
    speed: float = 0.0
    country: str = "UN"
    is_bs: bool = False
    source_url: str = ""

    @property
    def strict_id(self) -> str:
        ident = self.config.uuid or self.config.password or "anon"
        return f"{self.protocol}:{self.config.server}:{self.config.port}:{ident}"

    @property
    def machine_id(self) -> str:
        return f"{self.config.server}:{self.config.port}"
