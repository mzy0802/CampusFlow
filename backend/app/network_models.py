"""Validated editable graphs. Campus and fictional examples never share records."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict

class Node(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=100)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    latitude: float = Field(ge=-85, le=85, allow_inf_nan=False)
    kind: Literal['junction', 'entrance', 'parking'] = 'junction'
    parking_id: str | None = Field(None, max_length=80)
    capacity: int = Field(100, ge=1, le=100000)
    available: int = Field(50, ge=0, le=100000)

class Edge(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    source: str
    target: str
    modes: list[Literal['walk', 'bike']] = Field(default_factory=lambda: ['walk', 'bike'], min_length=1, max_length=2)
    bidirectional: bool = True
    congestion: float = Field(1, ge=1, le=10, allow_inf_nan=False)
    verified: bool = True

class Network(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    dataset: Literal['campus', 'example']
    revision: int = Field(0, ge=0)
    nodes: list[Node] = Field(default_factory=list, max_length=2000)
    edges: list[Edge] = Field(default_factory=list, max_length=5000)

    @model_validator(mode='after')
    def references(self):
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)): raise ValueError('节点 ID 重复')
        lookup = {n.id: n for n in self.nodes}
        eids = [e.id for e in self.edges]
        if len(eids) != len(set(eids)): raise ValueError('道路 ID 重复')
        for e in self.edges:
            if e.source not in lookup or e.target not in lookup: raise ValueError('道路引用不存在的节点')
            if e.source == e.target: raise ValueError('道路不能连接同一节点')
            a, b = lookup[e.source], lookup[e.target]
            if (a.longitude, a.latitude) == (b.longitude, b.latitude): raise ValueError('道路两端坐标不能相同')
        for n in self.nodes:
            if n.available > n.capacity: raise ValueError('示例空位不能大于容量')
            if self.dataset == 'campus' and n.kind == 'parking' and not n.parking_id:
                raise ValueError('校园停车入口必须关联已有停车区域')
        return self

class TripRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset: Literal['campus', 'example'] = 'campus'
    origin_id: str = Field(min_length=1, max_length=80)
    destination_id: str = Field(min_length=1, max_length=80)
    preference: Literal['fastest', 'less_walking'] = 'fastest'
    bike_speed_kmh: float = Field(12, ge=3, le=25, allow_inf_nan=False)
    walk_speed_kmh: float = Field(4.5, ge=1, le=8, allow_inf_nan=False)
    parking_minutes: float = Field(1, ge=0, le=30, allow_inf_nan=False)
    min_available: int = Field(1, ge=1, le=1000)
