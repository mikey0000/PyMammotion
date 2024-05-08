# This is an automatically generated file, please do not change
# gen by protobuf_to_pydantic[v0.2.6.2](https://github.com/so1n/protobuf_to_pydantic)
# Protobuf Version: 5.26.1 
# Pydantic Version: 2.6.2 
from google.protobuf.message import Message  # type: ignore
from pydantic import BaseModel
from pydantic import Field


class CommDataCouple(BaseModel):
    x: float = Field(default=0.0) 
    y: float = Field(default=0.0) 
